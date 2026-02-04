#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    # Ignore if not supported
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$script:ConfigCache = $null
$script:PromptCache = @{}
$script:PromptMap = @{
    system  = 'system.md'
    reply   = 'reply.md'
    summary = 'summary.md'
    todo    = 'todo.md'
}

function Is-Blank {
    param([string]$Value)
    return [string]::IsNullOrWhiteSpace($Value)
}

function Unquote {
    param([string]$Value)
    if ($null -eq $Value) {
        return ''
    }
    $trimmed = $Value.Trim()
    if ($trimmed.Length -ge 2) {
        if (($trimmed.StartsWith('"') -and $trimmed.EndsWith('"')) -or ($trimmed.StartsWith("'") -and $trimmed.EndsWith("'"))) {
            return $trimmed.Substring(1, $trimmed.Length - 2)
        }
    }
    return $trimmed
}

function Read-YamlSimple {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return @{}
    }
    $result = @{}
    $current = $null
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trim = $line.Trim()
        if ($trim -eq '' -or $trim.StartsWith('#')) {
            continue
        }
        if ($line -match '^(\s*)([^:#]+)\s*:\s*(.*)$') {
            $indent = $matches[1].Length
            $key = $matches[2].Trim()
            $value = $matches[3]
            if ($indent -eq 0) {
                if (Is-Blank $value) {
                    $result[$key] = @{}
                    $current = $key
                } else {
                    $result[$key] = (Unquote $value)
                    $current = $null
                }
            } elseif ($null -ne $current) {
                if (-not ($result[$current] -is [hashtable])) {
                    $result[$current] = @{}
                }
                $result[$current][$key] = (Unquote $value)
            }
        }
    }
    return $result
}

function Get-ConfigValue {
    param(
        [hashtable]$Data,
        [string]$Key,
        [string]$Fallback
    )
    if ($null -eq $Data) {
        return $Fallback
    }
    $value = $Data[$Key]
    if (Is-Blank $value) {
        return $Fallback
    }
    return [string]$value
}

function Get-ConfigPath {
    if (-not (Is-Blank $env:SLACK_AGENT_CONFIG)) {
        return $env:SLACK_AGENT_CONFIG
    }
    return (Join-Path $PSScriptRoot 'config\config.yml')
}

function Get-Config {
    if ($script:ConfigCache) {
        return $script:ConfigCache
    }
    $data = Read-YamlSimple (Get-ConfigPath)
    $slackData = $data['slack']
    $openaiData = $data['openai']
    $ollamaData = $data['ollama']
    $aiData = $data['ai']

    $searchDefault = if (-not (Is-Blank $env:SLACK_SEARCH_QUERY)) { $env:SLACK_SEARCH_QUERY } else { 'from:me' }
    $openaiModelDefault = if (-not (Is-Blank $env:OPENAI_MODEL)) { $env:OPENAI_MODEL } else { 'gpt-4o-mini' }
    $ollamaBaseDefault = if (-not (Is-Blank $env:OLLAMA_BASE_URL)) { $env:OLLAMA_BASE_URL } else { 'http://localhost:11434' }
    $aiProviderDefault = if (-not (Is-Blank $env:AI_PROVIDER)) { $env:AI_PROVIDER } else { 'ollama' }

    $slack = [pscustomobject]@{
        user_token  = Get-ConfigValue $slackData 'user_token' ($env:SLACK_USER_TOKEN)
        token       = Get-ConfigValue $slackData 'token' ($env:SLACK_TOKEN)
        search_query = Get-ConfigValue $slackData 'search_query' $searchDefault
    }
    $openai = [pscustomobject]@{
        api_key = Get-ConfigValue $openaiData 'api_key' ($env:OPENAI_API_KEY)
        model   = Get-ConfigValue $openaiData 'model' $openaiModelDefault
    }
    $ollama = [pscustomobject]@{
        base_url = Get-ConfigValue $ollamaData 'base_url' $ollamaBaseDefault
        model    = Get-ConfigValue $ollamaData 'model' ($env:OLLAMA_MODEL)
    }
    $aiProvider = Get-ConfigValue $aiData 'provider' $aiProviderDefault

    $script:ConfigCache = [pscustomobject]@{
        slack       = $slack
        openai      = $openai
        ollama      = $ollama
        ai_provider = ($aiProvider.Trim().ToLower())
    }
    return $script:ConfigCache
}

