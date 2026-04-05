from __future__ import annotations

from circle_monitor.notifiers.base import BaseNotifier


class StdoutNotifier(BaseNotifier):
    def send(self, message: str) -> None:
        print(message)
