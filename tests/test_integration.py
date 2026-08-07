from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_full_flow():
    # 1. 웹훅으로 질의 접수
    r = client.post(
        "/chat/webhook",
        json={"utterance": "이혼 문의", "user_key": "u1"},
    )
    assert r.status_code == 200
    assert "response" in r.json()

    # 2. 예약 생성
    r = client.post(
        "/chat/reservations",
        json={
            "name": "테스트",
            "phone": "01099998888",
            "field": "형사",
            "desired_dt": "8/15 11:00",
        },
    )
    assert r.status_code == 200
    rid = r.json()["id"]

    # 3. 관리자 API 동작
    r = client.get("/admin/reservations")
    assert r.status_code == 200
    assert len(r.json()) >= 1

    # 4. 확정 처리
    r = client.post(f"/admin/reservations/{rid}/confirm")
    assert r.status_code == 200
    assert r.json()["status"] == "확정"

    # 5. 질의 목록
    r = client.get("/admin/inquiries")
    assert r.status_code == 200


def test_admin_page_loads():
    r = client.get("/admin")
    assert r.status_code == 200
    assert "법률사무소 관리자" in r.text