function Get-PromptDir {
    if (-not (Is-Blank $env:SLACK_AGENT_PROMPTS)) {
        return $env:SLACK_AGENT_PROMPTS
    }
    return (Join-Path $PSScriptRoot 'prompts')
}

function Load-Prompts {
    if ($script:PromptCache.Count -gt 0) {
        return $script:PromptCache
    }
    $base = Get-PromptDir
    foreach ($key in $script:PromptMap.Keys) {
        $path = Join-Path $base $script:PromptMap[$key]
        if (Test-Path -LiteralPath $path) {
            $script:PromptCache[$key] = (Get-Content -LiteralPath $path -Raw -Encoding UTF8).Trim()
        }
    }
    return $script:PromptCache
}

function Get-Prompt {
    param([string]$Key)
    $prompts = Load-Prompts
    if (-not $prompts.ContainsKey($Key)) {
        throw "prompt file not found for key: $Key"
    }
    return $prompts[$Key]
}

function Get-SystemPrompt {
    return (Get-Prompt 'system')
}

function Resolve-AiProvider {
    param([string]$Value)
    $provider = ($Value | ForEach-Object { $_.Trim().ToLower() })
    if ($provider -eq 'openai' -or $provider -eq 'ollama') {
        return $provider
    }
    return $null
}

function Build-UserPrompt {
    param(
        [string]$Instruction,
        [string]$Context,
        [string]$Text
    )
    return "$Instruction`n`n[コンテキスト]`n$Context`n`n[メッセージ]`n$Text"
}

function Build-Messages {
    param(
        [string]$Instruction,
        [string]$Context,
        [string]$Text
    )
    $system = Get-SystemPrompt
    $user = Build-UserPrompt $Instruction $Context $Text
    return @(
        @{ role = 'system'; content = $system },
        @{ role = 'user'; content = $user }
    )
}

function New-SupportResult {
    param(
        [string]$Content,
        [string]$Model,
        [string]$Error = $null
    )
    return [pscustomobject]@{
        Content = $Content
        Model   = $Model
        Error   = $Error
    }
}

function New-ErrorSupport {
    param([string[]]$Errors)
    if ($Errors -and $Errors.Count -gt 0) {
        $detail = ($Errors | ForEach-Object { "- $_" }) -join "`n"
        $message = "AIサポートの生成に失敗しました。`n$detail"
    } else {
        $message = 'AIサポートの生成に失敗しました。'
    }
    return New-SupportResult $message 'error' $message
}

function Get-OpenAIResponseText {
    param($Response)
    if ($null -eq $Response) {
        return $null
    }
    if ($Response.PSObject.Properties['output_text']) {
        if (-not (Is-Blank $Response.output_text)) {
            return $Response.output_text
        }
    }
    if ($Response.PSObject.Properties['output']) {
        foreach ($item in $Response.output) {
            if ($item.PSObject.Properties['content']) {
                foreach ($content in $item.content) {
                    if ($content.PSObject.Properties['text']) {
                        if (-not (Is-Blank $content.text)) {
                            return $content.text
                        }
                    }
                }
            }
        }
    }
    return $null
}

function Invoke-OpenAI {
    param(
        [string]$Text,
        [string]$Mode,
        [string]$Context,
        $Config
    )
    $apiKey = $Config.openai.api_key
    if (Is-Blank $apiKey) {
        throw 'OpenAI APIキーが未設定です。'
    }
    $instruction = Get-Prompt $Mode
    $messages = Build-Messages $instruction $Context $Text
    $body = @{ model = $Config.openai.model; input = $messages } | ConvertTo-Json -Depth 6
    $headers = @{ Authorization = "Bearer $apiKey" }
    try {
        $response = Invoke-RestMethod -Method Post -Uri 'https://api.openai.com/v1/responses' -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 100
    } catch {
        throw "OpenAI APIエラー: $($_.Exception.Message)"
    }
    $content = Get-OpenAIResponseText $response
    if (Is-Blank $content) {
        throw 'OpenAI APIの応答が空でした。'
    }
    return $content.Trim()
}

