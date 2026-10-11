from support_agent.sessions import SessionStore


def test_session_store_roundtrip_and_ttl(tmp_path):
    store = SessionStore(tmp_path / "s.json", ttl_seconds=3600)
    assert store.get("u1") is None
    store.set("u1", "abc")
    assert store.get("u1") == "abc"
    store.clear("u1")
    assert store.get("u1") is None

    expired = SessionStore(tmp_path / "s.json", ttl_seconds=-1)
    expired.set("u2", "def")
    assert expired.get("u2") is None
