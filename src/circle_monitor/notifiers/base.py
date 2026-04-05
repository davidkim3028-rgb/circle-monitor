from __future__ import annotations

from abc import ABC, abstractmethod


class BaseNotifier(ABC):
    @abstractmethod
    def send(self, message: str) -> None:
        raise NotImplementedError
