from __future__ import annotations

from collections import Counter
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from circle_monitor.models import AppConfig, EventCandidate, RawItem

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "about", "after",
    "circle", "usdc", "stablecoin", "news", "press", "release", "says", "said",
}

UPDATE_MARKERS = (
    "approves", "approved", "files", "filed", "launches", "launched", "votes", "voted",
    "wins", "lost", "settles", "settlement", "hearing", "guidance", "reserve", "audit",
    "redeem", "mint", "investigation", "lawsuit", "partnership", "acquisition", "ipo",
)


class EventAnalyzer:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def should_consider(self, item: RawItem) -> bool:
        haystack = f"{item.title}\n{item.content}".lower()
        return any(keyword in haystack for keyword in self.config.required_keywords)

    def to_candidate(self, item: RawItem) -> EventCandidate:
        clean_title = squeeze_whitespace(strip_html(item.title))
        clean_content = squeeze_whitespace(strip_html(item.content))
        canonical_url = canonicalize_url(item.url)
        tokens = tokenize(f"{clean_title} {clean_content}")
        fingerprint = informative_tokens(tokens)
        numeric_markers = extract_numeric_markers(clean_title, clean_content)
        document_markers = extract_document_markers(clean_title, clean_content, canonical_url)
        cluster_key = build_cluster_key(clean_title, fingerprint)
        event_signature = build_event_signature(clean_title, clean_content, item.category, document_markers)
        impact_direction, short_term, medium_term, rationale = impact_assessment(
            clean_title, clean_content, self.config.high_impact_keywords
        )
        relevance_score, relevance_reason = assess_circle_relevance(clean_title, clean_content, item.category)
        summary_lines = build_summary_lines(clean_title, clean_content)
        detail_lines = build_detail_lines(item, clean_content)
        novelty_reason = build_novelty_hint(numeric_markers, document_markers, clean_title, clean_content)
        dedupe_key = hashlib.sha1(f"{canonical_url}|{cluster_key}".encode("utf-8")).hexdigest()

        return EventCandidate(
            dedupe_key=dedupe_key,
            category=item.category,
            title=clean_title,
            canonical_url=canonical_url,
            published_at=item.published_at,
            summary_lines=summary_lines,
            detail_lines=detail_lines,
            impact_direction=impact_direction,
            short_term_impact=short_term,
            medium_term_impact=medium_term,
            rationale=rationale,
            relevance_score=relevance_score,
            relevance_reason=relevance_reason,
            related_links=[canonical_url],
            novelty_reason=novelty_reason,
            cluster_key=cluster_key,
            event_signature=event_signature,
            title_norm=normalize_text(clean_title),
            content_fingerprint=fingerprint,
            numeric_markers=numeric_markers,
            document_markers=document_markers,
            publisher=item.publisher,
            source_name=item.source_name,
            raw_content=clean_content,
        )


def strip_html(text: str) -> str:
    return BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)


def squeeze_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def tokenize(text: str) -> list[str]:
    return [token for token in normalize_text(text).split() if token]


def informative_tokens(tokens: list[str]) -> set[str]:
    return {token for token in tokens if len(token) > 2 and token not in STOPWORDS}


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith(("utm_", "fbclid", "gclid"))
    ]
    cleaned = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        fragment="",
        query=urlencode(query),
    )
    normalized_path = re.sub(r"/+", "/", cleaned.path or "/")
    cleaned = cleaned._replace(path=normalized_path.rstrip("/") or "/")
    return urlunparse(cleaned)


def extract_numeric_markers(title: str, content: str) -> set[str]:
    text = f"{title}\n{content}"
    return set(re.findall(r"\b\d[\d,\.]*%?|\$\d[\d,\.]*\b", text))


def extract_document_markers(title: str, content: str, url: str) -> set[str]:
    text = f"{title}\n{content}\n{url}".lower()
    patterns = [
        r"\bfile\s+no\.\s*[a-z0-9-]+\b",
        r"\brelease\s+no\.\s*[a-z0-9-]+\b",
        r"\bhr\s*\d+\b",
        r"\bs\.\s*\d+\b",
        r"\bact\b",
        r"\bsec\b",
        r"\bcftc\b",
        r"\bocc\b",
        r"\bfdic\b",
    ]
    markers: set[str] = set()
    for pattern in patterns:
        markers.update(re.findall(pattern, text))
    return markers