function Invoke-Ollama {
    param(
        [string]$Text,
        [string]$Mode,
        [string]$Context,
        $Config
    )
    $model = $Config.ollama.model
    if (Is-Blank $model) {
        throw 'Ollamaのモデルが未設定です。'
    }
    $baseUrl = $Config.ollama.base_url
    if (Is-Blank $baseUrl) {
        $baseUrl = 'http://localhost:11434'
    }
    $baseUrl = $baseUrl.TrimEnd('/')
    $instruction = Get-Prompt $Mode
    $messages = Build-Messages $instruction $Context $Text
    $payload = @{ model = $model; stream = $false; messages = $messages } | ConvertTo-Json -Depth 6
    try {
        $response = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/chat" -ContentType 'application/json' -Body $payload -TimeoutSec 100
    } catch {
        throw "Ollama APIに接続できませんでした ($($_.Exception.Message))。"
    }
    $content = $null
    if ($response.PSObject.Properties['message']) {
        $content = $response.message.content
    }
    if (Is-Blank $content -and $response.PSObject.Properties['response']) {
        $content = $response.response
    }
    if (Is-Blank $content) {
        throw 'Ollama APIの応答が空でした。'
    }
    return $content.Trim()
}

function Generate-Support {
    param(
        [string]$Text,
        [string]$Mode,
        [string]$Context
    )
    $provider = Resolve-AiProvider $script:Config.ai_provider
    if ($null -eq $provider) {
        return New-ErrorSupport @('AI providerはopenai/ollamaのいずれかに設定してください。')
    }
    try {
        if ($provider -eq 'openai') {
            $content = Invoke-OpenAI $Text $Mode $Context $script:Config
            return New-SupportResult $content 'openai'
        }
        $content = Invoke-Ollama $Text $Mode $Context $script:Config
        return New-SupportResult $content 'ollama'
    } catch {
        return New-ErrorSupport @($_.Exception.Message)
    }
}

function Format-Timestamp {
    param([string]$Ts)
    try {
        $seconds = [double]$Ts
        $ms = [long]($seconds * 1000)
        $dt = [DateTimeOffset]::FromUnixTimeMilliseconds($ms).UtcDateTime
        return $dt.ToString('yyyy-MM-dd HH:mm:ss')
    } catch {
        return $Ts
    }
}

function Format-ListPreview {
    param([string]$Text)
    $preview = ($Text -replace "\r?\n", ' ').Trim()
    if ($preview.Length -gt 120) {
        return $preview.Substring(0, 120) + '...'
    }
    return $preview
}

function Invoke-SlackSearchMessages {
    param(
        [string]$Token,
        [string]$Query,
        [int]$Limit = 10
    )
    if (Is-Blank $Query) {
        throw '検索クエリが空です。'
    }
    $body = @{ query = $Query; sort = 'timestamp'; count = $Limit }
    try {
        $resp = Invoke-RestMethod -Method Post -Uri 'https://slack.com/api/search.messages' -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/x-www-form-urlencoded' -Body $body -TimeoutSec 30
    } catch {
        throw "Slack検索に失敗しました: $($_.Exception.Message)"
    }
    if (-not $resp.ok) {
        throw "Slack検索に失敗しました: $($resp.error)"
    }
    $matches = @()
    if ($resp.messages -and $resp.messages.matches) {
        $matches = $resp.messages.matches
    }
    $results = @()
    foreach ($match in $matches) {
        $channel = $match.channel
        $channelId = if ($channel) { $channel.id } else { $null }
        if (Is-Blank $channelId) {
            continue
        }
        $userId = $match.user
        $text = $match.text
        if ($null -eq $text) {
            $text = ''
        } else {
            $text = $text.ToString()
        }
        $text = $text.Trim()
        if (Is-Blank $userId -or Is-Blank $text) {
            continue
        }
        $channelName = if ($channel.name) { $channel.name } else { $channelId }
        $userName = if ($match.username) { $match.username } else { $userId }
        $ts = if ($match.ts) { $match.ts } elseif ($match.timestamp) { $match.timestamp } else { '0' }
        $threadTs = if ($match.thread_ts) { $match.thread_ts } elseif ($match.ts) { $match.ts } elseif ($match.timestamp) { $match.timestamp } else { '0' }
        $results += [pscustomobject]@{
            channel_id   = $channelId
            channel_name = $channelName
            user_id      = $userId
            user_name    = $userName
            text         = $text
            ts           = $ts
            permalink    = $match.permalink
            thread_ts    = $threadTs
        }
    }
    return $results
}

