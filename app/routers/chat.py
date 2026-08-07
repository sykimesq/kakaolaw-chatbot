from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.models import CaseField, Inquiry, InquiryStatus, Reservation
from app.services.elicitation import ElicitationService
from app.services.kakao_adapter import (
    MockAlimtalkAdapter,
    get_openbuilder_adapter,
)
from app.services.llm_provider import get_llm_adapter

router = APIRouter(prefix="/chat", tags=["chat"])

# 실제 알림톡 키 확보 전까지 mock 사용
_alimtalk = MockAlimtalkAdapter()


@router.post("/webhook")
def chat_webhook(payload: dict, session: Session = Depends(get_session)):
    """오픈빌더 웹훅 수신 → 되묻기 응답/접수 처리."""
    ob = get_openbuilder_adapter("mock")
    parsed = ob.parse_request(payload)
    text = parsed["text"]
    user_key = parsed["user_key"]

    # config의 llm_provider에 따라 어댑터 선택 (mock/openrouter)
    llm = get_llm_adapter()
    svc = ElicitationService(llm)

    # 긴급 감지
    urgent = svc.is_urgent(text)

    # 되묻기 질문 생성
    history = [{"role": "user", "content": text}]
    question = svc.next_question(history)

    # 간단한 상태 저장: 접수된 Inquiry 생성
    inquiry = Inquiry(
        phone=user_key or "미확인",
        summary=text,
        status=InquiryStatus.URGENT if urgent else InquiryStatus.COLLECTING,
        urgent=urgent,
    )
    session.add(inquiry)
    session.commit()

    # 알림톡 (mock) — 긴급 또는 질문 접수 시 변호사에게 전달 예정
    if urgent:
        _alimtalk.send_inquiry_to_lawyer({"summary": text, "urgent": True}, inquiry.phone)

    return {"response": question, "urgent": urgent, "inquiry_id": inquiry.id}


@router.post("/reservations")
def create_reservation(payload: dict, session: Session = Depends(get_session)):
    """고객이 예약 접수."""
    name = payload.get("name", "")
    phone = payload.get("phone", "")
    field = payload.get("field")
    desired_dt = payload.get("desired_dt", "")

    r = Reservation(
        name=name,
        phone=phone,
        field=CaseField(field) if field else CaseField.FAMILY,
        desired_dt=desired_dt,
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return {"id": r.id, "status": r.status.value}