def build_cluster_key(title: str, fingerprint: set[str]) -> str:
    title_tokens = tokenize(title)
    combined = sorted(set(title_tokens[:5]) | set(sorted(fingerprint)[:8]))
    return " ".join(combined[:10])


def build_event_signature(title: str, content: str, category: str, document_markers: set[str]) -> str:
    haystack = f"{title}\n{content}"
    parts = [category.lower()]

    named_patterns = [
        r"\bGENIUS Act\b",
        r"\bClarity Act\b",
        r"\bmemorandum of understanding\b",
        r"\broundtable\b",
        r"\bspeech\b",
        r"\bremarks\b",
        r"\bhearing\b",
        r"\bpress release\b",
        r"\bChair(?:man|woman)?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b",
        r"\bCommissioner\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b",
        r"\bSecretary\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b",
    ]
    for pattern in named_patterns:
        match = re.search(pattern, haystack, re.IGNORECASE)
        if match:
            parts.append(normalize_text(match.group(0)))

    if document_markers:
        parts.extend(sorted(document_markers)[:2])

    lowered = haystack.lower()
    if "sec" in lowered and "cftc" in lowered:
        parts.append("sec_cftc_joint")
    if "speech" in lowered or "remarks" in lowered:
        parts.append("speech_or_remarks")

    return " | ".join(dict.fromkeys(part for part in parts if part))


def build_summary_lines(title: str, content: str) -> list[str]:
    sentences = split_sentences(content)
    first = sentences[0] if sentences else title
    second = sentences[1] if len(sentences) > 1 else ""
    lines = [
        f"이번 알림의 핵심은 '{title}' 관련 새 정보가 포착됐다는 점입니다.",
        f"원문에서 가장 먼저 확인되는 내용은 {rewrite_sentence_as_korean(first)}",
        f"추가로 확인된 맥락은 {rewrite_sentence_as_korean(second) if second else '후속 사실은 원문 링크에서 계속 확인할 필요가 있다는 점입니다.'}",
    ]
    return [line[:280] for line in lines if line][:3]


def build_detail_lines(item: RawItem, content: str) -> list[str]:
    sentences = split_sentences(content)
    publisher = item.publisher or item.source_name
    first = rewrite_sentence_as_korean(sentences[0]) if sentences else "원문 본문이 짧아 링크 확인이 필요합니다."
    second = rewrite_sentence_as_korean(sentences[1]) if len(sentences) > 1 else "현재 확보된 본문만으로는 세부 수치나 후속 절차까지 모두 드러나지 않을 수 있습니다."
    third = rewrite_sentence_as_korean(sentences[2]) if len(sentences) > 2 else "이 이슈가 추가 공시, 규제 문서, 후속 인터뷰로 이어지는지 계속 추적하는 것이 중요합니다."
    details = [
        f"이번 내용은 {publisher}가 공개한 자료를 기준으로 수집됐습니다. 단순히 제목만 본 것이 아니라 본문과 링크를 함께 읽어, 무엇이 실제 변화인지 확인하도록 구성했습니다.",
        f"기사 또는 발표문이 전달하는 첫 번째 포인트는 {first}",
        f"그다음으로 눈여겨볼 부분은 {second}",
        f"이 정보를 중요하게 보는 이유는 {item.category} 카테고리 안에서 Circle, USDC, 경쟁 스테이블코인, 또는 미국 규제 환경에 연결될 수 있는 변화이기 때문입니다. 특히 {third}",
        f"즉, 이번 알림은 '관련 언급이 있었다' 수준이 아니라, 어떤 주체가 무엇을 발표했고 그 내용이 기존 상황과 어떻게 이어지는지를 빠르게 이해할 수 있도록 정리한 것입니다.",
    ]
    return [detail for detail in details if detail]


