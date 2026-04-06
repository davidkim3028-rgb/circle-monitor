from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from circle_monitor.models import EventCandidate
from circle_monitor.repository import EventRepository


def test_repository_stores_and_reads_recent_events() -> None:
    db_path = Path("data/test_repository_events.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    repo = EventRepository(str(db_path))
    candidate = EventCandidate(
        dedupe_key="abc",
        category="Circle",
        title="Circle launches service",
        canonical_url="https://example.com/news",
        published_at=datetime.now(UTC),
        summary_lines=["summary"],
        detail_lines=["detail"],
        impact_direction="호재",
        relevance_score=9,
        relevance_reason="Circle 직접 서비스 출시 기사입니다.",
        short_term_impact="short",
        medium_term_impact="medium",
        rationale="reason",
        related_links=["https://example.com/news"],
        novelty_reason="new",
        cluster_key="circle launches",
        event_signature="circle launches",
        title_norm="circle launches service",
        content_fingerprint={"circle", "launches"},
        numeric_markers={"100"},
        document_markers={"release no. 1"},
    )
    try:
        repo.save_event(candidate)
        events = repo.recent_events(24)
        assert len(events) == 1
        assert events[0].title == "Circle launches service"
        assert not repo.was_notified_recently("abc", 12)
        repo.record_notification("abc", candidate.title, candidate.canonical_url)
        assert repo.was_notified_recently("abc", 12)
    finally:
        repo.close()
        if db_path.exists():
            db_path.unlink()
