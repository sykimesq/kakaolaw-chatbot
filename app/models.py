from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class CaseField(str, Enum):
    FAMILY = "가정"  # 이혼/상속/가사
    REAL_ESTATE = "부동산"  # 매매/임대차/명의신탁
    CREDIT_DEBT = "채권채무"  # 대여금/회수/회생
    CRIMINAL = "형사"  # 고소/피의자·피해자 변호
    LABOR = "노무"  # 근로계약/해고/임금
    TRAFFIC = "교통사고"  # 손해배상/형사처벌 대응


class InquiryStatus(str, Enum):
    COLLECTING = "수집중"  # 되묻기 진행 중
    COMPLETED = "완료"  # 요약 전달 완료
    URGENT = "긴급"  # 긴급 접수
    RESOLVED = "처리완료"  # 변호사 처리 완료


class ReservationStatus(str, Enum):
    PENDING = "대기"  # 신규 접수
    CONFIRMED = "확정"  # 변호사 확정
    REJECTED = "불가"  # 변호사 거절


class Inquiry(SQLModel, table=True):
    """법률 상담 질의 (되묻기 수집 후 요약 전달)."""

    id: int | None = Field(default=None, primary_key=True)
    phone: str  # 문의자 연락처
    name: str = ""  # 문의자 이름
    field: CaseField | None = None  # 상담 분야
    position: str = ""  # 문의자 입장 (당사자/가족 등)
    summary: str = ""  # 질의 요약
    status: InquiryStatus = InquiryStatus.COLLECTING
    urgent: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Reservation(SQLModel, table=True):
    """상담 예약 신청."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    phone: str
    field: CaseField
    desired_dt: str  # 희망 날짜/시간 (문자열)
    status: ReservationStatus = ReservationStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
