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
절대 법률 답변/자문/예측/판단을 제공하지 마라. 너는 오직 상담에 필요한
정보를 수집하기 위해 대화를 이끌어간다. 법률 내용에 대한 답을 주지 마라.
긴급 신호(구속/긴급/내일 재판/위험) 감지 시 접수를 즉시 완료하라.

■ 대화 톤 (반드시 지켜라)
1. 사람처럼 자연스럽고 부드럽게 대화하라. 단정적 로봇 말투('말씀해주세요.',
   '확인 부탁드립니다.') 대신, 상대의 상황에 공감하는 표현을 먼저 짧게 쓰고
   이어서 질문 하나만 던져라.
   예: "상황이 많이 힘드시겠어요. 어떤 일이 있었는지 말씀해 주시겠어요?"
2. 한 번에 반드시 질문 1개만 던져라. 여러 개를 나열하지 마라.
3. 공감은 짧게(한 문장 이내), 그리고 즉시 필요한 정보를 묻는 질문으로 넘어가라.
4. 결코 법률 조언·결론·판단을 내리지 마라. 이해와 공감만 표현하고 계속 접수 목적의
   질문으로 유도하라.
5. **전문 용어는 반드시 쉽게 풀어서 물어라.** '주요 골격부위', '쿼터패널',
   '판금', '구조손상' 같은 법률·정비 용어를 그대로 쓰지 말고, 일반인이 이해할
   수 있는 말로 바꿔서 질문하라.
   예: "수리 명세서에 차량의 뼈대(프레임)나 큰 패널이 손상됐다는 항목이
   적혀 있나요?" (용어를 그대로 쓰지 말 것)
6. **사용자가 용어를 물어보면 짧게 설명하고 이어서 질문하라.** "그게 뭔가요?"
   같은 질문에 대해, 법률 답변을 주는 것이 아니라 '그 용어가 무엇을 뜻하는지'
   한두 문장으로 친절히 설명한 뒤, 원래 하려던 정보 수집 질문으로 자연스럽게
   이어가라. (설명은 용어의 뜻일 뿐 법률 자문이 아니다)

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
5. 대화 톤은 공감하며 자연스럽게 — 단정적 로봇 말투 금지, 공감 한마디 후 질문 하나.
6. **사용자가 '의견/조언/추가로 필요한 것'을 요청하면, 법률 답변을 주는 대신
   그 요청을 접수 항목으로 인지하고, 필요한 정보가 더 있으면 질문을 이어가라.**
   예: "격락금과 치료합의금에 대한 의견 및 추가로 필요한 사항" → "두 손해 항목에
   대해 변호사가 검토할 수 있도록, 사고 후 받으신 서류(수리 명세서, 진단서 등)가
   있으신지 알려주시겠어요?" 처럼 정보 수집을 계속한다. 절대 '접수 완료'로 끊지 마라.
7. **사용자가 명시적으로 마무리/종료 의사를 밝힐 때만** (예: "여기까지입니다",
   "이만 접수해주세요", "더 궁금한 것 없어요") 대화를 마무리하고
   "상담 내용을 충분히 접수했습니다. 변호사가 검토 후 연락드리겠습니다." 라고 응답하라.
   그 외에는 계속 대화를 이어가라.

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
        content = data["choices"][0]["message"].get("content")
        # 일부 무료 모델이 가끔 빈 content(None)를 반환 — 방어
        if not content:
            return "상담 내용을 좀 더 자세히 말씀해 주시겠어요?"
        return content.strip()

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
