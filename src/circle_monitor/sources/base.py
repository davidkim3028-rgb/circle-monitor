from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from email.utils import parsedate_to_datetime
import logging
from zoneinfo import ZoneInfo

from circle_monitor.models import RawItem, SourceConfig

LOGGER = logging.getLogger(__name__)


class BaseSource(ABC):
    def __init__(self, config: SourceConfig, timezone: str) -> None:
        self.config = config
        self.timezone = ZoneInfo(timezone)

    @abstractmethod
    def fetch(self, max_items: int) -> list[RawItem]:
        raise NotImplementedError

    def parse_datetime(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(tz=self.timezone)
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            LOGGER.debug("Falling back to now for unparseable datetime: %s", value)
            return datetime.now(tz=self.timezone)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=self.timezone)
        return parsed.astimezone(self.timezone)
