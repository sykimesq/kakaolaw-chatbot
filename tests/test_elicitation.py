from app.services.elicitation import (
    HARD_RULES,
    ElicitationService,
    detect_urgent,
    should_finish,
)
from app.services.llm_adapter import MockLLMAdapter


def test_hard_rules_present():
    assert "상담 접수 상담사" in HARD_RULES
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
