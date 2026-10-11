"""エージェントの設定(システムプロンプト・モデル・ツール)と 1 往復分の実行。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from .tools import SERVER_NAME, build_support_server

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_DIR", PROJECT_ROOT / "knowledge"))
DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
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
    *,
    customer_id: str | None = None,
    extra_instructions: str | None = None,
    resume: str | None = None,
) -> ClaudeAgentOptions:
    server, tool_names = build_support_server(
        knowledge_dir or KNOWLEDGE_DIR,
        tickets_path or DATA_DIR / "tickets.jsonl",
        customer_id,
    )
    system_prompt = SYSTEM_PROMPT
    if extra_instructions:
        system_prompt += "\n" + extra_instructions
    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model or os.environ.get("SUPPORT_AGENT_MODEL", DEFAULT_MODEL),
        # 組み込みツール(Bash やファイル操作)は使わせず、カスタムツールだけを許可する
        tools=[],
        mcp_servers={SERVER_NAME: server},
        allowed_tools=tool_names,
        strict_mcp_config=True,
        permission_mode="dontAsk",
        max_turns=10,
        resume=resume,
    )


@dataclass
class AgentReply:
    text: str
    session_id: str | None


async def ask(prompt: str, options: ClaudeAgentOptions) -> AgentReply:
    """1 通の問い合わせに回答する。options.resume を渡すと前回の会話の続きになる。"""
    texts: list[str] = []
    session_id: str | None = None
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        # ツール呼び出し前の前置き(「確認します」など)は回答に含めない
                        texts.clear()
                    elif isinstance(block, TextBlock):
                        texts.append(block.text)
            elif isinstance(message, ResultMessage):
                session_id = message.session_id
                if message.is_error:
                    raise RuntimeError(f"agent run failed: {message.subtype}")
    return AgentReply(text="\n\n".join(t.strip() for t in texts if t.strip()), session_id=session_id)
