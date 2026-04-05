from __future__ import annotations

import requests

from circle_monitor.models import AppConfig


def build_session(config: AppConfig) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": f"{config.request_user_agent} ({config.request_contact_email})",
            "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session
