from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class SourceConfig:
    name: str
    kind: str
    url: str
    category: str
    publisher: str = ""
    priority: int = 2
    item_selector: str | None = None


@dataclass(slots=True)
class AppConfig:
    poll_interval_seconds: int
    timezone: str
    database_path: str
    log_path: str
    request_user_agent: str
    request_contact_email: str
    alert_recency_hours: int
    duplicate_notification_cooldown_hours: int
    bootstrap_lookback_hours: int
    max_items_per_source: int
    title_similarity_threshold: float
    content_similarity_threshold: float
    event_window_hours: int
    enabled_notifiers: list[str]
    notifier_settings: dict[str, dict[str, str]]
    sources: list[SourceConfig]
    required_keywords: list[str]
    high_impact_keywords: list[str]
    llm_enabled: bool = False
    llm_provider: str = "openai"
    llm_model: str = "gpt-5-mini"
    llm_api_key_env: str = "OPENAI_API_KEY"
    llm_timeout_seconds: int = 45
    llm_max_input_chars: int = 6000


@dataclass(slots=True)
class RawItem:
    source_name: str
    source_kind: str
    category: str
    publisher: str
    title: str
    url: str
    published_at: datetime
    content: str


@dataclass(slots=True)
class EventCandidate:
    dedupe_key: str
    category: str
    title: str
    canonical_url: str
    published_at: datetime
    summary_lines: list[str]
    detail_lines: list[str]
    impact_direction: str
    short_term_impact: str
    medium_term_impact: str
    rationale: str
    relevance_score: int
    relevance_reason: str
    related_links: list[str]
    novelty_reason: str
    cluster_key: str
    event_signature: str
    title_norm: str
    content_fingerprint: set[str] = field(default_factory=set)
    numeric_markers: set[str] = field(default_factory=set)
    document_markers: set[str] = field(default_factory=set)
    publisher: str = ""
    source_name: str = ""
    raw_content: str = ""


@dataclass(slots=True)
class StoredEvent:
    id: int
    dedupe_key: str
    title: str
    category: str
    canonical_url: str
    cluster_key: str
    title_norm: str
    content_fingerprint: set[str]
    numeric_markers: set[str]
    document_markers: set[str]
    novelty_reason: str
    published_at: datetime


@dataclass(slots=True)
class NotificationRecord:
    notification_key: str
    last_sent_at: datetime
