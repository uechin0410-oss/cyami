import json
from pathlib import Path

import anyio

from support_agent.tools import build_tools

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"


def _call(tools, name, args):
    tool = next(t for t in tools if t.name == name)
    result = anyio.run(tool.handler, args)
    return result["content"][0]["text"]


def test_search_faq_tool():
    tools = build_tools(KNOWLEDGE_DIR, Path("unused.jsonl"))
    assert "PDF" in _call(tools, "search_faq", {"query": "領収書"})
    assert "見つかりません" in _call(tools, "search_faq", {"query": "zzz"})


def test_create_ticket_tool(tmp_path):
    tickets = tmp_path / "tickets.jsonl"
    tools = build_tools(KNOWLEDGE_DIR, tickets)
    assert "チケット T-" in _call(tools, "create_ticket", {"summary": "返金希望", "priority": "high"})
    ticket = json.loads(tickets.read_text(encoding="utf-8"))
    assert ticket["summary"] == "返金希望"
    assert ticket["priority"] == "high"
