from __future__ import annotations

import json
import os
from typing import Any

import requests

from circle_monitor.http import build_raw_session
from circle_monitor.models import AppConfig, EventCandidate


class OpenAIEnricher:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.api_key = os.getenv(config.llm_api_key_env, "").strip()
        self.temporarily_disabled = False
        self.session = build_raw_session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    def is_enabled(self) -> bool:
        return self.config.llm_enabled and bool(self.api_key) and not self.temporarily_disabled

    def enrich(self, candidate: EventCandidate) -> EventCandidate:
        if not self.is_enabled():
            return candidate

        payload = {
            "model": self.config.llm_model,
            "instructions": (
                "너는 Circle, USDC, stablecoin, 미국 규제 뉴스를 분석하는 한국어 애널리스트다. "
                "반드시 한국어로만 답하고 영어 문장을 그대로 복붙하지 마라. "
                "Circle 연관성 점수가 5점 미만이면 상세 설명은 짧게 유지하고, 핵심 요약과 링크, 주가 영향 분석 중심으로 간단히 정리하라. "
                "Circle 연관성 점수가 6점 이상이면 기사나 데이터 내용을 사용자가 이해하기 쉽게 자세하고 길게 설명하라. "
                "입력에 없는 사실을 지어내지 말고, 링크는 바꾸지 말며, 반드시 JSON만 출력하라."
            ),
            "input": build_prompt(candidate, self.config),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "circle_alert",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "summary_lines": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 3,
                                "maxItems": 3,
                            },
                            "detail_lines": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                                "maxItems": 6,
                            },
                            "impact_direction": {
                                "type": "string",
                                "enum": ["호재", "악재", "중립"],
                            },
                            "relevance_score": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 10,
                            },
                            "relevance_reason": {"type": "string"},
                            "short_term_impact": {"type": "string"},
                            "medium_term_impact": {"type": "string"},
                            "rationale": {"type": "string"},
                            "novelty_reason": {"type": "string"},
                        },
                        "required": [
                            "title",
                            "summary_lines",
                            "detail_lines",
                            "impact_direction",
                            "relevance_score",
                            "relevance_reason",
                            "short_term_impact",
                            "medium_term_impact",
                            "rationale",
                            "novelty_reason",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
        }

        response = self.session.post(
            "https://api.openai.com/v1/responses",
            json=payload,
            timeout=self.config.llm_timeout_seconds,
        )
        if response.status_code == 429:
            self.temporarily_disabled = True
            detail = safe_error_text(response)
            raise requests.HTTPError(
                f"OpenAI API 429 Too Many Requests / quota issue: {detail}",
                response=response,
            )
        response.raise_for_status()
        data = response.json()
        text = extract_output_text(data)
        parsed = json.loads(text)

        candidate.title = parsed["title"].strip() or candidate.title
        candidate.summary_lines = [item.strip() for item in parsed["summary_lines"] if item.strip()]
        candidate.detail_lines = [item.strip() for item in parsed["detail_lines"] if item.strip()]
        candidate.impact_direction = parsed["impact_direction"]
        candidate.relevance_score = int(parsed["relevance_score"])
        candidate.relevance_reason = parsed["relevance_reason"].strip()
        candidate.short_term_impact = parsed["short_term_impact"].strip()
        candidate.medium_term_impact = parsed["medium_term_impact"].strip()
        candidate.rationale = parsed["rationale"].strip()
        candidate.novelty_reason = parsed["novelty_reason"].strip() or candidate.novelty_reason
        return candidate


def build_prompt(candidate: EventCandidate, config: AppConfig) -> str:
    body = candidate.raw_content[: config.llm_max_input_chars]
    return (
        f"[이벤트 메타]\n"
        f"- 카테고리: {candidate.category}\n"
        f"- 원제목: {candidate.title}\n"
        f"- 발행 주체: {candidate.publisher or candidate.source_name}\n"
        f"- 발행 시각(KST 기준 처리 대상): {candidate.published_at.isoformat()}\n"
        f"- 링크: {candidate.canonical_url}\n"
        f"- 새 수치 후보: {', '.join(sorted(candidate.numeric_markers)) or '없음'}\n"
        f"- 새 문서 표식 후보: {', '.join(sorted(candidate.document_markers)) or '없음'}\n"
        f"- 규칙 기반 Circle 연관성 점수: {candidate.relevance_score}/10\n"
        f"- 규칙 기반 Circle 연관성 이유: {candidate.relevance_reason}\n"
        f"- 규칙 기반 신규성 힌트: {candidate.novelty_reason}\n\n"
        f"[본문]\n{body}\n\n"
        f"[작성 요청]\n"
        f"1. 영어를 그대로 남기지 말고 자연스러운 한국어 제목을 작성.\n"
        f"2. summary_lines는 3개. 각 줄은 한 문장으로, 사용자가 바로 핵심을 이해할 수 있게 작성.\n"
        f"3. relevance_score가 5점 미만이면 detail_lines는 1~2개의 짧은 설명으로 충분하다.\n"
        f"4. relevance_score가 6점 이상이면 detail_lines는 4~6개로 길고 자세하게 작성한다.\n"
        f"5. short_term_impact와 medium_term_impact는 각각 충분히 길게 작성.\n"
        f"6. relevance_score는 Circle과의 연관성을 1~10점으로 채점.\n"
        f"7. relevance_reason에는 왜 그 점수를 줬는지 설명.\n"
        f"8. rationale에는 왜 호재/악재/중립인지 논리를 설명.\n"
        f"9. novelty_reason에는 왜 이 알림이 새 정보인지 설명.\n"
    )


def extract_output_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"]

    output = data.get("output", [])
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return content["text"]
    raise ValueError("OpenAI response text를 찾지 못했습니다.")


def safe_error_text(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]
    error = payload.get("error")
    if isinstance(error, dict):
        return json.dumps(error, ensure_ascii=False)
    return json.dumps(payload, ensure_ascii=False)[:500]
