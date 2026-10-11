"""エージェントの設定(システムプロンプト・モデル・ツール)。"""

from __future__ import annotations

import os
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions

from .tools import SERVER_NAME, build_support_server

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """\
あなたはカスタマーサポート窓口の問い合わせ対応担当です。お客様からの質問に、丁寧で簡潔な日本語で回答してください。

対応の手順:
1. 問い合わせ内容を把握し、search_faq ツールで関連する FAQ を検索する。言い換えた語で再検索してもよい。
2. FAQ に根拠がある場合は、その内容に基づいて回答する。FAQ に書かれていない料金・期限・条件を推測で答えない。
3. FAQ で解決できない場合や、返金・契約変更・苦情・個別のアカウント調査など担当者の判断が必要な場合は、
   create_ticket ツールで担当者へエスカレーションし、チケット番号と「担当者から折り返し連絡する」旨を伝える。
4. 質問が曖昧なときは、検索の前に確認の質問を 1 つだけ返す。

回答は結論から先に書き、必要なら手順を箇条書きにする。社内の FAQ ID やツール名はお客様に見せない。
"""


def build_options(
    knowledge_dir: Path | None = None,
    tickets_path: Path | None = None,
    model: str | None = None,
) -> ClaudeAgentOptions:
    server, tool_names = build_support_server(
        knowledge_dir or PROJECT_ROOT / "knowledge",
        tickets_path or PROJECT_ROOT / "data" / "tickets.jsonl",
    )
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=model or os.environ.get("SUPPORT_AGENT_MODEL", DEFAULT_MODEL),
        # 組み込みツール(Bash やファイル操作)は使わせず、カスタムツールだけを許可する
        tools=[],
        mcp_servers={SERVER_NAME: server},
        allowed_tools=tool_names,
        strict_mcp_config=True,
        permission_mode="dontAsk",
        max_turns=10,
    )
