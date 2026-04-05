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


class NoveltyJudge:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def evaluate(self, candidate: EventCandidate, recent_events: list[StoredEvent]) -> NoveltyDecision:
        for event in recent_events:
            if candidate.canonical_url == event.canonical_url:
                if self._has_new_facts(candidate, event):
                    return NoveltyDecision(True, f"동일 URL이지만 새 사실 감지: {candidate.novelty_reason}", event.id)
                return NoveltyDecision(False, "동일 URL의 기존 이벤트", event.id)

            title_similarity = SequenceMatcher(None, candidate.title_norm, event.title_norm).ratio()
            content_similarity = jaccard(candidate.content_fingerprint, event.content_fingerprint)
            within_window = abs(candidate.published_at - event.published_at) <= timedelta(
                hours=self.config.event_window_hours
            )

            if within_window and title_similarity >= self.config.title_similarity_threshold:
                if self._has_new_facts(candidate, event):
                    return NoveltyDecision(True, f"유사 제목이지만 새 사실 감지: {candidate.novelty_reason}", event.id)
                return NoveltyDecision(False, f"제목 유사도 {title_similarity:.2f}로 기존 사건과 중복", event.id)

            if within_window and content_similarity >= self.config.content_similarity_threshold:
                if self._has_new_facts(candidate, event):
                    return NoveltyDecision(True, f"본문 유사하지만 새 사실 감지: {candidate.novelty_reason}", event.id)
                return NoveltyDecision(False, f"본문 유사도 {content_similarity:.2f}로 기존 사건과 중복", event.id)

            if candidate.cluster_key and candidate.cluster_key == event.cluster_key and within_window:
                if self._has_new_facts(candidate, event):
                    return NoveltyDecision(True, f"동일 사건 후속 업데이트로 판단: {candidate.novelty_reason}", event.id)
                return NoveltyDecision(False, "동일 사건 클러스터의 후속 기사이지만 새 사실 없음", event.id)

        return NoveltyDecision(True, "최근 저장 이벤트와 비교 시 신규 이벤트")

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
