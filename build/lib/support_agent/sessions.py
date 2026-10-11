"""LINE ユーザーごとの会話セッション ID の保存。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class SessionStore:
    """ユーザー ID → (Agent SDK のセッション ID, 最終更新時刻) を JSON ファイルに保存する。

    ttl_seconds を過ぎた会話は引き継がず、新しい会話として扱う。
    """

    def __init__(self, path: Path, ttl_seconds: float = 24 * 60 * 60):
        self.path = path
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, user_id: str) -> str | None:
        with self._lock:
            entry = self._load().get(user_id)
        if not entry or time.time() - entry["updated_at"] > self.ttl_seconds:
            return None
        return entry["session_id"]

    def set(self, user_id: str, session_id: str) -> None:
        with self._lock:
            data = self._load()
            data[user_id] = {"session_id": session_id, "updated_at": time.time()}
            self._save(data)

    def clear(self, user_id: str) -> None:
        with self._lock:
            data = self._load()
            if data.pop(user_id, None) is not None:
                self._save(data)
