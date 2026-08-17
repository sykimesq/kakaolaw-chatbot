from fastapi.testclient import TestClient

from app.main import app
from app.routers import chat as chat_router

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_reset_command_clears_user_data():
    """채팅창에서 '/reset' 입력 시 해당 사용자의 대화·접수가 삭제된다."""
    from sqlmodel import Session, select

    from app.database import engine
    from app.models import ChatMessage, Inquiry

    user_key = "reset-cmd-001"
    # 먼저 대화 몇 턴 생성
    for i in range(3):
        r = client.post(
            "/chat/webhook",
            json={"utterance": f"테스트 {i}", "user_key": user_key},
        )
        assert r.status_code == 200

    # 대화가 저장됐는지 확인
    with Session(engine) as s:
        msgs = s.exec(select(ChatMessage).where(ChatMessage.user_key == user_key)).all()
        assert len(msgs) == 6  # user 3 + assistant 3

    # /reset 명령 → 즉시 리셋 응답, 저장 로직 없이 반환
    r = client.post("/chat/webhook", json={"utterance": "/reset", "user_key": user_key})
    assert r.status_code == 200
    body = r.json()
    assert body["reset"] is True
    assert "초기화" in body["response"]

    # 대화·접수가 모두 삭제됐는지 확인
    with Session(engine) as s:
        msgs = s.exec(select(ChatMessage).where(ChatMessage.user_key == user_key)).all()
        assert len(msgs) == 0
        inqs = s.exec(select(Inquiry).where(Inquiry.user_key == user_key)).all()
        assert len(inqs) == 0

    # 리셋 후 새 대화는 '새 상담'으로 시작 (이전 컨텍스트 없음)
    r2 = client.post("/chat/webhook", json={"utterance": "새 상담", "user_key": user_key})
    assert r2.status_code == 200
    with Session(engine) as s:
        msgs = s.exec(select(ChatMessage).where(ChatMessage.user_key == user_key)).all()
        assert len(msgs) == 2  # user 1 + assistant 1 (리셋 직후 1턴만)


def test_phone_collection_flow(monkeypatch):
    """상담 동의 후 연락처를 물어보고, 받으면 DB에 저장한다."""
    from sqlmodel import Session, select

    from app.database import engine
    from app.models import Inquiry

    user_key = "phone-flow-1"

    def _done(history):
        user_msgs = [m for m in history if m["role"] == "user"]
        if len(user_msgs) < 2:
            return "추가 질문입니다"
        return "말씀해 주신 내용은 잘 접수했습니다. 변호사님과 직접 상담을 원하시면 도와드릴까요?"

    monkeypatch.setattr(
        chat_router, "get_llm_adapter",
        lambda: type("T", (), {"next_question": lambda self, h: _done(h),
                               "summarize": lambda self, h: {}})(),
    )

    # 2턴째에 LLM이 마감 멘트(COMPLETE_MESSAGE) 반환
    r = client.post("/chat/webhook", json={"utterance": "첫", "user_key": user_key})
    assert "접수했습니다" not in r.json()["response"]
    r = client.post("/chat/webhook", json={"utterance": "둘", "user_key": user_key})
    assert "접수했습니다" in r.json()["response"]

    # 상담 동의 → 연락처 요청
    r2 = client.post("/chat/webhook", json={"utterance": "상담 원해요", "user_key": user_key})
    assert r2.json()["response"] == chat_router.ASK_PHONE_MESSAGE

    # 연락처 입력 → 최종 접수 완료 + DB에 저장
    r3 = client.post("/chat/webhook", json={"utterance": "010-1234-5678", "user_key": user_key})
    assert r3.json()["response"] == chat_router.CONSULT_ACCEPTED_MESSAGE

    with Session(engine) as s:
        inq = s.exec(select(Inquiry).where(Inquiry.user_key == user_key)).first()
        assert inq, "Inquiry가 저장되지 않음"
        assert inq.phone == "01012345678"  # 정규화된 전화번호