function Invoke-SlackThreadMessages {
    param(
        [string]$Token,
        [string]$ChannelId,
        [string]$ThreadTs,
        [string]$ChannelName
    )
    $messages = @()
    $cursor = $null
    while ($true) {
        $body = @{ channel = $ChannelId; ts = $ThreadTs; limit = 200 }
        if (-not (Is-Blank $cursor)) {
            $body.cursor = $cursor
        }
        try {
            $resp = Invoke-RestMethod -Method Post -Uri 'https://slack.com/api/conversations.replies' -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/x-www-form-urlencoded' -Body $body -TimeoutSec 30
        } catch {
            throw "スレッド取得に失敗しました: $($_.Exception.Message)"
        }
        if (-not $resp.ok) {
            throw "スレッド取得に失敗しました: $($resp.error)"
        }
        foreach ($message in ($resp.messages | ForEach-Object { $_ })) {
            $text = $message.text
            if ($null -eq $text) {
                $text = ''
            } else {
                $text = $text.ToString()
            }
            $text = $text.Trim()
            if (Is-Blank $text) {
                continue
            }
            $userId = if ($message.user) { $message.user } elseif ($message.bot_id) { $message.bot_id } else { 'unknown' }
            $userName = if ($message.username) { $message.username } elseif ($message.bot_profile -and $message.bot_profile.name) { $message.bot_profile.name } else { $userId }
            $ts = if ($message.ts) { $message.ts } else { '0' }
            $messages += [pscustomobject]@{
                channel_id   = $ChannelId
                channel_name = $ChannelName
                user_id      = $userId
                user_name    = $userName
                text         = $text
                ts           = $ts
                thread_ts    = if ($message.thread_ts) { $message.thread_ts } else { $ts }
            }
        }
        $nextCursor = $null
        if ($resp.response_metadata -and $resp.response_metadata.next_cursor) {
            $nextCursor = $resp.response_metadata.next_cursor
        }
        if (Is-Blank $nextCursor) {
            break
        }
        $cursor = $nextCursor
    }
    return $messages
}

function Format-ThreadMessages {
    param($Messages)
    $lines = @()
    foreach ($message in $Messages) {
        $timestamp = Format-Timestamp $message.ts
        $lines += "[$timestamp] $($message.user_name): $($message.text)"
    }
    return ($lines -join "`n")
}

function Set-Status {
    param([string]$Text)
    $script:StatusLabel.Text = $Text
    [System.Windows.Forms.Application]::DoEvents()
}

function Clear-Detail {
    $script:SelectedIndex = $null
    $script:DetailTextBox.Text = ''
    $script:OutputTextBox.Text = ''
}

function Render-MessageList {
    $script:ListView.Items.Clear()
    foreach ($msg in $script:Messages) {
        $preview = Format-ListPreview $msg.text
        $item = New-Object System.Windows.Forms.ListViewItem($msg.user_name)
        [void]$item.SubItems.Add($msg.channel_name)
        [void]$item.SubItems.Add($preview)
        $script:ListView.Items.Add($item) | Out-Null
    }
    Clear-Detail
    Adjust-ListColumns
}

function Adjust-ListColumns {
    if (-not $script:ListView) {
        return
    }
    if ($script:ListView.Columns.Count -lt 3) {
        return
    }
    $total = $script:ListView.ClientSize.Width
    $first = 140
    $second = 120
    $third = [Math]::Max(120, $total - $first - $second - 6)
    $script:ListView.Columns[0].Width = $first
    $script:ListView.Columns[1].Width = $second
    $script:ListView.Columns[2].Width = $third
}

function Refresh-Messages {
    if (Is-Blank $script:SlackToken) {
        Set-Status 'Slackトークンが未設定です。'
        return
    }
    $query = $script:QueryTextBox.Text.Trim()
    Set-Status 'Slackから取得中...'
    try {
        $script:Messages = Invoke-SlackSearchMessages -Token $script:SlackToken -Query $query -Limit 10
    } catch {
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, '取得に失敗しました', 'OK', 'Error') | Out-Null
        Set-Status '取得に失敗しました'
        return
    }
    Render-MessageList
    Set-Status "$($script:Messages.Count)件の検索結果を表示中"
}

