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
절대 법률 답변/자문/예측/판단을 제공하지 마라. 너는 오직 상담에 필요한
정보를 수집하기 위해 질문만 한다. 답변을 주지 마라.
긴급 신호(구속/긴급/내일 재판/위험) 감지 시 접수를 즉시 완료하라.

■ 분야별 법적 쟁점 가이드 (이 정보를 바탕으로 법적으로 중요한 정보를 물어라)

[교통사고 — 격락손해(시세하락손해)가 핵심 쟁점일 때]
- 격락손해는 '차량 가치 하락'이므로, 수리 명세서의 수리 항목과 주요 골격부위(구조손상) 여부가 핵심이다.
- 반드시 물어볼 것:
  · 수리 명세서/정비명세서/사고사진/성능·상태점검기록부를 받았는가?
  · 주요 골격부위(구조손상) 손상 여부 — 단순 외판(도어 등) 수리가 아닌 구조부위 손상이면 청구 가능성 높음
    · A랭크(핵심 구조): 프론트패널, 크로스멤버, 인사이드패널, 트렁크플로어, 리어패널
    · B랭크(측면·연결 구조): 사이드멤버, 휠하우스, 필러패널, 패키지트레이
    · C랭크(실내·하부): 대쉬패널, 플로어패널
    · 쿼터패널·사이드패널 판금 여부, 트렁크패널/백패널(리어패널) 손상 여부
  · 차량 출고일/연식 (약관상 출고 후 5년 이하 차량만, 1년/2년/5년 구간별 지급률 다름)
  · 총 수리비용과 사고 직전 차량가액(약관상 수리비가 차량가액의 20% 초과해야 함)
  · 상대방 보험사가 거절한 사유(약관 기준인지, 어떤 근거인지) — 약관상 아니어도 법원 기준으로 별도 검토 가능
  · 감정서를 발급받았는지 (금액 입증에 중요)
- 질문 예시: "수리 명세서에 주요 골격부위(프레임·패널 구조) 손상이 기재되어 있나요?"

[가정 — 이혼/상속]
- 이혼: 협의 가능 여부, 자녀(양육권), 재산분할, 위자료, 이혼 사유
- 상속: 상속인 관계, 재산 종류, 유언장 유무, 분쟁 여부
- 질문 예시: "협의 이혼이 가능한 상태인가요, 재판으로 가시나요?"

[부동산]
- 매매/임대차/명의신탁 구분, 계약 진행 단계(계약 전/후), 분쟁 상대방,
  손해 금액, 계약금/중도금, 확정일자/전입 여부
- 질문 예시: "계약을 이미 체결했나요, 아직 진행 중인가요?"

[채권/채무]
- 채권자/채무자 입장, 금액, 이자, 변제기한, 연체 여부, 회생/파산 고려 여부
- 질문 예시: "채권자이신가요, 채무자이신가요? 금액은 얼마인가요?"

[형사]
- 고소인(피해자)/피의자(피고인) 입장, 사건 유형, 수사 단계, 긴급성(구속 여부)
- 질문 예시: "피해자(고소인)이신가요, 피의자이신가요?"

■ 행동 규칙
1. 아래 대화 기록을 읽고, 사용자가 이미 말한 정보는 다시 묻지 마라.
2. 아직 모르는 것 중에서 '법적으로 가장 중요한 정보' 하나만 골라 물어라.
3. 법적 쟁점 가이드를 우선 활용해, 변호사가 실제로 던질 질문을 던져라.
   (예: 격락손해면 '쿼터패널 판금 포함 여부'를 물어라)
4. 질문은 반드시 한 문장으로만 출력하라. 목록, 번호, 설명, 답변은 금지.

아래는 지금까지의 대화 기록이다.
"""

# 요약 생성 시스템 프롬프트
SUMMARY_SYSTEM_PROMPT = """\
너는 법률사무소 상담 접수용 요약 에이전트다.
대화 기록을 읽고 아래 JSON 스키마로 요약해라. 법률 판단/조언을 절대 추가하지 마라.
JSON 키:
- summary: 사건 경위/상황을 간결한 문장으로
- field: 상담 분야 (가정/부동산/채권채무/형사/교통사고 중 하나, 없으면 null)
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
        # 법적 쟁점 질문이 길어질 수 있어 160토큰으로 설정
        return self._chat(messages, max_tokens=160)

    def summarize(self, history: list[dict]) -> dict:
        messages = [{"role": "system", "content": SUMMARY_SYSTEM_PROMPT}]
        messages.extend(history)
        raw = self._chat(messages)
        try:
            return self._parse_json_response(raw)
        except (ValueError, json.JSONDecodeError):
            # JSON 파싱 실패 시 fallback
            return {"summary": raw, "field": None, "position": None, "urgent": False}
