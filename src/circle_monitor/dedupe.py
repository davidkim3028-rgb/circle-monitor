from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from difflib import SequenceMatcher

from circle_monitor.models import AppConfig, EventCandidate, StoredEvent


@dataclass(slots=True)
class NoveltyDecision:
    is_new: bool
    reason: str
    matched_event_id: int | None = None
    matched_dedupe_key: str | None = None


class NoveltyJudge:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def evaluate(self, candidate: EventCandidate, recent_events: list[StoredEvent]) -> NoveltyDecision:
        for event in recent_events:
            if candidate.canonical_url == event.canonical_url:
                if self._has_new_facts(candidate, event):
                    return NoveltyDecision(True, f"Same URL but new facts: {candidate.novelty_reason}", event.id, event.dedupe_key)
                return NoveltyDecision(False, "Duplicate of existing event with same URL", event.id, event.dedupe_key)

            title_similarity = SequenceMatcher(None, candidate.title_norm, event.title_norm).ratio()
            content_similarity = jaccard(candidate.content_fingerprint, event.content_fingerprint)
            within_window = abs(candidate.published_at - event.published_at) <= timedelta(
                hours=self.config.event_window_hours
            )

            if within_window and title_similarity >= self.config.title_similarity_threshold:
                if self._has_new_facts(candidate, event):
                    return NoveltyDecision(
                        True,
                        f"Similar title but new facts: {candidate.novelty_reason}",
                        event.id,
                        event.dedupe_key,
                    )
                return NoveltyDecision(
                    False,
                    f"Duplicate of existing event due to title similarity {title_similarity:.2f}",
                    event.id,
                    event.dedupe_key,
                )

            if within_window and content_similarity >= self.config.content_similarity_threshold:
                if self._has_new_facts(candidate, event):
                    return NoveltyDecision(
                        True,
                        f"Similar body but new facts: {candidate.novelty_reason}",
                        event.id,
                        event.dedupe_key,
                    )
                return NoveltyDecision(
                    False,
                    f"Duplicate of existing event due to body similarity {content_similarity:.2f}",
                    event.id,
                    event.dedupe_key,
                )

            if candidate.cluster_key and candidate.cluster_key == event.cluster_key and within_window:
                if self._has_new_facts(candidate, event):
                    return NoveltyDecision(
                        True,
                        f"Follow-up in the same cluster with new facts: {candidate.novelty_reason}",
                        event.id,
                        event.dedupe_key,
                    )
                return NoveltyDecision(
                    False,
                    "Duplicate follow-up in the same cluster without new facts",
                    event.id,
                    event.dedupe_key,
                )

        return NoveltyDecision(True, "New event compared with recent stored events")

    def _has_new_facts(self, candidate: EventCandidate, event: StoredEvent) -> bool:
        if candidate.numeric_markers - event.numeric_markers:
            return True
        if candidate.document_markers - event.document_markers:
            return True
        return False


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