def impact_assessment(title: str, content: str, high_impact_keywords: list[str]) -> tuple[str, str, str, str]:
    haystack = f"{title}\n{content}".lower()
    counter = Counter(keyword for keyword in high_impact_keywords if keyword in haystack)
    negative_terms = {"lawsuit", "investigation", "halt", "outage"}
    positive_terms = {"launch", "partnership", "approval", "ipo", "audit"}

    if any(term in haystack for term in negative_terms):
        direction = "악재"
    elif any(term in haystack for term in positive_terms):
        direction = "호재"
    else:
        direction = "중립"

    intensity = max(sum(counter.values()), 1)
    short_term = (
        f"단기적으로는 시장이 헤드라인 자체에 먼저 반응할 가능성이 큽니다. 이번 건에서는 중요 키워드가 {intensity}건 포착됐고, "
        f"그 조합상 투자자들은 이를 {direction} 재료로 받아들일 여지가 있습니다. 특히 단기 매매 관점에서는 관련 종목 심리, "
        f"스테이블코인 섹터 전반의 신뢰도, 규제 기대감 또는 리스크 프리미엄 변화가 먼저 움직일 수 있습니다."
    )
    medium_term = (
        "중기적으로 더 중요한 것은 이번 뉴스가 실제 사업 구조 변화로 이어지느냐입니다. 규제 발표라면 집행 또는 입법 단계의 진전이 있는지, "
        "파트너십이라면 실제 유통 확대와 거래량 증가로 연결되는지, 준비금이나 감사 이슈라면 신뢰도 개선 혹은 훼손으로 이어지는지 확인해야 합니다. "
        "즉, 오늘의 헤드라인보다 이후에 붙는 수치, 문서, 일정, 기관 반응이 중기 영향의 크기를 결정합니다."
    )
    rationale = (
        "방향성은 제목과 본문에 포함된 사건 유형, 규제/소송/제휴/감사 같은 키워드, 그리고 새 수치나 새 문서가 붙었는지 여부를 함께 보고 판단했습니다. "
        "지금 단계에서는 원문에서 확인되는 사실을 바탕으로 초기 해석을 제공하고, 후속 공시나 추가 보도가 나오면 그때 영향도를 더 정교하게 업데이트하는 구조입니다."
    )
    return direction, short_term, medium_term, rationale


def assess_circle_relevance(title: str, content: str, category: str) -> tuple[int, str]:
    haystack = f"{title}\n{content}".lower()
    score = 1
    reasons: list[str] = []

    if "circle" in haystack or "usdc" in haystack:
        score = max(score, 9)
        reasons.append("기사 본문이나 제목에 Circle 또는 USDC가 직접 등장합니다.")

    if "coinbase" in haystack or "tether" in haystack or "stablecoin" in haystack:
        score = max(score, 7)
        reasons.append("Circle 경쟁 구도 또는 스테이블코인 시장 비교와 연결됩니다.")

    if category in {"SEC", "Regulation", "Bill"} or any(
        keyword in haystack for keyword in ["sec", "cftc", "occ", "federal reserve", "treasury", "genius act", "clarity act"]
    ):
        score = max(score, 6)
        reasons.append("미국 규제 환경 변화로서 Circle 사업 모델에 간접 영향을 줄 수 있습니다.")

    if any(keyword in haystack for keyword in ["reserve", "audit", "redeem", "mint", "partnership", "ipo", "lawsuit"]):
        score = min(10, score + 1)
        reasons.append("준비금, 감사, 파트너십, 상장, 소송 같은 핵심 이벤트 유형이 감지됐습니다.")

    if not reasons:
        reasons.append("Circle과의 직접 연결은 약하지만 산업 또는 규제 맥락에서 참고할 가치는 있습니다.")

    return max(1, min(score, 10)), " ".join(dict.fromkeys(reasons))


def build_novelty_hint(
    numeric_markers: set[str], document_markers: set[str], title: str, content: str
) -> str:
    markers: list[str] = []
    if numeric_markers:
        markers.append(f"새 수치 후보 {', '.join(sorted(numeric_markers)[:3])}")
    if document_markers:
        markers.append(f"새 문서/기관 표식 {', '.join(sorted(document_markers)[:3])}")
    lowered = f"{title}\n{content}".lower()
    for term in UPDATE_MARKERS:
        if term in lowered:
            markers.append(f"업데이트 신호 '{term}' 감지")
            break
    if not markers:
        markers.append("기존 이벤트와 다른 제목/본문 클러스터로 분류")
    return "; ".join(markers)


def split_sentences(text: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"(?<=[\.\!\?])\s+", text) if segment.strip()]


def rewrite_sentence_as_korean(text: str) -> str:
    cleaned = squeeze_whitespace(text)
    if not cleaned:
        return "본문상 추가 문장이 부족합니다."
    return f"원문에서는 '{cleaned[:220]}'라고 설명합니다."
