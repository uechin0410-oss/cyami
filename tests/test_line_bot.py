import base64
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from linebot.v3.messaging import ApiException

from support_agent.agent import AgentReply
from support_agent.line_bot import (
    ERROR_REPLY,
    MAX_MESSAGES,
    MAX_TEXT_LENGTH,
    NON_TEXT_REPLY,
    RESET_REPLY,
    Settings,
    create_app,
    split_text,
)

SECRET = "test-secret"
USER_ID = "U1234567890abcdef"


class FakeMessagingApi:
    def __init__(self, reply_fails: bool = False):
        self.reply_fails = reply_fails
        self.replies = []
        self.pushes = []
        self.loading = []

    async def reply_message(self, request):
        if self.reply_fails:
            raise ApiException(status=400, reason="Invalid reply token")
        self.replies.append(request)

    async def push_message(self, request):
        self.pushes.append(request)

    async def show_loading_animation(self, request):
        self.loading.append(request)


class FakeResponder:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = []

    async def __call__(self, user_id, text, session_id):
        self.calls.append((user_id, text, session_id))
        if self.fail:
            raise RuntimeError("boom")
        return AgentReply(text=f"回答: {text}", session_id=f"session-{len(self.calls)}")


def _event(message):
    return {
        "type": "message",
        "mode": "active",
        "timestamp": 1700000000000,
        "source": {"type": "user", "userId": USER_ID},
        "webhookEventId": "01HXXXXXXXXXXXXXXXXXXXXXXX",
        "deliveryContext": {"isRedelivery": False},
        "replyToken": "reply-token",
        "message": message,
    }


def _text_event(text):
    return _event({"type": "text", "id": "1", "quoteToken": "q", "text": text})


def _post(client, events, secret=SECRET):
    body = json.dumps({"destination": "Uxxx", "events": events})
    signature = base64.b64encode(
        hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    ).decode()
    return client.post(
        "/callback",
        content=body,
        headers={"X-Line-Signature": signature, "Content-Type": "application/json"},
    )


@pytest.fixture
def make_client(tmp_path):
    def _make(api=None, responder=None):
        api = api or FakeMessagingApi()
        responder = responder or FakeResponder()
        settings = Settings(SECRET, "token", tmp_path / "sessions.json", 3600)
        client = TestClient(create_app(settings, api, responder))
        return client, api, responder

    return _make


def _texts(request):
    return [m.text for m in request.messages]


def test_replies_with_agent_answer_and_keeps_session(make_client):
    client, api, responder = make_client()
    with client:
        assert _post(client, [_text_event("領収書がほしい")]).status_code == 200
        assert _post(client, [_text_event("宛名は?")]).status_code == 200

    assert _texts(api.replies[0]) == ["回答: 領収書がほしい"]
    assert api.loading[0].chat_id == USER_ID
    # 2 通目は 1 通目のセッションを引き継ぐ
    assert responder.calls == [
        (USER_ID, "領収書がほしい", None),
        (USER_ID, "宛名は?", "session-1"),
    ]


def test_reset_clears_session(make_client):
    client, api, responder = make_client()
    with client:
        _post(client, [_text_event("こんにちは")])
        _post(client, [_text_event("リセット")])
        _post(client, [_text_event("もう一度")])

    assert _texts(api.replies[1]) == [RESET_REPLY]
    assert responder.calls[-1] == (USER_ID, "もう一度", None)


def test_rejects_invalid_signature(make_client):
    client, api, _ = make_client()
    with client:
        assert _post(client, [_text_event("x")], secret="wrong").status_code == 400
    assert api.replies == []


def test_non_text_message(make_client):
    client, api, responder = make_client()
    with client:
        _post(client, [_event({"type": "sticker", "id": "1", "quoteToken": "q",
                               "packageId": "1", "stickerId": "1", "stickerResourceType": "STATIC"})])
    assert _texts(api.replies[0]) == [NON_TEXT_REPLY]
    assert responder.calls == []


def test_agent_error_sends_apology(make_client):
    client, api, _ = make_client(responder=FakeResponder(fail=True))
    with client:
        _post(client, [_text_event("x")])
    assert _texts(api.replies[0]) == [ERROR_REPLY]


def test_falls_back_to_push_when_reply_token_expired(make_client):
    client, api, _ = make_client(api=FakeMessagingApi(reply_fails=True))
    with client:
        _post(client, [_text_event("x")])
    assert api.pushes[0].to == USER_ID
    assert _texts(api.pushes[0]) == ["回答: x"]


def test_split_text_respects_line_limits():
    assert split_text("短い") == ["短い"]
    chunks = split_text("あ" * (MAX_TEXT_LENGTH * 7))
    assert len(chunks) == MAX_MESSAGES
    assert all(len(c) <= MAX_TEXT_LENGTH for c in chunks)
