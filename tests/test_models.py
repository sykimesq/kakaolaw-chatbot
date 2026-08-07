from app.models import CaseField, Inquiry, Reservation


def test_case_fields():
    assert len(CaseField) == 6


def test_inquiry_model():
    i = Inquiry(phone="01012345678")
    assert i.status.value == "수집중"
    assert i.urgent is False


def test_reservation_model():
    r = Reservation(
        name="김",
        phone="010",
        field=CaseField.FAMILY,
        desired_dt="8/12 14:00",
    )
    assert r.status.value == "대기"
