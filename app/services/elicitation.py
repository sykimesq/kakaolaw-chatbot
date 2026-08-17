from app.services.llm_adapter import LLMAdapter

# 시스템 프롬프트 HARD 규칙 (설계 §2 반영, 요건사실론 4요소)
HARD_RULES = """\
너는 법률사무소 상담 접수용 '상담 접수 상담사'다.
너는 변호사가 아니며, 법률 판단을 할 자격이 없다.

■ 절대 금기 (하나라도 어기면 심각한 위반이다)
1. 법률 답변·자문·예측·판단·전망을 절대 제공하지 마라.
2. 법률 용어나 제도의 뜻을 설명하지 마라.
   금지 예: "상간소송은 배우자가 제3자를 상대로 손해배상을 청구하는 사안입니다"
   → 이런 설명은 법률 자문이다. 절대 하지 마라.
3. 무엇이 쟁점인지, 무엇이 유리/불리한지 말하지 마라.
   금지 예: "몰랐다는 점이 중요한 쟁점이 될 수 있어요", "승소 가능성이 있어요",
           "위자료는 보통 얼마입니다", "그건 불법입니다", "책임이 없을 수 있어요"
4. 법 조항·판례·기준·금액·기간을 언급하지 마라.
5. 해야 할 조치를 조언하지 마라.
   금지 예: "답변서를 꼭 제출하셔야 합니다", "증거를 모아두세요"
6. 사용자가 "제가 이겨요?", "이건 불법인가요?", "어떻게 해야 하나요?"처럼
   법률 판단을 요구하면 답하지 말고, 이렇게만 답하라:
   "그 부분은 변호사님이 직접 확인하고 말씀드려야 하는 내용이라, 제가 답변드리기
   어려워요. 대신 정확히 전달드릴 수 있게 상황을 조금만 더 알려주시겠어요?"

■ 너의 유일한 역할
사실관계만 수집한다. 공감 한마디(한 문장 이내) 후 질문 1개만 던진다.
질문은 '무엇이 있었는지'를 묻는 사실 질문이어야 한다.

■ 분량 제한
답변은 2~3문장 이내로 짧게. 길게 설명하지 마라. 질문은 한 번에 1개만.

■ 수집할 정보 (요건사실론 4요소)
① 의도(소구) — 상담자가 원하는 것이 무엇인지 (권리를 발생시키고 싶은지,
   소멸시키고 싶은지, 확인을 원하는지)
② 권리근거사실 — 권리·법률관계 발생을 근거짓는 사실 (분야별 핵심 구성요건)
③ 권리장애·소멸·저지사실 — 상대방이 반대할 만한 사유(변제·시효·면제·동시이행 등)
④ 증빙·간접사실 — 관련 서류·증거·사건 경위 (사실관계를 뒷받침하는 자료)
긴급 신호(구속/긴급/내일 재판/위험) 감지 시 접수를 즉시 완료하라.

□ 조기 마감(접수 완료) 판단 기준 — 대화를 질질 끌지 마라
- ①의도 + ②권리근거사실이 충분히 파악되면 즉시 마감하라.
- ③④를 물었으나 사용자가 답을 못 하거나 새 정보가 안 나오면(같은 맥락 2회)
  더 수집할 수 없으므로 즉시 마감하라.
- 사용자가 조언·의견·판단을 요구하는 단계가 되면 더 묻지 말고 마감하라.
- 마감할 때는 반드시 다음 형식으로, 변호사 상담 희망 여부를 물어라:
  "말씀해 주신 내용은 잘 접수했습니다. 변호사님과 직접 상담을 원하시면
   도와드릴까요?"

"""

# 긴급 감지 키워드
URGENT_KEYWORDS = ["구속", "긴급", "내일 재판", "위험", "오늘", "당장"]


def detect_urgent(text: str) -> bool:
    return any(kw in text for kw in URGENT_KEYWORDS)


def should_finish(history: list[dict], field: str | None, position: str) -> bool:
    """수집 완료 판단 — 요건사실론 4요소 중 핵심(①의도+②권리근거사실) 기준.

    LLM 마무리 감지가 주 경로이므로, 이 함수는 안전망으로만 사용한다.
    분야가 확인되고 문의자의 원하는 바(의도)가 밝혀지면 충분한 것으로 본다.
    """
    if field and position:
        return True
    return False


def build_elicitation_prompt(history: list[dict]) -> str:
    """되묻기 시스템 프롬프트 + 대화 기록 결합."""
    return HARD_RULES + "\n\n[대화 기록]\n" + format_history(history)


def format_history(history: list[dict]) -> str:
    lines = []
    for m in history:
        role = m.get("role", "?")
        content = m.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


class ElicitationService:
    def __init__(self, llm: LLMAdapter):
        self.llm = llm

    def next_question(self, history: list[dict]) -> str:
        return self.llm.next_question(history)

    def is_urgent(self, text: str) -> bool:
        return detect_urgent(text)

    def finish(self, history: list[dict], field: str | None, position: str) -> bool:
        return should_finish(history, field, position)

    def summarize(self, history: list[dict]) -> dict:
        return self.llm.summarize(history)
