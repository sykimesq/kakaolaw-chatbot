from app.services.elicitation import (
    HARD_RULES,
    ElicitationService,
    detect_urgent,
    should_finish,
)
from app.services.llm_adapter import (
    ELICITATION_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    MockLLMAdapter,
)


def test_hard_rules_present():
    assert "상담 접수 상담사" in HARD_RULES
    assert "법률 답변·자문·예측·판단·전망을 절대 제공하지 마라" in HARD_RULES
    # 마감 시 변호사 상담 희망 여부를 묻는 규칙
    assert "변호사님과 직접 상담을 원하시면" in HARD_RULES


def test_hard_rules_요건사실론_4요소():
    """되묻기 프롬프트에 요건사실론 4요소 수집 구조가 명시돼야 한다."""
    for kw in ["① 의도", "② 권리근거사실", "③ 권리장애·소멸·저지사실", "④ 증빙·간접사실"]:
        assert kw in HARD_RULES


def test_elicitation_prompt_요건사실론_4요소():
    """LLM 되묻기 시스템 프롬프트에 요건사실론 4요소가 반영돼야 한다."""
    for kw in ["① 의도", "② 권리근거사실", "③ 권리장애·소멸·저지사실", "④ 증빙·간접사실"]:
        assert kw in ELICITATION_SYSTEM_PROMPT


def test_summary_prompt_요건사실론_스키마():
    """요약 프롬프트가 요건사실론 구조(intent/claim_facts 등)를 요구해야 한다."""
    for kw in ["intent", "claim_facts", "defense_facts", "evidence", "missing"]:
        assert kw in SUMMARY_SYSTEM_PROMPT


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
