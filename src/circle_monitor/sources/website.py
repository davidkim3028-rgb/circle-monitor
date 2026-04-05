from __future__ import annotations

from datetime import datetime
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from circle_monitor.http import build_session
from circle_monitor.models import RawItem, SourceConfig
from circle_monitor.retry import with_retry
from circle_monitor.sources.base import BaseSource

LOGGER = logging.getLogger(__name__)


class WebsiteSource(BaseSource):
    def __init__(self, config: SourceConfig, timezone: str, app_config) -> None:
        super().__init__(config, timezone)
        self.session = build_session(app_config)

    def fetch(self, max_items: int) -> list[RawItem]:
        selector = self.config.item_selector or "a"

        def _load():
            response = self.session.get(self.config.url, timeout=20)
            response.raise_for_status()
            return response

        response = with_retry(_load)
        soup = BeautifulSoup(response.text, "html.parser")
        items: list[RawItem] = []
        seen_urls: set[str] = set()
        for tag in soup.select(selector):
            href = (tag.get("href") or "").strip()
            title = tag.get_text(" ", strip=True)
            if not href or not title:
                continue
            url = urljoin(self.config.url, href)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            items.append(
                RawItem(
                    source_name=self.config.name,
                    source_kind=self.config.kind,
                    category=self.config.category,
                    publisher=self.config.publisher,
                    title=title,
                    url=url,
                    published_at=datetime.now(tz=self.timezone),
                    content=title,
                )
            )
            if len(items) >= max_items:
                break
        LOGGER.info("Fetched %s items from website source %s", len(items), self.config.name)
        return items
