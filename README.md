# cyami 問い合わせ対応エージェント

[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk) (Python) で作った、カスタマーサポートの問い合わせ対応 AI エージェントです。

- `knowledge/` の FAQ を検索し、根拠に基づいて回答します
- FAQ で解決できない案件や、返金・契約変更・苦情など人の判断が必要な案件は、チケットを作って担当者にエスカレーションします(`data/tickets.jsonl` に保存)
- Bash やファイル操作などの組み込みツールは無効にし、下記のカスタムツールだけを使います

| ツール | 役割 |
| --- | --- |
| `search_faq` | FAQ をキーワード検索(日本語対応の文字 2-gram 類似度) |
| `list_faq_categories` | FAQ のカテゴリと質問の一覧 |
| `create_ticket` | 担当者へのエスカレーションチケット作成 |

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[line,dev]'
export ANTHROPIC_API_KEY=sk-ant-...   # Claude API キー
```

## 使い方

```bash
support-agent            # 対話開始
support-agent -v         # ツール呼び出しとコストも表示
support-agent --model claude-sonnet-5-5   # モデルを変更(環境変数 SUPPORT_AGENT_MODEL でも可)
```

既定のモデルは `claude-opus-5-5` です。

## LINE で使う

LINE 公式アカウントに届いたメッセージにエージェントが自動で返信します(`support_agent/line_bot.py`)。

- 1 対 1 のトークに対応(グループトークでは反応しません)
- ユーザーごとに会話を記憶し、続けて質問すると文脈を引き継ぎます。最後のやり取りから 24 時間(`SESSION_TTL_HOURS`)経つと新しい会話になります
- 「リセット」と送ると会話を最初からやり直します
- 回答を作っている間は、トーク画面に読み込み中のアニメーションを表示します
- 回答に 1 分以上かかって応答トークンが失効した場合は、プッシュメッセージで送ります(プッシュは月の無料メッセージ数に含まれます)
- エスカレーションのチケットには LINE のユーザー ID(`line:U...`)が記録されるので、担当者は LINE で折り返し連絡できます

### 1. LINE 側の準備

1. [LINE Developers コンソール](https://developers.line.biz/console/)でプロバイダーと **Messaging API チャネル**を作成する
2. 「チャネル基本設定」の **チャネルシークレット** を控える
3. 「Messaging API 設定」で **チャネルアクセストークン(長期)** を発行して控える
4. 同じ画面で「応答メッセージ」と「あいさつメッセージ」をオフにする(LINE Official Account Manager の自動応答と二重に返信しないため)

### 2. サーバーを起動する

```bash
pip install -e '.[line]'
export ANTHROPIC_API_KEY=sk-ant-...
export LINE_CHANNEL_SECRET=...
export LINE_CHANNEL_ACCESS_TOKEN=...
uvicorn support_agent.line_bot:app --host 0.0.0.0 --port 8000
```

LINE から届くには HTTPS の公開 URL が必要です。手元で試すときは [ngrok](https://ngrok.com/) などで `ngrok http 8000` として公開 URL を作ってください。

### 3. Webhook を登録する

「Messaging API 設定」の **Webhook URL** に `https://<公開URL>/callback` を入力し、「検証」で成功を確認してから **Webhook の利用** をオンにします。あとは公式アカウントを友だち追加して話しかけるだけです。

### 本番での運用

`Dockerfile` を用意しています。Cloud Run、Render、Fly.io などのコンテナ実行サービスにデプロイできます。

```bash
docker build -t cyami-line .
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY -e LINE_CHANNEL_SECRET -e LINE_CHANNEL_ACCESS_TOKEN \
  -v cyami-data:/app/data -v cyami-claude:/root/.claude \
  cyami-line
```

会話の記録は `/app/data`(ユーザーとセッションの対応表、チケット)と `/root/.claude`(会話履歴)にファイルとして保存されます。

- この 2 か所は永続ボリュームにしてください。そうしないと、再起動するたびに会話の記憶が消えます
- インスタンスは 1 台で動かしてください。複数台に分けると、会話の記憶を台の間で共有できません

| 環境変数 | 内容 | 既定値 |
| --- | --- | --- |
| `LINE_CHANNEL_SECRET` | チャネルシークレット | (必須) |
| `LINE_CHANNEL_ACCESS_TOKEN` | チャネルアクセストークン | (必須) |
| `SESSION_TTL_HOURS` | 会話を引き継ぐ時間 | `24` |
| `KNOWLEDGE_DIR` | FAQ のディレクトリ | `./knowledge` |
| `DATA_DIR` | セッション・チケットの保存先 | `./data` |
| `SUPPORT_AGENT_MODEL` | モデル ID | `claude-opus-5-5` |

## FAQ の追加

`knowledge/` に Markdown ファイルを置くと、ファイル名がカテゴリ、`## 見出し` が質問、その下の本文が回答になります。

```markdown
# 配送

## 送料はいくらですか?
全国一律 500 円です。5,000 円以上のご注文で無料になります。
```

## カスタマイズのポイント

- 応対方針: `support_agent/agent.py` の `SYSTEM_PROMPT`
- ツールの追加(注文状況の照会、社内 API 連携など): `support_agent/tools.py` に `@tool` で関数を追加し、`build_tools` の戻り値に加える
- LINE 向けの話し方: `support_agent/line_bot.py` の `LINE_INSTRUCTIONS`
- 他のチャネル(Slack・Web など)への組み込み: `support_agent/line_bot.py` と同じように `agent.ask()` を呼ぶ

## テスト

```bash
pytest
```
