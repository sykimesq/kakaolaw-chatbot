from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models import (
    CaseField,
    ChatMessage,
    Inquiry,
    InquiryStatus,
    Reservation,
)
from app.services.elicitation import ElicitationService
from app.services.kakao_adapter import (
    MockAlimtalkAdapter,
    get_openbuilder_adapter,
)
from app.services.llm_provider import get_llm_adapter

router = APIRouter(prefix="/chat", tags=["chat"])

# 실제 알림톡 키 확보 전까지 mock 사용
_alimtalk = MockAlimtalkAdapter()

# 최근 대화 컨텍스트로 LLM에 보낼 최대 메시지 수 (토큰 제한 대응)
MAX_HISTORY = 10

# 되묻기 최대 턴 수 — 이 턴이 지나면 자동으로 "접수 완료"로 전환
# (대화가 길어지면 LLM 생성 시간이 늘어 오픈빌더 스킬 timeout(5초) 위험이 커짐)
MAX_ELICIT_TURNS = 4

# 접수 완료 시 사용자에게 보낼 고정 응답 (LLM 호출 없음 → timeout 안전)
COMPLETE_MESSAGE = (
    "상담 내용을 충분히 접수했습니다. "
    "변호사가 검토 후 연락드리겠습니다. 감사합니다."
)


def _get_history(session: Session, user_key: str) -> list[dict]:
    """사용자별 최근 대화 메시지를 LLM용 히스토리로 변환."""
    msgs = session.exec(
        select(ChatMessage)
        .where(ChatMessage.user_key == user_key)
        .order_by(ChatMessage.id.desc())
        .limit(MAX_HISTORY)
    ).all()
    # 오래된 순으로 뒤집기
    return [
        {"role": m.role, "content": m.content}
        for m in reversed(msgs)
    ]


def _save_message(session: Session, user_key: str, role: str, content: str) -> None:
    session.add(ChatMessage(user_key=user_key, role=role, content=content))


def _count_user_turns(history: list[dict]) -> int:
    """히스토리에서 사용자 발화(턴) 수를 센다."""
    return sum(1 for m in history if m["role"] == "user")


def _process_utterance(text: str, user_key: str, session: Session) -> dict:
    """공용: 되묻기 응답 생성 + 대화 저장. (내부 처리 함수)"""
    # config의 llm_provider에 따라 어댑터 선택 (mock/openrouter)
    llm = get_llm_adapter()
    svc = ElicitationService(llm)

    # 긴급 감지
    urgent = svc.is_urgent(text)

    # 현재 입력을 히스토리에 추가
    history = _get_history(session, user_key)
    history.append({"role": "user", "content": text})
    user_turns = _count_user_turns(history)

    # 긴급이면 즉시 접수 완료 (되묻기 생략)
    if urgent:
        response = COMPLETE_MESSAGE
        inquiry_status = InquiryStatus.URGENT
    # 되묻기 턴 한도 도달 시 자동 접수 완료 (LLM 호출 없이 빠르게 응답 → timeout 안전)
    elif user_turns > MAX_ELICIT_TURNS:
        response = COMPLETE_MESSAGE
        inquiry_status = InquiryStatus.COMPLETED
    else:
        # 되묻기 질문 생성 (이전 대화 포함)
        response = svc.next_question(history)
        inquiry_status = InquiryStatus.COLLECTING

    # 대화 저장: 사용자 입력 + 챗봇 응답
    _save_message(session, user_key, "user", text)
    _save_message(session, user_key, "assistant", response)
    session.commit()

    # 접수된 Inquiry 저장
    inquiry = Inquiry(
        phone=user_key or "미확인",
        summary=text,
        status=inquiry_status,
        urgent=urgent,
    )
    session.add(inquiry)
    session.commit()

    # 접수 완료(또는 긴급) 시 변호사에게 대화 요약 전달
    if inquiry_status in (InquiryStatus.COMPLETED, InquiryStatus.URGENT):
        try:
            summary = svc.summarize(history)
        except Exception:
            # 요약 실패 시 원문 그대로 전달 (LLM 호출 실패 방어)
            summary = {"summary": " ".join(m["content"] for m in history if m["role"] == "user")}
        _alimtalk.send_inquiry_to_lawyer(
            {"summary": summary, "urgent": urgent},
            inquiry.phone,
        )

    return {"response": response, "urgent": urgent, "inquiry_id": inquiry.id}


@router.post("/webhook")
def chat_webhook(payload: dict, session: Session = Depends(get_session)):
    """(개발/테스트용) 간단한 웹훅: {"utterance": "...", "user_key": "..."}."""
    ob = get_openbuilder_adapter("mock")
    parsed = ob.parse_request(payload)
    return _process_utterance(parsed["text"], parsed["user_key"], session)


@router.post("/openbuilder")
def openbuilder_webhook(payload: dict, session: Session = Depends(get_session)):
    """카카오 i 오픈빌더 실제 웹훅 수신 → 되묻기 응답/접수 처리.

    요청: {"userRequest": {"utterance": "...", "user": {"id": "..."}}}
    응답: {"version": "2.0", "template": {"outputs": [{"simpleText": {"text": "..."}}]}}
    """
    ob = get_openbuilder_adapter("real")
    parsed = ob.parse_request(payload)
    result = _process_utterance(parsed["text"], parsed["user_key"], session)
    return ob.send_response(result)


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
