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
