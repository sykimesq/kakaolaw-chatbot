# Step 02: 데이터 모델 + 저장소

## 목표
상담 질의와 예약 접수를 위한 데이터 모델과 SQLite 저장소(repository)를 생성한다.

## 사전 조건
- [ ] Step 01 완료 (`app/main.py`, `app/config.py` 존재)
- [ ] `requirements.txt`에 `sqlmodel` 포함

## 변경할 파일
- 생성: `app/models.py` (데이터 모델)
- 생성: `app/database.py` (DB 세션/초기화)
- 생성: `tests/test_models.py` (모델 테스트)

## 구현 내용

### 1. `app/models.py` — 데이터 모델

```python
from datetime import datetime
from enum import Enum
from sqlmodel import SQLModel, Field

class CaseField(str, Enum):
    FAMILY = "가정"          # 이혼/상속/가사
    REAL_ESTATE = "부동산"    # 매매/임대차/명의신탁
    CREDIT_DEBT = "채권채무"  # 대여금/회수/회생
    CRIMINAL = "형사"         # 고소/피의자·피해자 변호
    LABOR = "노무"            # 근로계약/해고/임금
    TRAFFIC = "교통사고"      # 손해배상/형사처벌

class InquiryStatus(str, Enum):
    COLLECTING = "수집중"     # 되묻기 진행 중
    COMPLETED = "완료"        # 요약 전달 완료
    URGENT = "긴급"           # 긴급 접수
    RESOLVED = "처리완료"     # 변호사 처리 완료

class ReservationStatus(str, Enum):
    PENDING = "대기"          # 신규 접수
    CONFIRMED = "확정"        # 변호사 확정
    REJECTED = "불가"         # 변호사 거절

class Inquiry(SQLModel, table=True):
    """법률 상담 질의 (되묻기 수집 후 요약 전달)."""
    id: int | None = Field(default=None, primary_key=True)
    phone: str                       # 문의자 연락처
    name: str = ""                   # 문의자 이름
    field: CaseField | None = None   # 상담 분야
    position: str = ""               # 문의자 입장 (당사자/가족 등)
    summary: str = ""                # 질의 요약
    status: InquiryStatus = InquiryStatus.COLLECTING
    urgent: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Reservation(SQLModel, table=True):
    """상담 예약 신청."""
    id: int | None = Field(default=None, primary_key=True)
    name: str
    phone: str
    field: CaseField
    desired_dt: str       # 희망 날짜/시간 (문자열)
    status: ReservationStatus = ReservationStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### 2. `app/database.py` — DB 세션/초기화

```python
from sqlmodel import SQLModel, create_engine, Session
from app.config import settings

engine = create_engine(settings.database_url, echo=False)

def init_db() -> None:
    """DB 테이블 생성."""
    SQLModel.metadata.create_all(engine)

def get_session():
    """FastAPI 의존성용 세션."""
    with Session(engine) as session:
        yield session
```

### 3. `tests/test_models.py`

```python
from app.models import CaseField, Inquiry, Reservation

def test_case_fields():
    assert len(CaseField) == 6

def test_inquiry_model():
    i = Inquiry(phone="01012345678")
    assert i.status.value == "수집중"
    assert i.urgent is False

def test_reservation_model():
    r = Reservation(name="김", phone="010", field=CaseField.FAMILY, desired_dt="8/12 14:00")
    assert r.status.value == "대기"
```

## 검증
```bash
python -c "from app.models import Inquiry, Reservation; from app.database import init_db; init_db(); print('DB OK')"
python -m pytest tests/test_models.py -q
```

## 완료 조건
- [ ] 모델 import 성공
- [ ] DB 초기화 성공
- [ ] pytest 통과
