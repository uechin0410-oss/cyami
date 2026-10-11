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
pip install -e '.[dev]'
export ANTHROPIC_API_KEY=sk-ant-...   # Claude API キー
```

## 使い方

```bash
support-agent            # 対話開始
support-agent -v         # ツール呼び出しとコストも表示
support-agent --model claude-sonnet-5-5   # モデルを変更(環境変数 SUPPORT_AGENT_MODEL でも可)
```

既定のモデルは `claude-opus-5-5` です。

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
- Slack / LINE / Web への組み込み: `support_agent/cli.py` の `ClaudeSDKClient` の使い方を参考に、入出力部分を差し替える

## テスト

```bash
pytest
```
