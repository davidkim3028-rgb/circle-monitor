from __future__ import annotations

import requests

from circle_monitor.notifiers.base import BaseNotifier


class TelegramNotifier(BaseNotifier):
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, message: str) -> None:
        if not self.bot_token or not self.chat_id:
            raise ValueError("Telegram bot_token/chat_id가 설정되지 않았습니다.")
        response = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={"chat_id": self.chat_id, "text": message},
            timeout=20,
        )
        if not response.ok:
            detail = response.text[:500]
            raise requests.HTTPError(
                f"Telegram sendMessage failed ({response.status_code}): {detail}",
                response=response,
            )
