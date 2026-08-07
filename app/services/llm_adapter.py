import json
from abc import ABC, abstractmethod

import httpx

from app.config import settings


class LLMAdapter(ABC):
    """되묻기 LLM 인터페이스."""

    @abstractmethod
    def next_question(self, history: list[dict]) -> str:
        """대화 기록을 보고 다음 되묻기 질문 1개 반환."""
        ...

    @abstractmethod
    def summarize(self, history: list[dict]) -> dict:
        """수집된 대화를 구조화된 질의 요약으로 반환."""
        ...


class MockLLMAdapter(LLMAdapter):
    """실제 LLM 없이 테스트용 mock."""

    def next_question(self, history: list[dict]) -> str:
        return "어떤 일이 있었는지 자세히 말씀해주세요."

    def summarize(self, history: list[dict]) -> dict:
        return {
            "summary": "대화 요약 (mock)",
            "field": None,
            "urgent": False,
        }


# ── 되묻기 시스템 프롬프트 (HARD 규칙) ──────────────────────────
# 설계 문서 `elicitation-design.md` §2 반영.
# LLM이 법률 답변/자문을 절대 생성하지 않도록 강제.
ELICITATION_SYSTEM_PROMPT = """\
너는 법률사무소 상담 접수용 '되묻기 에이전트'다.
절대 법률 답변/자문/예측/판단을 제공하지 마라.
너의 역할은 문의자의 질문을 이해하고, 충분한 정보를 수집하기 위해
한 번에 질문 1개만 던지는 것이다. 답변을 주지 마라.
수집할 정보: 상담 분야, 문의자 입장, 사건 경위, 진행 상황, 원하는 것, 구체적 수치.
긴급 신호(구속/긴급/내일 재판/위험) 감지 시 접수를 즉시 완료하라.

다음은 문의자와의 대화 기록이다. 마지막 문의자 발언을 읽고,
다음으로 던질 '되묻기 질문'을 단 1개만, 반드시 한 문장(30자 이내)으로
짧게 출력하라. 질문 외 다른 텍스트, 목록, 번호는 절대 출력하지 마라.
"""

# 요약 생성 시스템 프롬프트
SUMMARY_SYSTEM_PROMPT = """\
너는 법률사무소 상담 접수용 요약 에이전트다.
대화 기록을 읽고 아래 JSON 스키마로 요약해라. 법률 판단/조언을 절대 추가하지 마라.
JSON 키:
- summary: 사건 경위/상황을 간결한 문장으로
- field: 상담 분야 (가정/부동산/채권채무/형사/노무/교통사고 중 하나, 없으면 null)
- position: 문의자 입장 (예: 당사자/가족/제3자, 없으면 null)
- urgent: 긴급 여부 (true/false)

JSON만 출력하고, 마크다운 코드블록 없이 순수 JSON으로만 응답하라.
"""


class OpenRouterLLMAdapter(LLMAdapter):
    """OpenRouter API 기반 LLM 어댑터 (OpenAI 호환 채팅 완성).

    provider/model은 config의 `llm_provider`/`llm_model`로 변경 가능.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 15.0,
    ):
        self.api_key = api_key or settings.openrouter_api_key
        self.base_url = base_url or settings.openrouter_base_url
        self.model = model or settings.llm_model
        self.timeout = timeout

    def _chat(
        self, messages: list[dict], max_tokens: int | None = None
    ) -> str:
        """OpenRouter 채팅 완성 호출."""
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "KakaoLawChatbot",
        }
        payload: dict = {"model": self.model, "messages": messages}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def _parse_json_response(self, text: str) -> dict:
        """LLM 응답에서 JSON 추출 (코드블록 마크다운 제거)."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # ```json ... ``` 형태 제거
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return json.loads(cleaned)

    def next_question(self, history: list[dict]) -> str:
        messages = [{"role": "system", "content": ELICITATION_SYSTEM_PROMPT}]
        messages.extend(history)
        # max_tokens 제한으로 생성 시간 단축 (오픈빌더 스킬 timeout 5초 대응)
        return self._chat(messages, max_tokens=80)

    def summarize(self, history: list[dict]) -> dict:
        messages = [{"role": "system", "content": SUMMARY_SYSTEM_PROMPT}]
        messages.extend(history)
        raw = self._chat(messages)
        try:
            return self._parse_json_response(raw)
        except (ValueError, json.JSONDecodeError):
            # JSON 파싱 실패 시 fallback
            return {"summary": raw, "field": None, "position": None, "urgent": False}
