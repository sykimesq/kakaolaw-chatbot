from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.database import get_session
from app.models import (
    Inquiry,
    InquiryStatus,
    Reservation,
    ReservationStatus,
)
from app.services.kakao_adapter import MockAlimtalkAdapter

router = APIRouter(prefix="/admin", tags=["admin"])

_alimtalk = MockAlimtalkAdapter()


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
    session.add(r)
    session.commit()
    _alimtalk.send_reservation(
        r.phone, f"상담 예약이 확정되었습니다. {r.desired_dt}"
    )
    return {"status": r.status.value}


@router.post("/reservations/{rid}/reject")
def reject_reservation(rid: int, session: Session = Depends(get_session)):
    r = session.get(Reservation, rid)
    if not r:
        raise HTTPException(404, "not found")
    r.status = ReservationStatus.REJECTED
    session.add(r)
    session.commit()
    _alimtalk.send_reservation(
        r.phone, "해당 시간 예약이 불가하여 사무소에서 연락드리겠습니다."
    )
    return {"status": r.status.value}


@router.post("/inquiries/{iid}/resolve")
def resolve_inquiry(iid: int, session: Session = Depends(get_session)):
    i = session.get(Inquiry, iid)
    if not i:
        raise HTTPException(404, "not found")
    i.status = InquiryStatus.RESOLVED
    session.add(i)
    session.commit()
    return {"status": i.status.value}
