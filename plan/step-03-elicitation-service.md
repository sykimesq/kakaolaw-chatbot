# Step 03: LLM 되묻기 서비스 (어댑터 + mock)

## 목표
법률 질의에 대해 "되묻기 에이전트"로만 동작하는 LLM 서비스와, 테스트 가능한 mock 어댑터를 생성한다.

## 사전 조건
- [ ] Step 02 완료 (`app/models.py` 존재)
- [ ] 설계: `2026-08-07-kakao-law-chatbot-elicitation-design.md` (§2 HARD 규칙)

## 변경할 파일
- 생성: `app/services/__init__.py`
- 생성: `app/services/llm_adapter.py` (인터페이스 + mock)
- 생성: `app/services/elicitation.py` (되묻기 로직)
- 생성: `tests/test_elicitation.py` (테스트)

## 구현 내용

### 1. `app/services/llm_adapter.py` — LLM 어댑터

```python
from abc import ABC, abstractmethod

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
```

### 2. `app/services/elicitation.py` — 되묻기 로직

되묻기 흐름 관리 + 완료 판단 + 긴급 감지 + 질의 요약 생성을 담당.

```python
from app.services.llm_adapter import LLMAdapter

# 시스템 프롬프트 HARD 규칙 (설계 §2 반영)
HARD_RULES = """
너는 법률사무소 상담 접수용 '되묻기 에이전트'다.
절대 법률 답변/자문/예측/판단을 제공하지 마라.
너의 역할은 문의자의 질문을 이해하고, 충분한 정보를 수집하기 위해
한 번에 질문 1개만 던지는 것이다. 답변을 주지 마라.
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
```

### 3. `tests/test_elicitation.py`

```python
from app.services.elicitation import (
    ElicitationService, detect_urgent, should_finish,
    HARD_RULES,
)
from app.services.llm_adapter import MockLLMAdapter

def test_hard_rules_present():
    assert "되묻기 에이전트" in HARD_RULES
    assert "답변을 주지 마라" in HARD_RULES

def test_detect_urgent():
    assert detect_urgent("구속되었어요")
    assert detect_urgent("긴급합니다")
    assert not detect_urgent("평범한 문의입니다")

def test_should_finish():
    assert should_finish([], "가정", "당사자")
    assert not should_finish([], None, "")

def test_elicitation_next_question():
    svc = ElicitationService(MockLLMAdapter())
    q = svc.next_question([{"role": "user", "content": "이혼 문의"}])
    assert isinstance(q, str) and len(q) > 0
```

## 검증
```bash
python -m pytest tests/test_elicitation.py -q
```

## 완료 조건
- [ ] 어댑터/서비스 import 성공
- [ ] 긴급 감지 동작
- [ ] 완료 판단 동작
- [ ] pytest 통과
