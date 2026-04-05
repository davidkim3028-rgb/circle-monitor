from __future__ import annotations

from zoneinfo import ZoneInfo

from circle_monitor.models import AppConfig, EventCandidate


def format_alert(candidate: EventCandidate, config: AppConfig, novelty_reason: str) -> str:
    published_at = candidate.published_at.astimezone(ZoneInfo(config.timezone))
    summary = "\n".join(f"* {line}" for line in candidate.summary_lines)
    details = "\n".join(f"* {line}" for line in candidate.detail_lines)
    links = "\n".join(f"* {link}" for link in candidate.related_links)
    return (
        f"[새 알림] {candidate.title}\n\n"
        f"* 발생 시각(KST): {published_at.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"* 카테고리: {candidate.category}\n\n"
        f"0. Circle 연관성\n\n"
        f"* 점수: {candidate.relevance_score}/10\n"
        f"* 판단 이유: {candidate.relevance_reason}\n\n"
        f"1. 핵심 요약\n\n"
        f"{summary}\n\n"
        f"2. 상세 설명\n\n"
        f"{details}\n\n"
        f"3. 주가 및 Circle 영향 분석\n\n"
        f"* 방향성: {candidate.impact_direction}\n"
        f"* 단기 영향: {candidate.short_term_impact}\n"
        f"* 중기 영향: {candidate.medium_term_impact}\n"
        f"* 해석 근거: {candidate.rationale}\n"
        f"* 종합 판단: 이번 이슈는 Circle 자체 이슈이든, 경쟁사/규제/시장 이벤트이든 결국 USDC의 신뢰도, 유통 확대 가능성, 규제 부담, 투자심리에 어떻게 연결되는지가 핵심입니다. 따라서 단순 기사 존재 여부보다 실제 후속 데이터가 붙는지 계속 추적하는 것이 중요합니다.\n\n"
        f"4. 관련 링크\n\n"
        f"{links}\n\n"
        f"5. 중복 여부 체크 결과\n\n"
        f"* {novelty_reason}\n"
    )
