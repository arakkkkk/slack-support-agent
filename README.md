## 要件
* Linux/Windowsで動作する
* デスクトップアプリとして使える

## 設計
* Pythonで実装
* Slack APIを利用
* 設定は `config/config.yml` に集約

## できること
* 直近のSlackの連絡に対して、AIサポートが受けられる
    * 返信を考える
    * 連絡を要約する
    * TODOの具体化

## 機能
1. 検索クエリに一致するSlackメッセージを10件リストする（例: `from:me`）
2. メッセージと、AIサポートの種類を選択することで適切なAIサポートを受けられる



https://api.slack.com/apps/A05SV98A9JB
