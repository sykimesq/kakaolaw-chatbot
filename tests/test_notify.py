"""접수 완료 시 변호사 전달 파이프라인 테스트.

⚠️ 이 테스트 없이는 '접수했습니다'라고만 하고 실제 전달이 안 되는
   치명적 누락을 잡지 못한다.
"""

from fastapi.testclient import TestClient

from app import database
from app.main import app
from app.models import Inquiry
from app.routers import chat as chat_router


def _client():
    database.init_db()
    return TestClient(app)


def _force_completion(monkeypatch, user_key: str, turns: int = 1):
    """LLM이 turns 턴 후 '접수했습니다' 마감 멘트를 반환하도록 주입.

    턴 한도가 제거된 뒤, 접수 완료는 LLM 마무리 감지로만 이뤄지므로
    마감 유도에 사용한다.
    """
    def _next(history):
        user_msgs = [m for m in history if m["role"] == "user"]
        if len(user_msgs) < turns:
            return "추가 질문입니다"
        return "말씀해 주신 내용은 잘 접수했습니다. 변호사님과 직접 상담을 원하시면 도와드릴까요?"

    monkeypatch.setattr(
        chat_router,
        "get_llm_adapter",
        lambda: type(
            "T", (), {
                "next_question": lambda self, h: _next(h),
                "summarize": lambda self, h: {},
            }
        )(),
    )


def test_inquiry_saved_with_transcript_on_completion(monkeypatch):
    """접수 완료 시 Inquiry가 대화 전문(transcript)과 함께 저장된다."""
    from sqlmodel import Session, select

    _force_completion(monkeypatch, "notify-flow-1", turns=1)
    c = _client()
    uk = "notify-flow-1"
    # 첫 턴에 LLM이 마감 멘트 반환 (요건사실 충분 → 접수 완료)
    r = c.post(
        "/chat/webhook",
        json={"utterance": "상담내용 0", "user_key": uk},
    )
    assert r.status_code == 200
    assert "접수했습니다" in r.json()["response"]

    with Session(database.engine) as s:
        inq = s.exec(
            select(Inquiry).where(Inquiry.user_key == uk)
        ).all()
        assert inq, "접수 완료되었는데 Inquiry가 저장되지 않음"
        saved = inq[0]
        assert "상담내용 0" in saved.transcript
        # ⚠️ transcript는 방금 생성한 챗봇 응답(상담사:)까지 포함해야 한다.
        #    (history에 assistant 응답이 아직 없어 누락되면 관리자 페이지에서
        #     대화가 상담자 메시지에서 끝나 잘려 보인다 — #151 사례)
        assert "상담사: " in saved.transcript
        assert saved.status.value in ("완료", "긴급")


def test_admin_page_lists_inquiry(monkeypatch):
    """관리자 페이지(/admin/inquiries)가 접수 내역을 노출한다."""

    _force_completion(monkeypatch, "notify-admin-1", turns=1)
    c = _client()
    uk = "notify-admin-1"
    c.post(
        "/chat/webhook",
        json={"utterance": "테스트 0", "user_key": uk},
    )
    res = c.get("/admin/inquiries")
    assert res.status_code == 200
    data = res.json()
    assert any(d["user_key"] == uk and d["transcript"] for d in data)


def test_admin_detail_returns_transcript(monkeypatch):
    """관리자 상세 API가 전체 대화 전문을 반환한다."""
    from sqlmodel import Session, select

    _force_completion(monkeypatch, "notify-detail-1", turns=1)
    c = _client()
    uk = "notify-detail-1"
    c.post(
        "/chat/webhook",
        json={"utterance": "디테일 0", "user_key": uk},
    )
    with Session(database.engine) as s:
        inq = s.exec(select(Inquiry).where(Inquiry.user_key == uk)).first()
        iid = inq.id

    res = c.get(f"/admin/inquiries/{iid}")
    assert res.status_code == 200
    body = res.json()
    assert "디테일 0" in body["transcript"]


def test_notify_called_on_completion(monkeypatch):
    """접수 완료 시 알림 채널(notify_lawyer)이 호출된다."""
    import app.services.notify as notify

    calls = []
    monkeypatch.setattr(
        notify, "notify_lawyer",
        lambda iid, summary, urgent, phone=None: (
            calls.append((iid, summary, urgent, phone)) or {"admin_page": "stored"}
        ),
    )
    _force_completion(monkeypatch, "notify-hook-1", turns=1)
    c = _client()
    uk = "notify-hook-1"
    c.post("/chat/webhook", json={"utterance": "x0", "user_key": uk})
    # 백그라운드 스레드가 실행될 시간 대기
    import time
    # Thread가 commit할 여유를 충분히 확보 (기본 스레드 scheduler 지연 대비)
    deadline = time.time() + 3.0
    while time.time() < deadline and not calls:
        time.sleep(0.1)
    assert calls, "접수 완료되었는데 알림(notify_lawyer)이 호출되지 않음"
    assert calls[0][2] in (True, False)


def test_notify_message_includes_요건사실론():
    """알림 본문에 요건사실론 구조(의도/권리근거사실 등)가 반영돼야 한다."""
    import app.services.notify as notify

    msg = notify._format_message(
        7,
        {
            "field": "교통사고",
            "position": "당사자",
            "intent": "손해배상 청구",
            "claim_facts": "상대 과실로 사고, 쿼터패널 판금 수리",
            "defense_facts": "상대방이 격락손해 부인",
            "evidence": "수리 명세서 보유",
            "missing": "차량 출고 연식 미확인",
        },
        False,
    )
    assert "의도: 손해배상 청구" in msg
    assert "권리근거사실: 상대 과실로 사고, 쿼터패널 판금 수리" in msg
    assert "상대방 반대측: 상대방이 격락손해 부인" in msg
    assert "증빙·간접사실: 수리 명세서 보유" in msg
    assert "미확인(추가필요): 차량 출고 연식 미확인" in msg


def test_slack_mock_fallback_without_webhook():
    """Slack webhook 미설정 시 mock 폴백(오류 없이 'mock' 반환)."""
    import app.services.notify as notify

    notify.settings.slack_webhook_url = ""
    res = notify._send_slack(1, "테스트 메시지", False)
    assert res == "mock"


def test_alimtalk_mock_fallback_without_keys():
    """알림톡 키 미설정 시 mock 폴백(오류 없이 'mock' 반환)."""
    import app.services.notify as notify

    notify.settings.kakao_biz_token = ""
    notify.settings.kakao_sender_key = ""
    notify.settings.lawyer_phone = ""
    res = notify._send_alimtalk("테스트 메시지", False)
    assert res == "mock"
