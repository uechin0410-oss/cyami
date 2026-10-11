"""LINE Messaging API の Webhook サーバー。

LINE からのメッセージを受け取り、問い合わせ対応エージェントの回答を返信する。
ユーザーごとに会話セッションを保存するので、続けて質問すると文脈を引き継いで回答する。

起動:
    uvicorn support_agent.line_bot:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiException,
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    PushMessageRequest,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, UserSource

from .agent import DATA_DIR, AgentReply, ask, build_options
from .sessions import SessionStore

logger = logging.getLogger(__name__)

LINE_INSTRUCTIONS = """\
この会話は LINE のトーク画面で行われる。LINE は Markdown を表示できないため、
見出し・太字・表などの記法は使わず、プレーンテキストで書くこと。箇条書きは「・」を使う。
スマートフォンで読みやすいよう、回答は 300 文字程度を目安に短くまとめる。
"""

RESET_WORDS = {"リセット", "最初から", "reset"}
RESET_REPLY = "会話をリセットしました。ご用件をお送りください。"
NON_TEXT_REPLY = "恐れ入りますが、お問い合わせ内容は文字でお送りください。"
ERROR_REPLY = (
    "申し訳ございません。ただいま回答を作成できませんでした。"
    "お手数ですが、少し時間をおいて再度お送りください。"
)

# LINE の制限: テキスト 1 通 5000 文字、1 回の返信で 5 通まで
MAX_TEXT_LENGTH = 5000
MAX_MESSAGES = 5

Responder = Callable[[str, str, str | None], Awaitable[AgentReply]]


async def agent_responder(user_id: str, text: str, session_id: str | None) -> AgentReply:
    options = build_options(
        customer_id=f"line:{user_id}",
        extra_instructions=LINE_INSTRUCTIONS,
        resume=session_id,
    )
    return await ask(text, options)


def split_text(text: str) -> list[str]:
    """LINE の文字数・通数の上限に収まるように分割する。"""
    chunks: list[str] = []
    while text and len(chunks) < MAX_MESSAGES:
        if len(text) <= MAX_TEXT_LENGTH:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, MAX_TEXT_LENGTH)
        cut = cut if cut > 0 else MAX_TEXT_LENGTH
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks


@dataclass
class Settings:
    channel_secret: str
    channel_access_token: str
    sessions_path: Path
    session_ttl_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            secret = os.environ["LINE_CHANNEL_SECRET"]
            token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
        except KeyError as e:
            raise RuntimeError(f"環境変数 {e.args[0]} が設定されていません") from None
        return cls(
            channel_secret=secret,
            channel_access_token=token,
            sessions_path=DATA_DIR / "line_sessions.json",
            session_ttl_seconds=float(os.environ.get("SESSION_TTL_HOURS", "24")) * 3600,
        )


class LineSupportBot:
    def __init__(self, settings: Settings, api: AsyncMessagingApi, responder: Responder):
        self.parser = WebhookParser(settings.channel_secret)
        self.api = api
        self.responder = responder
        self.sessions = SessionStore(settings.sessions_path, settings.session_ttl_seconds)
        # 同じユーザーから連投されても会話が混ざらないよう、ユーザー単位で順番に処理する
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def parse(self, body: str, signature: str) -> list:
        return self.parser.parse(body, signature)

    async def handle_event(self, event) -> None:
        # 1 対 1 のトークのみ対応(グループ・複数人トークは無視)
        if not isinstance(event, MessageEvent) or not isinstance(event.source, UserSource):
            return
        user_id = event.source.user_id
        if not isinstance(event.message, TextMessageContent):
            await self._send(event.reply_token, user_id, NON_TEXT_REPLY)
            return

        text = event.message.text.strip()
        async with self._locks[user_id]:
            if text in RESET_WORDS:
                self.sessions.clear(user_id)
                await self._send(event.reply_token, user_id, RESET_REPLY)
                return

            await self._show_loading(user_id)
            try:
                reply = await self.responder(user_id, text, self.sessions.get(user_id))
            except Exception:
                logger.exception("agent failed for user %s", user_id)
                await self._send(event.reply_token, user_id, ERROR_REPLY)
                return
            if reply.session_id:
                self.sessions.set(user_id, reply.session_id)
            await self._send(event.reply_token, user_id, reply.text or ERROR_REPLY)

    async def _show_loading(self, user_id: str) -> None:
        try:
            await self.api.show_loading_animation(
                ShowLoadingAnimationRequest(chat_id=user_id, loading_seconds=60)
            )
        except ApiException:
            logger.warning("failed to show loading animation", exc_info=True)

    async def _send(self, reply_token: str, user_id: str, text: str) -> None:
        messages = [TextMessage(text=chunk) for chunk in split_text(text)]
        try:
            await self.api.reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=messages)
            )
        except ApiException:
            # 回答に時間がかかり応答トークンが失効した場合はプッシュメッセージで送る
            logger.info("reply failed, falling back to push for %s", user_id)
            await self.api.push_message(PushMessageRequest(to=user_id, messages=messages))


def create_app(
    settings: Settings | None = None,
    api: AsyncMessagingApi | None = None,
    responder: Responder = agent_responder,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal settings, api
        settings = settings or Settings.from_env()
        api_client = None
        if api is None:
            api_client = AsyncApiClient(Configuration(access_token=settings.channel_access_token))
            api = AsyncMessagingApi(api_client)
        app.state.bot = LineSupportBot(settings, api, responder)
        yield
        if api_client is not None:
            await api_client.close()

    app = FastAPI(title="cyami LINE support agent", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/callback")
    async def callback(
        request: Request,
        background_tasks: BackgroundTasks,
        x_line_signature: str = Header(...),
    ) -> str:
        bot: LineSupportBot = request.app.state.bot
        body = (await request.body()).decode("utf-8")
        try:
            events = bot.parse(body, x_line_signature)
        except InvalidSignatureError:
            raise HTTPException(status_code=400, detail="Invalid signature") from None
        # LINE プラットフォームにはすぐ 200 を返し、回答の生成は裏で行う
        for event in events:
            background_tasks.add_task(bot.handle_event, event)
        return "OK"

    return app


logging.basicConfig(level=logging.INFO)
app = create_app()