function Show-MessageDetail {
    if ($script:ListView.SelectedIndices.Count -eq 0) {
        return
    }
    $index = $script:ListView.SelectedIndices[0]
    $script:SelectedIndex = $index
    $msg = $script:Messages[$index]
    $detail = "送信者: $($msg.user_name)`nチャンネル: $($msg.channel_name)`n日時: $(Format-Timestamp $msg.ts) (UTC)`n$($msg.text)"
    if (-not (Is-Blank $msg.permalink)) {
        $detail += "`n`nPermalink: $($msg.permalink)"
    }
    $script:DetailTextBox.Text = $detail
    $script:OutputTextBox.Text = ''
}

function Generate-SupportHandler {
    if ($null -eq $script:SelectedIndex) {
        [System.Windows.Forms.MessageBox]::Show('対象メッセージを選択してください。', '選択してください', 'OK', 'Information') | Out-Null
        return
    }
    $msg = $script:Messages[$script:SelectedIndex]
    $mode = if ($script:ReplyRadio.Checked) { 'reply' } elseif ($script:SummaryRadio.Checked) { 'summary' } else { 'todo' }
    $context = "$($msg.user_name) / $($msg.channel_name)"
    Set-Status 'スレッドを取得中...'
    try {
        $threadMessages = Invoke-SlackThreadMessages -Token $script:SlackToken -ChannelId $msg.channel_id -ThreadTs $msg.thread_ts -ChannelName $msg.channel_name
    } catch {
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'スレッド取得に失敗しました', 'OK', 'Error') | Out-Null
        Set-Status 'スレッド取得に失敗しました'
        return
    }
    if (-not $threadMessages -or $threadMessages.Count -eq 0) {
        Set-Status 'スレッド取得に失敗しました'
        return
    }
    $threadText = Format-ThreadMessages $threadMessages
    Set-Status 'AIサポートを生成中...'
    $result = Generate-Support -Text $threadText -Mode $mode -Context $context
    $script:OutputTextBox.Text = $result.Content
    if ($result.Model -eq 'error') {
        Set-Status 'AIサポートの生成に失敗しました'
    } else {
        Set-Status 'AIサポートを表示しました'
    }
}

$script:Config = Get-Config
$script:SlackToken = if (-not (Is-Blank $script:Config.slack.user_token)) { $script:Config.slack.user_token } else { $script:Config.slack.token }
$script:Messages = @()
$script:SelectedIndex = $null

[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Slack Agent'
$form.Size = New-Object System.Drawing.Size(980, 640)
$form.StartPosition = 'CenterScreen'
$form.Padding = New-Object System.Windows.Forms.Padding(12)

$header = New-Object System.Windows.Forms.TableLayoutPanel
$header.ColumnCount = 5
$header.RowCount = 1
$header.Dock = 'Top'
$header.AutoSize = $true
$header.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
$header.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Absolute, 380)))
$header.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
$header.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
$header.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))

$label = New-Object System.Windows.Forms.Label
$label.Text = '検索クエリ'
$label.AutoSize = $true
$label.Anchor = 'Left'

$script:QueryTextBox = New-Object System.Windows.Forms.TextBox
$script:QueryTextBox.Width = 360
$script:QueryTextBox.Text = $script:Config.slack.search_query

$searchButton = New-Object System.Windows.Forms.Button
$searchButton.Text = '検索'
$searchButton.AutoSize = $true

$refreshButton = New-Object System.Windows.Forms.Button
$refreshButton.Text = '更新'
$refreshButton.AutoSize = $true

$header.Controls.Add($label, 0, 0)
$header.Controls.Add($script:QueryTextBox, 1, 0)
$header.Controls.Add($searchButton, 2, 0)
$header.Controls.Add((New-Object System.Windows.Forms.Label), 3, 0)
$header.Controls.Add($refreshButton, 4, 0)

$split = New-Object System.Windows.Forms.SplitContainer
$split.Dock = 'Fill'
$split.Orientation = 'Vertical'
$split.SplitterDistance = 340

