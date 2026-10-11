"""エージェントが使うカスタムツール(インプロセス MCP サーバー)。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import SdkMcpTool, ToolAnnotations, create_sdk_mcp_server, tool

from .knowledge import FaqEntry, load_faq, search_faq

SERVER_NAME = "support"


def _text(text: str, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["is_error"] = True
    return result


def _format_entry(entry: FaqEntry) -> str:
    return f"[{entry.id}] Q: {entry.question}\nA: {entry.answer}"


def build_tools(
    knowledge_dir: Path, tickets_path: Path, customer_id: str | None = None
) -> list[SdkMcpTool[Any]]:
    """FAQ 検索とエスカレーション用のツールを作る。

    customer_id はチャネル側で識別できる顧客 ID(LINE のユーザー ID など)で、チケットに記録される。
    """
    entries = load_faq(knowledge_dir)

    @tool(
        "search_faq",
        "FAQ ナレッジベースをキーワードで検索し、関連する質問と回答を最大 limit 件返す。"
        "回答する前に必ずこのツールで根拠を確認すること。",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "検索キーワードや問い合わせ文"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
            },
            "required": ["query"],
        },
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def search_faq_tool(args: dict[str, Any]) -> dict[str, Any]:
        hits = search_faq(entries, args["query"], args.get("limit", 3))
        if not hits:
            return _text("該当する FAQ は見つかりませんでした。")
        return _text("\n\n".join(_format_entry(e) for e in hits))

    @tool(
        "list_faq_categories",
        "FAQ のカテゴリ一覧と各カテゴリの質問タイトルを返す。",
        {},
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def list_categories_tool(args: dict[str, Any]) -> dict[str, Any]:
        lines: list[str] = []
        for category in sorted({e.category for e in entries}):
            lines.append(f"# {category}")
            lines.extend(f"- [{e.id}] {e.question}" for e in entries if e.category == category)
        return _text("\n".join(lines) or "FAQ が登録されていません。")

    @tool(
        "create_ticket",
        "FAQ で解決できない問い合わせ、返金・契約変更・苦情など人の判断が必要な案件を"
        "担当者へエスカレーションするチケットを作成する。",
        {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "問い合わせ内容の要約"},
                "priority": {"type": "string", "enum": ["low", "normal", "high"]},
                "customer_contact": {
                    "type": "string",
                    "description": "顧客の連絡先(聞き取れた場合のみ)",
                },
            },
            "required": ["summary", "priority"],
        },
    )
    async def create_ticket_tool(args: dict[str, Any]) -> dict[str, Any]:
        ticket = {
            "id": f"T-{uuid.uuid4().hex[:8].upper()}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "summary": args["summary"],
            "priority": args["priority"],
            "customer_contact": args.get("customer_contact", ""),
            "customer_id": customer_id or "",
        }
        tickets_path.parent.mkdir(parents=True, exist_ok=True)
        with tickets_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ticket, ensure_ascii=False) + "\n")
        return _text(f"チケット {ticket['id']} を作成しました(優先度: {ticket['priority']})。")

    return [search_faq_tool, list_categories_tool, create_ticket_tool]


def build_support_server(
    knowledge_dir: Path, tickets_path: Path, customer_id: str | None = None
):
    tools = build_tools(knowledge_dir, tickets_path, customer_id)
    server = create_sdk_mcp_server(name=SERVER_NAME, version="0.1.0", tools=tools)
    tool_names = [f"mcp__{SERVER_NAME}__{t.name}" for t in tools]
    return server, tool_names
