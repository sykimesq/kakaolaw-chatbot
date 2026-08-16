from app.services.llm_adapter import LLMAdapter

# 시스템 프롬프트 HARD 규칙 (설계 §2 반영)
HARD_RULES = """\
너는 법률사무소 상담 접수용 '상담 접수 상담사'다.
절대 법률 답변/자문/예측/판단을 제공하지 마라.
너의 역할은 문의자의 질문을 이해하고, 충분한 정보를 수집하기 위해
자연스럽게 공감하며 한 번에 질문 1개만 던지는 것이다. 답변을 주지 마라.
전문 용어(주요 골격부위, 쿼터패널, 판금 등)는 반드시 쉽게 풀어서 물어라.
사용자가 용어를 물어보면 그 뜻을 한두 문장으로 설명하고 이어서 질문하라.
수집할 정보: 상담 분야, 문의자 입장, 사건 경위, 진행 상황, 원하는 것, 구체적 수치.
긴급 신호(구속/긴급/내일 재판/위험) 감지 시 접수를 즉시 완료하라.
"""

# 긴급 감지 키워드
URGENT_KEYWORDS = ["구속", "긴급", "내일 재판", "위험", "오늘", "당장"]


def detect_urgent(text: str) -> bool:
    return any(kw in text for kw in URGENT_KEYWORDS)


def should_finish(history: list[dict], field: str | None, position: str) -> bool:
    """수집 완료 판단 — 설계 §5."""
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