$script:ListView = New-Object System.Windows.Forms.ListView
$script:ListView.View = 'Details'
$script:ListView.FullRowSelect = $true
$script:ListView.MultiSelect = $false
$script:ListView.HideSelection = $false
$script:ListView.Dock = 'Fill'
[void]$script:ListView.Columns.Add('From', 140)
[void]$script:ListView.Columns.Add('Channel', 120)
[void]$script:ListView.Columns.Add('Message', 320)

$split.Panel1.Controls.Add($script:ListView)

$rightLayout = New-Object System.Windows.Forms.TableLayoutPanel
$rightLayout.RowCount = 3
$rightLayout.ColumnCount = 1
$rightLayout.Dock = 'Fill'
$rightLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 40)))
$rightLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 70)))
$rightLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 60)))

$script:DetailTextBox = New-Object System.Windows.Forms.TextBox
$script:DetailTextBox.Multiline = $true
$script:DetailTextBox.ScrollBars = 'Vertical'
$script:DetailTextBox.ReadOnly = $true
$script:DetailTextBox.Dock = 'Fill'

$group = New-Object System.Windows.Forms.GroupBox
$group.Text = 'AIサポート'
$group.Dock = 'Fill'

$groupLayout = New-Object System.Windows.Forms.TableLayoutPanel
$groupLayout.ColumnCount = 4
$groupLayout.RowCount = 1
$groupLayout.Dock = 'Fill'
$groupLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
$groupLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
$groupLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
$groupLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))

$script:ReplyRadio = New-Object System.Windows.Forms.RadioButton
$script:ReplyRadio.Text = '返信を考える'
$script:ReplyRadio.Checked = $true
$script:ReplyRadio.AutoSize = $true

$script:SummaryRadio = New-Object System.Windows.Forms.RadioButton
$script:SummaryRadio.Text = '連絡を要約する'
$script:SummaryRadio.AutoSize = $true

$script:TodoRadio = New-Object System.Windows.Forms.RadioButton
$script:TodoRadio.Text = 'TODOを具体化'
$script:TodoRadio.AutoSize = $true

$generateButton = New-Object System.Windows.Forms.Button
$generateButton.Text = 'AIサポートを生成'
$generateButton.AutoSize = $true
$generateButton.Anchor = 'Right'

$groupLayout.Controls.Add($script:ReplyRadio, 0, 0)
$groupLayout.Controls.Add($script:SummaryRadio, 1, 0)
$groupLayout.Controls.Add($script:TodoRadio, 2, 0)
$groupLayout.Controls.Add($generateButton, 3, 0)

$group.Controls.Add($groupLayout)

$script:OutputTextBox = New-Object System.Windows.Forms.TextBox
$script:OutputTextBox.Multiline = $true
$script:OutputTextBox.ScrollBars = 'Vertical'
$script:OutputTextBox.ReadOnly = $true
$script:OutputTextBox.Dock = 'Fill'

$rightLayout.Controls.Add($script:DetailTextBox, 0, 0)
$rightLayout.Controls.Add($group, 0, 1)
$rightLayout.Controls.Add($script:OutputTextBox, 0, 2)

$split.Panel2.Controls.Add($rightLayout)

$statusStrip = New-Object System.Windows.Forms.StatusStrip
$script:StatusLabel = New-Object System.Windows.Forms.ToolStripStatusLabel
$script:StatusLabel.Text = '準備完了'
[void]$statusStrip.Items.Add($script:StatusLabel)

$form.Controls.Add($split)
$form.Controls.Add($statusStrip)
$form.Controls.Add($header)

$searchButton.Add_Click({ Refresh-Messages })
$refreshButton.Add_Click({ Refresh-Messages })
$script:ListView.Add_SelectedIndexChanged({ Show-MessageDetail })
$generateButton.Add_Click({ Generate-SupportHandler })
$form.Add_Shown({
    if (Is-Blank $script:SlackToken) {
        [System.Windows.Forms.MessageBox]::Show('config/config.yml に Slack トークンを設定してください。', 'Slackトークンが未設定です', 'OK', 'Warning') | Out-Null
    }
    Refresh-Messages
})
$form.Add_Resize({ Adjust-ListColumns })

[System.Windows.Forms.Application]::Run($form)
