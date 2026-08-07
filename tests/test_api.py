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


def test_elicit_turn_limit_completes():
    """되묻기 턴 한도(4턴) 도달 시 자동 '접수 완료' 응답."""
    from sqlmodel import Session, select

    from app.database import engine
    from app.models import ChatMessage

    user_key = "limit-user-001"
    last_response = ""
    for i in range(6):  # 6턴 전송
        r = client.post(
            "/chat/openbuilder",
            json={"userRequest": {"utterance": f"상담 {i}", "user": {"id": user_key}}},
        )
        assert r.status_code == 200
        body = r.json()
        text = body["template"]["outputs"][0]["simpleText"]["text"]
        last_response = text

    # 4턴 초과(5턴부터) 이후에는 '접수 완료' 메시지
    assert "접수했습니다" in last_response or "변호사가 검토" in last_response

    # DB에 메시지가 저장됐는지 확인 (user 6 + assistant 6 = 12)
    with Session(engine) as s:
        msgs = s.exec(
            select(ChatMessage).where(ChatMessage.user_key == user_key)
        ).all()
        assert len(msgs) == 12


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
