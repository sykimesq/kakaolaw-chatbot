"""법률 판단 발화 차단(legal_guard) + 대화 마감 흐름 테스트.

⚠️ 이 테스트는 변호사법 위반 방지를 위한 것이므로 절대 느슨하게 만들지 말 것.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.routers import chat as chat_router
from app.services.legal_guard import SAFE_REPLACEMENT, find_violation, sanitize

client = TestClient(app)


# 실제로 추론 모델이 생성했던 위반 발화 + 대표적 법률 자문 패턴
FORBIDDEN_SAMPLES = [
    # 2026-08-16 실제 발생 사례
    "상간소송은 혼인 관계의 당사자가 배우자 외 제3자를 상대로 손해배상을 "
    "청구하는 사안인데, 혼인한 사람인 줄 모르고 만났다는 점이 중요한 쟁점 중 "
    "하나로 다뤄질 수 있어요.",
    "몰랐다는 점이 인정되면 책임이 없을 수 있습니다.",
    "승소 가능성이 높아 보입니다.",
    "그건 불법입니다.",
    "답변서를 반드시 제출하셔야 합니다.",
    "위자료는 보통 2천만원 정도입니다.",
    "민법 제750조에 따라 손해배상 책임이 발생합니다.",
    "증거를 수집해야 합니다.",
    "소멸시효가 지났을 수 있어요.",
    "법적으로 유리한 상황입니다.",
]

# 접수 상담사가 해도 되는 안전한 발화 (오탐이 나면 안 됨)
ALLOWED_SAMPLES = [
    "많이 당황스러우셨겠어요. 소장은 언제 받으셨나요?",
    "어떤 일로 상담을 원하시는 건가요?",
    "많이 답답하시겠어요. 계약서는 가지고 계신가요?",
    "말씀해 주신 내용은 잘 접수했습니다. "
    "변호사님과 직접 상담을 원하시면 도와드릴까요? "
    "원하시면 '상담 원해요'라고 말씀해 주세요.",
    "네, 접수했습니다. 변호사님께 전달드리고 검토 후 연락드릴게요. 감사합니다.",
    SAFE_REPLACEMENT,
    "지금 경찰 조사는 어느 단계까지 진행되었나요?",
    "수리 명세서를 받아 보셨나요?",
    # 분야 확인 질문 — 사건 유형을 되짚는 것은 법률 판단이 아니다 (오탐 방지)
    "그 분야가 가정·이혼 소송이라고 보는데, 맞으신가요?",
    "말씀해 주신 내용이 부동산 관련 상담이라고 보면 될까요?",
]


def test_forbidden_legal_advice_is_detected():
    """법률 판단/자문 발화는 모두 차단되어야 한다."""
    for sample in FORBIDDEN_SAMPLES:
        assert find_violation(sample) is not None, f"미탐: {sample}"


def test_allowed_utterances_pass():
    """접수 목적의 사실 질문/공감/마감 멘트는 차단되지 않아야 한다."""
    for sample in ALLOWED_SAMPLES:
        assert find_violation(sample) is None, f"오탐: {sample}"


def test_sanitize_replaces_violation():
    """위반 발화는 안전 문구로 교체된다."""
    assert sanitize(FORBIDDEN_SAMPLES[0]) == SAFE_REPLACEMENT
    # 안전한 발화는 그대로 통과
    safe = "많이 당황스러우셨겠어요. 소장은 언제 받으셨나요?"
    assert sanitize(safe) == safe


def test_webhook_blocks_legal_advice_from_llm(monkeypatch):
    """LLM이 법률 자문을 생성해도 사용자에게 전달되지 않는다 (엔드투엔드).

    프롬프트를 무시하는 모델을 시뮬레이션 — 안전망이 최후에 막아야 한다.
    """
    monkeypatch.setattr(
        chat_router,
        "get_llm_adapter",
        lambda: type(
            "Rogue",
            (),
            {
                "next_question": lambda self, h: FORBIDDEN_SAMPLES[0],
                "summarize": lambda self, h: {},
            },
        )(),
    )
    r = client.post(
        "/chat/webhook",
        json={"utterance": "상간소송 당했습니다", "user_key": "guard-e2e-1"},
    )
    assert r.status_code == 200
    text = r.json()["response"]
    assert text == SAFE_REPLACEMENT
    assert "쟁점" not in text


def test_consult_accept_completes_immediately(monkeypatch):
    """마감 멘트 후 사용자가 상담을 원하면 LLM 호출 없이 즉시 종료된다."""
    calls = []

    def _tracked(history):
        calls.append(1)
        # 첫 턴은 질문, 이후 LLM 마무리 감지로 "접수했습니다" 마감 멘트 반환
        user_msgs = [m for m in history if m["role"] == "user"]
        if len(user_msgs) < 2:
            return "추가 질문입니다"
        return "말씀해 주신 내용은 잘 접수했습니다. 변호사님과 직접 상담을 원하시면 도와드릴까요?"

    monkeypatch.setattr(
        chat_router,
        "get_llm_adapter",
        lambda: type(
            "T", (), {"next_question": lambda self, h: _tracked(h),
                      "summarize": lambda self, h: {}}
        )(),
    )
    user_key = "consult-accept-1"
    # 두 번째 턴에서 LLM이 마감 멘트를 반환하도록 유도
    for i in range(2):
        r = client.post(
            "/chat/webhook",
            json={"utterance": f"상담 {i}", "user_key": user_key},
        )
    assert "변호사님과 직접 상담을 원하시면" in r.json()["response"]

    before = len(calls)
    r2 = client.post(
        "/chat/webhook", json={"utterance": "상담 원해요", "user_key": user_key}
    )
    text = r2.json()["response"]
    # 상담 동의 → 연락처 요청 (LLM 호출 없이 즉시)
    assert text == chat_router.ASK_PHONE_MESSAGE
    # LLM을 추가로 호출하지 않았는지 확인
    assert len(calls) == before

    # 연락처를 주면 최종 접수 완료
    r3 = client.post(
        "/chat/webhook", json={"utterance": "010-1234-5678", "user_key": user_key}
    )
    assert r3.json()["response"] == chat_router.CONSULT_ACCEPTED_MESSAGE


def test_bare_yes_without_offer_is_not_completion():
    """마감 멘트가 없었는데 '네'만 오면 종료로 오판하지 않는다."""
    r = client.post(
        "/chat/webhook", json={"utterance": "네", "user_key": "bare-yes-1"}
    )
    assert r.json()["response"] != chat_router.CONSULT_ACCEPTED_MESSAGE


def test_reasoning_tags_are_stripped():
    """추론 태그(<think>)가 사용자 응답에 노출되지 않는다.

    ⚠️ 실제 발생: 닫는 태그만 남아 내부 사고과정이 그대로 전달됐다.
    """
    from app.services.llm_adapter import _strip_reasoning

    # 완전한 블록
    assert _strip_reasoning("<think>내부 추론</think>실제 답변입니다") == "실제 답변입니다"
    # 닫는 태그만 남은 경우 (실제 발생 패턴)
    assert (
        _strip_reasoning("추론 중입니다…</think>많이 당황스러우셨겠어요.")
        == "많이 당황스러우셨겠어요."
    )
    # 여는 태그만 남은 경우
    assert _strip_reasoning("실제 답변입니다<think>이후 추론") == "실제 답변입니다"
    # 태그가 없으면 그대로
    assert _strip_reasoning("  평범한 답변  ") == "평범한 답변"
    # 태그를 걷어내 빈 문자열이 되면 방어 문구
    from app.services.llm_adapter import EMPTY_CONTENT_FALLBACK

    assert _strip_reasoning("<think>추론만</think>") == EMPTY_CONTENT_FALLBACK
