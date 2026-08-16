from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_webhook():
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


def test_conversation_continues_beyond_turn_limit():
    """턴 한도(12) 이내에서는 대화가 계속된다 (사용자 마무리 전 강제 종료 없음).

    mock LLM은 항상 질문을 반환하므로, 턴 한도 이내에서는 '접수 완료'로 끊기지 않고
    계속 질문 응답이 나와야 한다. (사용자가 마무리 의사를 밝힐 때만 종료)
    """
    from sqlmodel import Session, select

    from app.database import engine
    from app.models import ChatMessage

    user_key = "limit-user-001"
    for i in range(10):  # 10턴 전송 (턴 한도 12 이내)
        r = client.post(
            "/chat/openbuilder",
            json={"userRequest": {"utterance": f"상담 {i}", "user": {"id": user_key}}},
        )
        assert r.status_code == 200
        body = r.json()
        text = body["template"]["outputs"][0]["simpleText"]["text"]
        # 턴 한도 이내에서는 계속 질문 응답 (접수 완료로 끊기지 않음)
        assert "접수했습니다" not in text

    # DB에 메시지가 저장됐는지 확인 (user 10 + assistant 10 = 20)
    with Session(engine) as s:
        msgs = s.exec(
            select(ChatMessage).where(ChatMessage.user_key == user_key)
        ).all()
        assert len(msgs) == 20


def test_turn_limit_completes_after_max():
    """턴 한도(12)를 넘으면 LLM 호출 없이 즉시 '접수 완료'로 전환 (timeout 안전).

    대화가 길어져 히스토리가 커지면 LLM 생성이 5초를 넘길 수 있으므로,
    턴 한도 초과 시 고정 응답을 즉시 반환한다.
    """
    from sqlmodel import Session, select

    from app.database import engine
    from app.models import ChatMessage

    user_key = "limit-user-002"
    # 턴 한도(12) + 1 = 13턴 전송
    for i in range(13):
        r = client.post(
            "/chat/openbuilder",
            json={"userRequest": {"utterance": f"상담 {i}", "user": {"id": user_key}}},
        )
        assert r.status_code == 200
        body = r.json()
        text = body["template"]["outputs"][0]["simpleText"]["text"]
        if i < 12:
            # 한도 이내: 계속 질문 응답
            assert "접수했습니다" not in text
        else:
            # 한도 초과(13번째): 즉시 접수 완료
            assert "접수했습니다" in text


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
