from __future__ import annotations

import requests

from circle_monitor.notifiers.base import BaseNotifier


class SlackNotifier(BaseNotifier):
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def send(self, message: str) -> None:
        if not self.webhook_url:
            raise ValueError("Slack webhook_url이 설정되지 않았습니다.")
        response = requests.post(
            self.webhook_url,
            json={"text": message},
            timeout=20,
        )
        response.raise_for_status()
