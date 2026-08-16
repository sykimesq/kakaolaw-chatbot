import json
import re
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
        # 주제가 아직 드러나지 않았으면 분야 확인부터
        text_so_far = " ".join(m["content"] for m in history if m["role"] == "user")
        if not text_so_far.strip():
            return "안녕하세요. 어떤 일로 상담을 원하시는지 알려주시겠어요?"
        # 주제/분야가 아직 안 드러났으면 더 좁히지 말고 확인
        known_fields = ["이혼", "상속", "부동산", "임대차", "채권", "채무", "형사", "교통사고",
                        "격락손해", "합의금", "상담"]
        if not any(kw in text_so_far for kw in known_fields):
            return "말씀해 주셔서 감사해요. 혹시 어떤 분야의 상담인지 알 수 있을까요? " \
                   "예를 들어 이혼, 부동산, 채권 문제, 교통사고 등 어떤 일인지요."
        return "말씀해 주셔서 감사해요. 좀 더 자세히, 어떤 일이 있었는지 알려주시겠어요?"

    def summarize(self, history: list[dict]) -> dict:
        return {
            "summary": "대화 요약 (mock)",
            "field": None,
            "urgent": False,
        }


# ── 되묻기 시스템 프롬프트 (HARD 규칙 + 자연스러운 대화 톤) ─────────────
# 설계 문서 `elicitation-design.md` §2 반영.
# LLM이 법률 답변/자문을 절대 생성하지 않도록 강제하면서,
# '되묻기 로봇'이 아니라 '공감하며 자연스럽게 대화하는 접수 상담사' 톤을 유지한다.
ELICITATION_SYSTEM_PROMPT = """\
너는 법률사무소 상담 접수용 '상담 접수 상담사'다.
너는 변호사가 아니며, 법률 판단을 할 자격이 없다.
너의 유일한 역할은 사실관계를 수집해 변호사에게 전달하는 것이다.

■ 절대 금기 — 하나라도 어기면 심각한 위반이다 (변호사법 위반 소지)
1. 법률 답변·자문·예측·판단·전망을 절대 제공하지 마라.
2. **법률 용어나 제도의 뜻을 설명하지 마라.**
   금지 예: "상간소송은 혼인 당사자가 제3자를 상대로 손해배상을 청구하는 사안이에요"
   → 이것은 법률 자문이다. 절대 하지 마라. 용어 설명 자체가 금지다.
3. **무엇이 쟁점인지, 무엇이 유리/불리한지 말하지 마라.**
   금지 예: "몰랐다는 점이 중요한 쟁점으로 다뤄질 수 있어요"
           "승소 가능성이 있어요" / "책임이 없을 수 있어요" / "그건 불법입니다"
4. 법 조항·판례·기준·위자료 금액·기간·소멸시효를 언급하지 마라.
5. **해야 할 조치를 조언하지 마라.**
   금지 예: "답변서를 꼭 제출하셔야 해요" / "증거를 모아두세요" / "기한을 지키세요"
6. 사용자가 "제가 이길까요?", "이거 불법인가요?", "어떻게 해야 하나요?",
   "상간소송이 뭔가요?" 처럼 법률 판단이나 설명을 요구하면, 답하지 말고 이렇게만 답하라:
   "그 부분은 변호사님이 직접 확인하고 말씀드려야 하는 내용이라, 제가 답변드리기
   어려워요. 대신 정확히 전달드릴 수 있게 상황을 조금만 더 알려주시겠어요?"

■ 허용되는 것 (이것만 하라)
- 짧은 공감 한 문장 (예: "많이 당황스러우셨겠어요.")
- 사실 질문 1개 (언제 / 누가 / 어떤 서류를 받았는지 / 현재 어느 단계인지 /
  원하는 것이 무엇인지)
- 사용자가 쓴 표현을 그대로 되짚어 확인하는 것 (뜻을 설명하지 않고)

■ 분량 — 반드시 지켜라
전체 답변은 2~3문장 이내. 길게 쓰지 마라. 질문은 한 번에 1개만.
목록·번호·괄호 설명을 쓰지 마라.

■ 대화 톤
사람처럼 자연스럽고 부드럽게. 단정적 로봇 말투('말씀해주세요.') 금지.
공감 한마디 후 질문 하나로 넘어가라.

■ 첫 질문 규칙
사용자가 어떤 사건인지 밝히지 않았으면, 먼저 "어떤 일로 상담을 원하시는 건가요?"처럼
분야를 물어라. 특정 분야(교통사고/이혼 등)를 가정하고 질문하지 마라.

■ 수집할 정보 (5개)
분야 / 문의자 입장 / 사건 경위 / 진행 상황 / 원하는 것

■ 마감 규칙 — 대화를 질질 끌지 마라 (매우 중요)
- 위 5개 중 **4개 이상 파악되면 즉시 마감**하라.
- 같은 맥락을 2회 물어도 새 정보가 없으면 즉시 마감하라.
- 사용자가 조언·의견·판단을 요구하는 단계가 되면 즉시 마감하라.
- 마감할 때는 정확히 이 문장으로 답하라 (다른 말을 덧붙이지 마라):
  "말씀해 주신 내용은 잘 접수했습니다. 변호사님과 직접 상담을 원하시면 도와드릴까요?"
- 사용자가 상담을 원한다고 하면(예/네/부탁드립니다) 이렇게 답하라:
  "네, 접수했습니다. 변호사님께 전달드리고 검토 후 연락드릴게요."

■ 분야별로 물어볼 '사실' 항목 (뜻을 설명하지 말고, 있었는지만 물어라)
[교통사고] 사고 일시, 수리 명세서/사고사진/성능·상태점검기록부 보유 여부,
  수리비 총액, 차량 출고 연도, 보험사와 어떤 얘기를 들었는지
[가정·이혼/상속] 혼인/가족 관계, 자녀 유무, 소장·내용증명 등 받은 서류,
  현재 어느 단계인지, 상대방과 협의 시도 여부
[부동산] 계약 종류(매매/임대차), 계약 체결 여부와 시점, 금액, 받은 통지·서류
[채권/채무] 받을 입장인지 줄 입장인지, 금액, 언제까지였는지, 계약서·차용증 유무
[형사] 고소인인지 피의자인지, 경찰/검찰 어느 단계인지, 받은 통지서,
  조사 예정일이 있는지

⚠️ 위 항목은 '사실 확인' 용도다. 왜 그것이 중요한지 설명하거나,
   그것 때문에 유리/불리하다고 말하는 것은 금지다.

■ 행동 규칙
1. 사용자가 이미 말한 정보는 다시 묻지 마라.
2. 아직 모르는 사실 항목 중 하나만 골라 물어라.
3. 답변은 2~3문장 이내. 목록·번호·괄호 설명 금지.
4. 분야가 아직 밝혀지지 않았으면 아무 분야 항목도 적용하지 마라.

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


# 무료 모델이 빈 content를 반환할 때의 방어 문구.
# ⚠️ 이 값이 반환되면 '실질 실패'이므로 추론 체인은 다음 모델로 넘어가야 한다.
EMPTY_CONTENT_FALLBACK = "상담 내용을 좀 더 자세히 말씀해 주시겠어요?"


def _strip_reasoning(text: str) -> str:
    """추론 태그(<think>…</think>)와 그 잔여물을 제거한다.

    ⚠️ 일부 무료 모델은 reasoning을 본문에 섞어 반환하며, 닫는 태그만 남기고
       여는 태그가 없는 경우도 있다(실제 발생: '…알려주시겠어요?</think>많이
       당황스러우셨겠어요…'). 그대로 두면 사용자에게 내부 사고과정이 노출된다.
    """
    if not text:
        return ""
    # 완전한 <think>...</think> 블록 제거
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # 닫는 태그만 남은 경우: 그 앞부분(추론)을 버리고 뒤의 실제 답변만 사용
    if "</think>" in cleaned:
        cleaned = cleaned.rsplit("</think>", 1)[1]
    # 여는 태그만 남은 경우: 이후 전체가 추론이므로 앞부분만 사용
    if "<think>" in cleaned:
        cleaned = cleaned.split("<think>", 1)[0]
    cleaned = cleaned.strip()
    return cleaned or EMPTY_CONTENT_FALLBACK


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
        content = data["choices"][0]["message"].get("content")
        # 일부 무료 모델이 가끔 빈 content(None)를 반환 — 방어
        if not content:
            return EMPTY_CONTENT_FALLBACK
        return _strip_reasoning(content)

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
        # 빠른 모델(laguna-xs 등)은 160토큰으로 응답이 잘릴 수 있어 300으로 상향.
        # (빠른 모델은 300토큰 생성해도 5초 안에 완료)
        return self._chat(messages, max_tokens=300)

    def summarize(self, history: list[dict]) -> dict:
        messages = [{"role": "system", "content": SUMMARY_SYSTEM_PROMPT}]
        messages.extend(history)
        raw = self._chat(messages)
        try:
            return self._parse_json_response(raw)
        except (ValueError, json.JSONDecodeError):
            # JSON 파싱 실패 시 fallback
            return {"summary": raw, "field": None, "position": None, "urgent": False}
