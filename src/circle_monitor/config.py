from __future__ import annotations

from pathlib import Path
import os
import tomllib

from circle_monitor.models import AppConfig, SourceConfig


def load_config(path: str) -> AppConfig:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    app = data["app"]
    analysis = data["analysis"]
    notifications = data.get("notifications", {})
    filters = data.get("filters", {})
    llm = data.get("llm", {})

    sources = [
        SourceConfig(
            name=item["name"],
            kind=item["kind"],
            url=item["url"],
            category=item["category"],
            publisher=item.get("publisher", ""),
            priority=int(item.get("priority", 2)),
            item_selector=item.get("item_selector"),
        )
        for item in data.get("sources", [])
    ]

    return AppConfig(
        poll_interval_seconds=int(app.get("poll_interval_seconds", 900)),
        timezone=app.get("timezone", "Asia/Seoul"),
        database_path=app.get("database_path", "data/events.db"),
        log_path=app.get("log_path", "logs/circle_monitor.log"),
        request_user_agent=app.get("request_user_agent", "circle-monitor/0.1"),
        request_contact_email=app.get("request_contact_email", "your-email@example.com"),
        alert_recency_hours=int(app.get("alert_recency_hours", 48)),
        bootstrap_lookback_hours=int(app.get("bootstrap_lookback_hours", 6)),
        max_items_per_source=int(app.get("max_items_per_source", 20)),
        title_similarity_threshold=float(analysis.get("title_similarity_threshold", 0.83)),
        content_similarity_threshold=float(analysis.get("content_similarity_threshold", 0.88)),
        event_window_hours=int(analysis.get("event_window_hours", 168)),
        enabled_notifiers=list(notifications.get("enabled", ["stdout"])),
        notifier_settings={
            key: value
            for key, value in notifications.items()
            if isinstance(value, dict)
        },
        sources=sources,
        required_keywords=[item.lower() for item in filters.get("required_keywords", [])],
        high_impact_keywords=[item.lower() for item in filters.get("high_impact_keywords", [])],
        llm_enabled=bool(llm.get("enabled", False)),
        llm_provider=llm.get("provider", "openai"),
        llm_model=llm.get("model", "gpt-5-mini"),
        llm_api_key_env=llm.get("api_key_env", "OPENAI_API_KEY"),
        llm_timeout_seconds=int(llm.get("timeout_seconds", 45)),
        llm_max_input_chars=int(llm.get("max_input_chars", 6000)),
    )