def test_phone_skip_flow(monkeypatch):
    """연락처를 거절하면 연락처 없이 마무리된다."""
    from sqlmodel import Session, select

    from app.database import engine
    from app.models import Inquiry

    user_key = "phone-skip-1"

    def _done(history):
        user_msgs = [m for m in history if m["role"] == "user"]
        if len(user_msgs) < 2:
            return "추가 질문입니다"
        return "말씀해 주신 내용은 잘 접수했습니다. 변호사님과 직접 상담을 원하시면 도와드릴까요?"

    monkeypatch.setattr(
        chat_router, "get_llm_adapter",
        lambda: type("T", (), {"next_question": lambda self, h: _done(h),
                               "summarize": lambda self, h: {}})(),
    )

    r = client.post("/chat/webhook", json={"utterance": "첫", "user_key": user_key})
    r = client.post("/chat/webhook", json={"utterance": "둘", "user_key": user_key})
    assert "접수했습니다" in r.json()["response"]

    # 상담 동의 → 연락처 요청
    r2 = client.post("/chat/webhook", json={"utterance": "상담 원해요", "user_key": user_key})
    assert r2.json()["response"] == chat_router.ASK_PHONE_MESSAGE

    # 연락처 거절
    r3 = client.post("/chat/webhook", json={"utterance": "없어요", "user_key": user_key})
    assert r3.json()["response"] == chat_router.PHONE_SKIPPED_MESSAGE

    with Session(engine) as s:
        inq = s.exec(select(Inquiry).where(Inquiry.user_key == user_key)).first()
        assert inq, "Inquiry가 저장되지 않음"
        # 연락처를 안 줬으므로 phone은 user_key 그대로
        assert inq.phone == user_key


def test_webhook_first_asks_field_when_unspecified():
    r = client.post(
        "/chat/webhook",
        json={"utterance": "안녕하세요", "user_key": "field-probe-1"},
    )
    assert r.status_code == 200
    text = r.json()["response"]
    # "안녕하세요" 한마디로 분야 미확인 상태 → 특정 분야를 가정하지 않아야 함
    assert "격락손해" not in text
    assert "수리" not in text
    # 분야 확인 질문이 포함되어야 함
    assert "어떤 일" in text or "상담" in text or "분야" in text
    r = client.post("/chat/webhook", json={"utterance": "이혼 문의", "user_key": "u1"})
    assert r.status_code == 200
    assert "response" in r.json()


def test_webhook_urgent():
    r = client.post("/chat/webhook", json={"utterance": "구속되었어요 긴급합니다"})
    assert r.status_code == 200
    assert r.json()["urgent"] is True


def test_openbuilder_webhook():
    """실제 오픈빌더 형식 요청 → 오픈빌더 형식 응답."""
    r = client.post(
        "/chat/openbuilder",
        json={
            "userRequest": {
                "utterance": "이혼 문의",
                "user": {"id": "kakao-user-123"},
            }
        },
    )
    assert r.status_code == 200
    body = r.json()
    # 오픈빌더 응답 형식 검증
    assert body["version"] == "2.0"
    assert body["template"]["outputs"][0]["simpleText"]["text"]
    # 사용자 키 추출 확인 (접수 DB에 저장됐는지는 별개 — 여기선 응답 형식만)
    assert "simpleText" in body["template"]["outputs"][0]


def test_conversation_history_persists():
    """같은 user_key로 연속 발화 시 이전 대화가 컨텍스트로 유지되는지 확인.

    mock LLM은 히스토리 길이를 응답으로 돌려주도록 검증 (DB에 메시지 누적 확인).
    """
    # 같은 user_key로 3번 연속 메시지
    user_key = "conv-user-001"
    for i in range(3):
        r = client.post(
            "/chat/openbuilder",
            json={"userRequest": {"utterance": f"메시지 {i}", "user": {"id": user_key}}},
        )
        assert r.status_code == 200

    # DB에 메시지가 저장됐는지 ChatMessage를 직접 조회
    from sqlmodel import Session, select

    from app.database import engine
    from app.models import ChatMessage

    with Session(engine) as s:
        msgs = s.exec(
            select(ChatMessage).where(ChatMessage.user_key == user_key)
        ).all()
        # user 3 + assistant 3 = 6개
        assert len(msgs) == 6
        # 순서 확인: 첫 user 메시지가 먼저
        assert msgs[0].role == "user"
        assert msgs[0].content == "메시지 0"


def test_conversation_continues_without_turn_limit():
    """턴 한도가 없어도 LLM이 계속 질문하면 대화가 무한정 이어진다.

    요건사실 수집이 완료될 때까지 질문하므로, LLM이 '접수했습니다'를 반환하기
    전에는 턴 수와 무관하게 대화가 계속된다. (강제 종료 없음)
    """
    from sqlmodel import Session, select

    from app.database import engine
    from app.models import ChatMessage

    user_key = "limit-user-001"
    for i in range(10):  # 이전 턴 한도(6)를 넘는 10턴
        r = client.post(
            "/chat/openbuilder",
            json={"userRequest": {"utterance": f"상담 {i}", "user": {"id": user_key}}},
        )
        assert r.status_code == 200
        body = r.json()
        text = body["template"]["outputs"][0]["simpleText"]["text"]
        # 턴 수와 무관하게 계속 질문 응답 (접수 완료로 끊기지 않음)
        assert "접수했습니다" not in text

    # DB에 메시지가 저장됐는지 확인 (user 10 + assistant 10 = 20)
    with Session(engine) as s:
        msgs = s.exec(
            select(ChatMessage).where(ChatMessage.user_key == user_key)
        ).all()
        assert len(msgs) == 20


