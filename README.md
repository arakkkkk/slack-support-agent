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

## exeビルド（PyInstaller）
Windows / Linux はそれぞれのOS上でビルドしてください（クロスビルド非対応）。

### 前提
```
pip install -r requirements.txt
pip install pyinstaller
```

### Windows
```
python -m PyInstaller --name slack-agent-windows --onefile --windowed --distpath ./ --workpath %TEMP%\\slack-agent-build --specpath %TEMP%\\slack-agent-spec app.py
```

### Linux
```
pyinstaller --name slack-agent-linux --onefile --distpath ./ --workpath /tmp/slack-agent-build --specpath /tmp/slack-agent-spec app.py
```

ビルド成果物は `dist/windows` または `dist/linux` に生成されます（ビルド用の一時ファイルはOSの一時ディレクトリに出力）。  
※ `config/config.yml` にはトークン情報が入るため、配布時は扱いに注意してください。



https://api.slack.com/apps/A05SV98A9JB
