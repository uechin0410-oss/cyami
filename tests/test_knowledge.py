from pathlib import Path

from support_agent.knowledge import load_faq, search_faq

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"


def test_load_faq_splits_sections():
    entries = load_faq(KNOWLEDGE_DIR)
    assert len(entries) == 8
    first = next(e for e in entries if e.id == "account-1")
    assert first.question == "パスワードを忘れました"
    assert "24 時間" in first.answer


def test_search_faq_ranks_relevant_entry_first():
    entries = load_faq(KNOWLEDGE_DIR)
    hits = search_faq(entries, "パスワードがわからなくてログインできない")
    assert hits[0].id == "account-1"


def test_search_faq_returns_empty_for_unrelated_query():
    entries = load_faq(KNOWLEDGE_DIR)
    assert search_faq(entries, "") == []
