from __future__ import annotations

import requests

from circle_monitor.http import build_raw_session
from circle_monitor.notifiers.base import BaseNotifier


class TelegramNotifier(BaseNotifier):
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.session = build_raw_session()

    _LIMIT = 4096

    def send(self, message: str) -> None:
        if not self.bot_token or not self.chat_id:
            raise ValueError("Telegram bot_token/chat_id가 설정되지 않았습니다.")
        for chunk in self._split(message):
            self._post(chunk)

    def _post(self, text: str) -> None:
        response = self.session.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={"chat_id": self.chat_id, "text": text},
            timeout=20,
        )
        if not response.ok:
            detail = response.text[:500]
            raise requests.HTTPError(
                f"Telegram sendMessage failed ({response.status_code}): {detail}",
                response=response,
            )

    def _split(self, message: str) -> list[str]:
        if len(message) <= self._LIMIT:
            return [message]
        chunks: list[str] = []
        while message:
            if len(message) <= self._LIMIT:
                chunks.append(message)
                break
            cut = message.rfind("\n", 0, self._LIMIT)
            if cut <= 0:
                cut = self._LIMIT
            chunks.append(message[:cut])
            message = message[cut:].lstrip("\n")
        return chunks
