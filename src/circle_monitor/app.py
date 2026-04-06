from __future__ import annotations

from datetime import datetime, timedelta
from difflib import SequenceMatcher
import logging
import time
from zoneinfo import ZoneInfo

from circle_monitor.analysis import EventAnalyzer
from circle_monitor.config import load_config
from circle_monitor.dedupe import NoveltyJudge
from circle_monitor.formatting import format_alert, format_stored_event_alert
from circle_monitor.logging_utils import configure_logging
from circle_monitor.llm import OpenAIEnricher
from circle_monitor.models import AppConfig, EventCandidate, RawItem, StoredEvent
from circle_monitor.notifiers.base import BaseNotifier
from circle_monitor.notifiers.discord import DiscordNotifier
from circle_monitor.notifiers.slack import SlackNotifier
from circle_monitor.notifiers.stdout import StdoutNotifier
from circle_monitor.notifiers.telegram import TelegramNotifier
from circle_monitor.repository import EventRepository
from circle_monitor.sources.base import BaseSource
from circle_monitor.sources.rss import RssSource
from circle_monitor.sources.website import WebsiteSource

LOGGER = logging.getLogger(__name__)


def build_sources(config: AppConfig) -> list[BaseSource]:
    sources: list[BaseSource] = []
    for source in config.sources:
        if source.kind == "rss":
            sources.append(RssSource(source, config.timezone, config))
        elif source.kind == "website":
            sources.append(WebsiteSource(source, config.timezone, config))
        else:
            raise ValueError(f"지원하지 않는 source kind: {source.kind}")
    return sources


def build_notifiers(config: AppConfig) -> list[BaseNotifier]:
    notifiers: list[BaseNotifier] = []
    for name in config.enabled_notifiers:
        settings = config.notifier_settings.get(name, {})
        if name == "stdout":
            notifiers.append(StdoutNotifier())
        elif name == "telegram":
            notifiers.append(TelegramNotifier(settings.get("bot_token", ""), settings.get("chat_id", "")))
        elif name == "discord":
            notifiers.append(DiscordNotifier(settings.get("webhook_url", "")))
        elif name == "slack":
            notifiers.append(SlackNotifier(settings.get("webhook_url", "")))
        else:
            raise ValueError(f"지원하지 않는 notifier: {name}")
    return notifiers


