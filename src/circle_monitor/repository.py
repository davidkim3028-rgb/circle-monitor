from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sqlite3

from circle_monitor.models import EventCandidate, StoredEvent


class EventRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database_path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dedupe_key TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                cluster_key TEXT NOT NULL,
                title_norm TEXT NOT NULL,
                content_fingerprint TEXT NOT NULL,
                numeric_markers TEXT NOT NULL,
                document_markers TEXT NOT NULL,
                novelty_reason TEXT NOT NULL,
                published_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_events_published_at
            ON events (published_at)
            """
        )
        self.connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedupe_key
            ON events (dedupe_key)
            """
        )
        self.connection.commit()

    def has_events(self) -> bool:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM events").fetchone()
        return bool(row["count"])

    def recent_events(self, hours: int) -> list[StoredEvent]:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        rows = self.connection.execute(
            """
            SELECT *
            FROM events
            WHERE published_at >= ?
            ORDER BY published_at DESC
            LIMIT 500
            """,
            (cutoff.isoformat(),),
        ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def save_event(self, candidate: EventCandidate) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO events (
                dedupe_key,
                title,
                category,
                canonical_url,
                cluster_key,
                title_norm,
                content_fingerprint,
                numeric_markers,
                document_markers,
                novelty_reason,
                published_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.dedupe_key,
                candidate.title,
                candidate.category,
                candidate.canonical_url,
                candidate.cluster_key,
                candidate.title_norm,
                json.dumps(sorted(candidate.content_fingerprint)),
                json.dumps(sorted(candidate.numeric_markers)),
                json.dumps(sorted(candidate.document_markers)),
                candidate.novelty_reason,
                candidate.published_at.astimezone(UTC).isoformat(),
            ),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def _row_to_event(self, row: sqlite3.Row) -> StoredEvent:
        published_at = datetime.fromisoformat(row["published_at"])
        return StoredEvent(
            id=row["id"],
            dedupe_key=row["dedupe_key"],
            title=row["title"],
            category=row["category"],
            canonical_url=row["canonical_url"],
            cluster_key=row["cluster_key"],
            title_norm=row["title_norm"],
            content_fingerprint=set(json.loads(row["content_fingerprint"])),
            numeric_markers=set(json.loads(row["numeric_markers"])),
            document_markers=set(json.loads(row["document_markers"])),
            novelty_reason=row["novelty_reason"],
            published_at=published_at,
        )
