from __future__ import annotations

from datetime import UTC, datetime, timedelta

from circle_monitor.dedupe import NoveltyJudge
from circle_monitor.models import AppConfig, EventCandidate, StoredEvent


def build_config() -> AppConfig:
    return AppConfig(
        poll_interval_seconds=900,
        timezone="Asia/Seoul",
        database_path=":memory:",
        log_path="logs/test.log",
        request_user_agent="circle-monitor/0.1",
        request_contact_email="test@example.com",
        alert_recency_hours=48,
        duplicate_notification_cooldown_hours=12,
        bootstrap_lookback_hours=6,
        max_items_per_source=20,
        title_similarity_threshold=0.8,
        content_similarity_threshold=0.75,
        event_window_hours=168,
        enabled_notifiers=["stdout"],
        notifier_settings={},
        sources=[],
        required_keywords=["circle"],
        high_impact_keywords=["lawsuit", "partnership"],
    )


def build_candidate(title: str, url: str, numeric_markers: set[str]) -> EventCandidate:
    now = datetime.now(UTC)
    return EventCandidate(
        dedupe_key=f"key-{title}",
        category="Circle",
        title=title,
        canonical_url=url,
        published_at=now,
        summary_lines=["summary"],
        detail_lines=["detail"],
        impact_direction="중립",
        relevance_score=8,
        relevance_reason="Circle 관련 파트너십 이슈입니다.",
        short_term_impact="short",
        medium_term_impact="medium",
        rationale="reason",
        related_links=[url],
        novelty_reason="new",
        cluster_key="circle partnership",
        event_signature="circle partnership",
        title_norm=title.lower(),
        content_fingerprint={"circle", "partnership"},
        numeric_markers=numeric_markers,
        document_markers=set(),
    )


def build_stored(title: str, url: str, numeric_markers: set[str]) -> StoredEvent:
    return StoredEvent(
        id=1,
        dedupe_key="stored",
        title=title,
        category="Circle",
        canonical_url=url,
        cluster_key="circle partnership",
        title_norm=title.lower(),
        content_fingerprint={"circle", "partnership"},
        numeric_markers=numeric_markers,
        document_markers=set(),
        novelty_reason="old",
        published_at=datetime.now(UTC) - timedelta(hours=1),
    )


def test_duplicate_url_without_new_facts_is_rejected() -> None:
    judge = NoveltyJudge(build_config())
    candidate = build_candidate("Circle partnership update", "https://example.com/a", {"100"})
    decision = judge.evaluate(candidate, [build_stored("Circle partnership", "https://example.com/a", {"100"})])
    assert not decision.is_new


def test_duplicate_cluster_with_new_numbers_is_allowed() -> None:
    judge = NoveltyJudge(build_config())
    candidate = build_candidate("Circle partnership update", "https://example.com/b", {"150"})
    decision = judge.evaluate(candidate, [build_stored("Circle partnership", "https://example.com/a", {"100"})])
    assert decision.is_new