class MonitorApplication:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.repo = EventRepository(config.database_path)
        self.analyzer = EventAnalyzer(config)
        self.judge = NoveltyJudge(config)
        self.sources = build_sources(config)
        self.notifiers = build_notifiers(config)
        self.llm_enricher = OpenAIEnricher(config)
        self.timezone = ZoneInfo(config.timezone)
        self._log_config_warnings()

    def run_forever(self) -> None:
        while True:
            self.run_once()
            LOGGER.info("Sleeping for %s seconds", self.config.poll_interval_seconds)
            time.sleep(self.config.poll_interval_seconds)

    def run_once(self) -> None:
        raw_items = self._collect_items()
        LOGGER.info("Collected %s raw items", len(raw_items))
        recent_events = self.repo.recent_events(self.config.event_window_hours)
        is_bootstrap = not self.repo.has_events()
        pending_candidates: list[EventCandidate] = []

        for item in sorted(raw_items, key=lambda raw: raw.published_at):
            if not self.analyzer.should_consider(item):
                continue

            candidate = self.analyzer.to_candidate(item)
            decision = self.judge.evaluate(candidate, recent_events)
            if not decision.is_new:
                if is_bootstrap:
                    LOGGER.info("Skipped duplicate item during bootstrap '%s': %s", candidate.title, decision.reason)
                    continue
                if not self._within_alert_window(item):
                    LOGGER.info("Skipped stale duplicate item '%s': %s", candidate.title, decision.reason)
                    continue
                notification_key = self._notification_key(candidate, decision)
                if self.repo.was_notified_recently(
                    notification_key,
                    self.config.duplicate_notification_cooldown_hours,
                ):
                    LOGGER.info("Skipped duplicate item '%s': %s", candidate.title, decision.reason)
                    continue
                candidate.novelty_reason = (
                    f"{decision.reason} / no alert sent in the last "
                    f"{self.config.duplicate_notification_cooldown_hours} hours"
                )
                candidate.dedupe_key = notification_key
                pending_candidates.append(candidate)
                LOGGER.info(
                    "Queued duplicate item '%s' because it has not been alerted in %s hours",
                    candidate.title,
                    self.config.duplicate_notification_cooldown_hours,
                )
                continue

            if is_bootstrap:
                self.repo.save_event(candidate)
                recent_events = self.repo.recent_events(self.config.event_window_hours)
                LOGGER.info("Bootstrap baseline saved without alert: %s", candidate.title)
                continue

            if not self._within_alert_window(item):
                self.repo.save_event(candidate)
                recent_events = self.repo.recent_events(self.config.event_window_hours)
                LOGGER.info("Skipped stale event outside alert window: %s", candidate.title)
                continue

            pending_candidates.append(candidate)

        merged_candidates = self._merge_similar_candidates(pending_candidates)

        for candidate in merged_candidates:
            decision_reason = candidate.novelty_reason

            try:
                candidate = self.llm_enricher.enrich(candidate)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("LLM enrichment failed for '%s': %s", candidate.title, exc)

            message = format_alert(candidate, self.config, decision_reason)
            for notifier in self.notifiers:
                try:
                    notifier.send(message)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.exception(
                        "Notifier %s failed for '%s': %s",
                        notifier.__class__.__name__,
                        candidate.title,
                        exc,
                    )
            self.repo.save_event(candidate)
            self.repo.record_notification(candidate.dedupe_key, candidate.title, candidate.canonical_url)
            recent_events = self.repo.recent_events(self.config.event_window_hours)
            LOGGER.info("Stored new event '%s'", candidate.title)

        self._send_catch_up_alerts()

    def _collect_items(self) -> list[RawItem]:
        items: list[RawItem] = []
        for source in self.sources:
            try:
                items.extend(source.fetch(self.config.max_items_per_source))
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Source failed: %s", exc)
        return items

    def _within_alert_window(self, item: RawItem) -> bool:
        now = datetime.now(tz=self.timezone)
        cutoff = now - timedelta(hours=self.config.alert_recency_hours)
        return item.published_at >= cutoff

    def _notification_key(self, candidate: EventCandidate, decision) -> str:
        if getattr(decision, "matched_dedupe_key", None):
            return decision.matched_dedupe_key
        return candidate.dedupe_key

    def _send_catch_up_alerts(self) -> None:
        events = self.repo.recent_unnotified_events(
            self.config.alert_recency_hours,
            self.config.duplicate_notification_cooldown_hours,
        )
        for event in events:
            message = format_stored_event_alert(
                event,
                self.config,
                f"not sent in the last {self.config.duplicate_notification_cooldown_hours} hours",
            )
            if self._send_message_to_notifiers(message, event.title):
                self.repo.record_notification(event.dedupe_key, event.title, event.canonical_url)
                LOGGER.info("Sent catch-up alert for '%s'", event.title)

    def _send_message_to_notifiers(self, message: str, title: str) -> bool:
        delivered = False
        for notifier in self.notifiers:
            try:
                notifier.send(message)
                delivered = True
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception(
                    "Notifier %s failed for '%s': %s",
                    notifier.__class__.__name__,
                    title,
                    exc,
                )
        return delivered

    def _merge_similar_candidates(self, candidates: list[EventCandidate]) -> list[EventCandidate]:
        merged: list[EventCandidate] = []
        for candidate in candidates:
            target = None
            for existing in merged:
                if self._should_merge(existing, candidate):
                    target = existing
                    break

            if target is None:
                merged.append(candidate)
                continue

            target.related_links = dedupe_preserve_order(target.related_links + candidate.related_links)
            target.numeric_markers |= candidate.numeric_markers
            target.document_markers |= candidate.document_markers
            target.content_fingerprint |= candidate.content_fingerprint
            target.raw_content = merge_text_blocks(target.raw_content, candidate.raw_content)
            target.relevance_score = max(target.relevance_score, candidate.relevance_score)
            if len(candidate.relevance_reason) > len(target.relevance_reason):
                target.relevance_reason = candidate.relevance_reason
            target.novelty_reason = f"{target.novelty_reason} / 유사 기사 병합: 링크 {len(target.related_links)}건"
            if candidate.published_at > target.published_at:
                target.published_at = candidate.published_at
            if len(candidate.title) > len(target.title):
                target.title = candidate.title
                target.title_norm = candidate.title_norm
            target.detail_lines = dedupe_preserve_order(target.detail_lines + candidate.detail_lines)[:6]
            target.summary_lines = dedupe_preserve_order(target.summary_lines + candidate.summary_lines)[:3]

        return merged

    def _should_merge(self, left: EventCandidate, right: EventCandidate) -> bool:
        same_category = left.category == right.category
        close_in_time = abs(left.published_at - right.published_at) <= timedelta(hours=24)
        same_cluster = bool(left.cluster_key and left.cluster_key == right.cluster_key)
        same_signature = bool(left.event_signature and left.event_signature == right.event_signature)
        title_similarity = SequenceMatcher(None, left.title_norm, right.title_norm).ratio()
        overlapping_links = bool(set(left.related_links) & set(right.related_links))
        return same_category and close_in_time and (
            same_signature or same_cluster or title_similarity >= 0.72 or overlapping_links
        )

    def _log_config_warnings(self) -> None:
        notifier_names = self.config.enabled_notifiers
        external_notifiers = {"telegram", "discord", "slack"}

        if not notifier_names:
            LOGGER.warning("No notifiers are enabled. New events will be stored, but no alerts will be sent.")
        elif not any(name in external_notifiers for name in notifier_names):
            LOGGER.warning(
                "Only non-external notifiers are enabled (%s). Alerts will stay in local stdout/logs.",
                ", ".join(notifier_names),
            )

        if self.config.request_contact_email == "your-email@example.com":
            LOGGER.warning("request_contact_email is still using the placeholder value in config.toml.")

        if self.config.llm_enabled and not self.llm_enricher.api_key:
            LOGGER.warning(
                "LLM enrichment is enabled, but %s is not set. The app will continue without OpenAI enrichment.",
                self.config.llm_api_key_env,
            )


def create_application(config_path: str) -> MonitorApplication:
    config = load_config(config_path)
    configure_logging(config.log_path)
    return MonitorApplication(config)


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen or not item:
            continue
        seen.add(item)
        output.append(item)
    return output


def merge_text_blocks(left: str, right: str) -> str:
    if not left:
        return right
    if not right or right in left:
        return left
    if left in right:
        return right
    return f"{left}\n\n{right}"
