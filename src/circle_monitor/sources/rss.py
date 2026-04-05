from __future__ import annotations

import logging

import feedparser

from circle_monitor.http import build_session
from circle_monitor.models import RawItem, SourceConfig
from circle_monitor.retry import with_retry
from circle_monitor.sources.base import BaseSource

LOGGER = logging.getLogger(__name__)


class RssSource(BaseSource):
    def __init__(self, config: SourceConfig, timezone: str, app_config) -> None:
        super().__init__(config, timezone)
        self.session = build_session(app_config)

    def fetch(self, max_items: int) -> list[RawItem]:
        def _load():
            response = self.session.get(self.config.url, timeout=20)
            response.raise_for_status()
            return response

        response = with_retry(_load)
        parsed = feedparser.parse(response.content)
        items: list[RawItem] = []
        for entry in parsed.entries[:max_items]:
            published_raw = (
                entry.get("published")
                or entry.get("updated")
                or entry.get("pubDate")
            )
            published_at = self.parse_datetime(published_raw)
            title = entry.get("title", "").strip()
            url = entry.get("link", "").strip()
            summary = entry.get("summary", "").strip()
            content_parts = [summary]
            for content_item in entry.get("content", []):
                content_parts.append(content_item.get("value", ""))
            items.append(
                RawItem(
                    source_name=self.config.name,
                    source_kind=self.config.kind,
                    category=self.config.category,
                    publisher=self.config.publisher,
                    title=title,
                    url=url,
                    published_at=published_at,
                    content="\n".join(part for part in content_parts if part),
                )
            )
        LOGGER.info("Fetched %s items from RSS source %s", len(items), self.config.name)
        return items