def test_completion_when_llm_returns_접수했습니다(monkeypatch):
    """LLM이 요건사실 수집 완료로 '접수했습니다'를 반환하면 즉시 종료된다.

    턴 한도가 사라진 뒤의 유일한 종료 경로 중 하나. (LLM 마무리 감지)
    """
    from sqlmodel import Session, select

    from app.database import engine
    from app.models import ChatMessage

    user_key = "llm-done-001"

    def _done(history):
        # 질문을 몇 번 하다가 수집 완료 신호를 반환
        user_msgs = [m for m in history if m["role"] == "user"]
        if len(user_msgs) < 2:
            return "추가 질문입니다"
        return "말씀해 주신 내용은 잘 접수했습니다. 변호사님과 직접 상담을 원하시면 도와드릴까요?"

    monkeypatch.setattr(
        chat_router, "get_llm_adapter",
        lambda: type("T", (), {"next_question": lambda self, h: _done(h),
                               "summarize": lambda self, h: {}})(),
    )

    # 2턴째부터 접수 완료
    r = client.post("/chat/webhook", json={"utterance": "첫 질문", "user_key": user_key})
    assert "접수했습니다" not in r.json()["response"]
    r2 = client.post("/chat/webhook", json={"utterance": "두번째", "user_key": user_key})
    assert "접수했습니다" in r2.json()["response"]

    with Session(engine) as s:
        msgs = s.exec(
            select(ChatMessage).where(ChatMessage.user_key == user_key)
        ).all()
        assert len(msgs) == 4  # user 2 + assistant 2


def test_turn_reset_after_completion(monkeypatch):
    """접수 완료 후 새 대화 시작 시 새 세션으로 동작한다.

    LLM이 '접수했습니다'로 마감한 뒤, 다음 메시지는 새 상담으로 처리돼
    즉시 종료되지 않는다. (과거 턴 카운트 누적 문제 제거 후 검증)
    """
    from sqlmodel import Session, select

    from app.database import engine
    from app.models import Inquiry, InquiryStatus

    user_key = "reset-user-001"

    def _done(history):
        # 마지막 "접수했습니다" 이후의 user 메시지만 센다 (새 세션 재개)
        count = 0
        for m in reversed(history):
            if m["role"] == "assistant" and "접수했습니다" in m["content"]:
                break
            if m["role"] == "user":
                count += 1
        if count < 2:
            return "추가 질문입니다"
        return "말씀해 주신 내용은 잘 접수했습니다. 변호사님과 직접 상담을 원하시면 도와드릴까요?"

    monkeypatch.setattr(
        chat_router, "get_llm_adapter",
        lambda: type("T", (), {"next_question": lambda self, h: _done(h),
                               "summarize": lambda self, h: {}})(),
    )

    # 2턴째에 접수 완료
    r = client.post("/chat/webhook", json={"utterance": "첫", "user_key": user_key})
    assert "접수했습니다" not in r.json()["response"]
    r = client.post("/chat/webhook", json={"utterance": "둘", "user_key": user_key})
    assert "접수했습니다" in r.json()["response"]

    # Inquiry가 완료 상태로 저장됐는지 확인
    with Session(engine) as s:
        inq = s.exec(select(Inquiry).where(Inquiry.user_key == user_key)).first()
        assert inq and inq.status == InquiryStatus.COMPLETED

    # 접수 완료 이후 새 메시지 — 새 세션 1턴째이므로 질문 응답
    r2 = client.post("/chat/webhook", json={"utterance": "새로운 상담입니다", "user_key": user_key})
    text = r2.json()["response"]
    assert "접수했습니다" not in text


def test_create_reservation():
    r = client.post(
        "/chat/reservations",
        json={
            "name": "김",
            "phone": "01012345678",
            "field": "가정",
            "desired_dt": "8/12 14:00",
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "대기"


def test_reservation_confirm_404():
    r = client.post("/admin/reservations/999/confirm")
    assert r.status_code == 404


def test_reservation_confirm_flow():
    r = client.post(
        "/chat/reservations",
        json={
            "name": "박",
            "phone": "01011112222",
            "field": "부동산",
            "desired_dt": "8/13 10:00",
        },
    )
    rid = r.json()["id"]
    r2 = client.post(f"/admin/reservations/{rid}/confirm")
    assert r2.status_code == 200
    assert r2.json()["status"] == "확정"
