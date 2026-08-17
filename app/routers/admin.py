import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.models import (
    Inquiry,
    InquiryStatus,
    Reservation,
    ReservationStatus,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# ── 관리자 인증 (HTTP Basic Auth) ─────────────────────────────
# settings.admin_username/admin_password가 둘 다 채워져 있을 때만 활성화.
# 비어있으면(기본값) 인증 없이 동작 → 테스트/로컬 개발은 그대로 통과.
_security = HTTPBasic(auto_error=False)


def _admin_auth_enabled() -> bool:
    return bool(settings.admin_username and settings.admin_password)


def require_admin(
    credentials: HTTPBasicCredentials | None = Depends(_security),
) -> None:
    """/admin 페이지·API 보호. 인증 미설정 시 통과, 설정 시 Basic Auth 검증."""
    if not _admin_auth_enabled():
        return
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="인증 필요",
            headers={"WWW-Authenticate": "Basic"},
        )
    ok_user = secrets.compare_digest(
        credentials.username, settings.admin_username
    )
    ok_pass = secrets.compare_digest(
        credentials.password, settings.admin_password
    )
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=401,
            detail="인증 실패",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("/inquiries")
def list_inquiries(
    session: Session = Depends(get_session),
    _: None = Depends(require_admin),
):
    # 최신 접수가 위로 (id 내림차순)
    return session.exec(
        select(Inquiry).order_by(Inquiry.id.desc())
    ).all()


@router.get("/inquiries/{iid}")
def get_inquiry(
    iid: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_admin),
):
    """접수 1건 + 전체 대화 전문 반환 (관리자 페이지 상세 보기용)."""
    i = session.get(Inquiry, iid)
    if not i:
        raise HTTPException(404, "not found")
    return {
        "id": i.id,
        "user_key": i.user_key,
        "phone": i.phone,
        "field": i.field.value if i.field else None,
        "position": i.position,
        "summary": i.summary,
        "transcript": i.transcript,
        "status": i.status.value,
        "urgent": i.urgent,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


@router.get("/reservations")
def list_reservations(
    session: Session = Depends(get_session),
    _: None = Depends(require_admin),
):
    return session.exec(select(Reservation)).all()


@router.post("/reservations/{rid}/confirm")
def confirm_reservation(
    rid: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_admin),
):
    r = session.get(Reservation, rid)
    if not r:
        raise HTTPException(404, "not found")
    r.status = ReservationStatus.CONFIRMED
    session.add(r)
    session.commit()
    from app.services import notify

    notify.notify_reservation(
        r.phone, f"상담 예약이 확정되었습니다. {r.desired_dt}"
    )
    return {"status": r.status.value}


@router.post("/reservations/{rid}/reject")
def reject_reservation(
    rid: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_admin),
):
    r = session.get(Reservation, rid)
    if not r:
        raise HTTPException(404, "not found")
    r.status = ReservationStatus.REJECTED
    session.add(r)
    session.commit()
    from app.services import notify

    notify.notify_reservation(
        r.phone, "해당 시간 예약이 불가하여 사무소에서 연락드리겠습니다."
    )
    return {"status": r.status.value}


@router.post("/inquiries/{iid}/resolve")
def resolve_inquiry(
    iid: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_admin),
):
    i = session.get(Inquiry, iid)
    if not i:
        raise HTTPException(404, "not found")
    i.status = InquiryStatus.RESOLVED
    session.add(i)
    session.commit()
    return {"status": i.status.value}
