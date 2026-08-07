# Step 05: API 엔드포인트

## 목표
챗봇(오픈빌더) → 백엔드 질의/예약 수신 API와, 관리자용 예약 확인/확정/불가 API를 구현한다.

## 사전 조건
- [ ] Step 01~04 완료 (모델, DB, 서비스, 어댑터)

## 변경할 파일
- 수정: `app/main.py` (라우터 등록)
- 생성: `app/routers/__init__.py`
- 생성: `app/routers/chat.py` (오픈빌더 수신)
- 생성: `app/routers/admin.py` (관리자)
- 생성: `tests/test_api.py`

## 구현 내용

### 1. `app/routers/chat.py` — 챗봇 수신

```python
from fastapi import APIRouter, Depends
from sqlmodel import Session
from app.database import get_session
from app.models import Inquiry
from app.services.elicitation import ElicitationService
from app.services.llm_adapter import MockLLMAdapter
from app.services.kakao_adapter import get_openbuilder_adapter, MockAlimtalkAdapter

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("/webhook")
def chat_webhook(payload: dict, session: Session = Depends(get_session)):
    """오픈빌더 웹훅 수신 → 되묻기 응답."""
    ob = get_openbuilder_adapter("mock")
    parsed = ob.parse_request(payload)
    text = parsed["text"]

    svc = ElicitationService(MockLLMAdapter())
    question = svc.next_question([{"role": "user", "content": text}])

    return {"response": question}
```

### 2. `app/routers/admin.py` — 관리자 API

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.database import get_session
from app.models import Inquiry, Reservation, ReservationStatus
from app.services.kakao_adapter import get_alimtalk_adapter

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/inquiries")
def list_inquiries(session: Session = Depends(get_session)):
    return session.exec(select(Inquiry)).all()

@router.get("/reservations")
def list_reservations(session: Session = Depends(get_session)):
    return session.exec(select(Reservation)).all()

@router.post("/reservations/{rid}/confirm")
def confirm_reservation(rid: int, session: Session = Depends(get_session)):
    r = session.get(Reservation, rid)
    if not r:
        raise HTTPException(404, "not found")
    r.status = ReservationStatus.CONFIRMED
    session.add(r); session.commit()
    alimtalk = get_alimtalk_adapter("mock")
    alimtalk.send_reservation(r.phone, f"상담 예약이 확정되었습니다. {r.desired_dt}")
    return {"status": r.status.value}

@router.post("/reservations/{rid}/reject")
def reject_reservation(rid: int, session: Session = Depends(get_session)):
    r = session.get(Reservation, rid)
    if not r:
        raise HTTPException(404, "not found")
    r.status = ReservationStatus.REJECTED
    session.add(r); session.commit()
    alimtalk = get_alimtalk_adapter("mock")
    alimtalk.send_reservation(r.phone, "해당 시간 예약이 불가하여 사무소에서 연락드리겠습니다.")
    return {"status": r.status.value}
```

### 3. `app/main.py` — 라우터 등록
```python
from fastapi import FastAPI
from app.config import settings
from app.database import init_db
from app.routers import chat, admin

app = FastAPI(title=settings.app_name)

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(chat.router)
app.include_router(admin.router)

@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
```

### 4. `tests/test_api.py`

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_webhook():
    r = client.post("/chat/webhook", json={"utterance": "이혼 문의"})
    assert r.status_code == 200
    assert "response" in r.json()

def test_reservation_confirm_404():
    r = client.post("/admin/reservations/999/confirm")
    assert r.status_code == 404
```

## 검증
```bash
python -m pytest tests/test_api.py -q
```

## 완료 조건
- [ ] 웹훅 수신 동작
- [ ] 관리자 API 동작
- [ ] pytest 통과
