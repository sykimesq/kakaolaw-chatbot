import logging
import threading
import time

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.config import settings
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
    get_callback_adapter,
    get_openbuilder_adapter,
)
from app.services.llm_provider import get_llm_adapter
from app.services.reasoning import reason_next_question

router = APIRouter(prefix="/chat", tags=["chat"])

logger = logging.getLogger(__name__)

# 실제 알림톡 키 확보 전까지 mock 사용
_alimtalk = MockAlimtalkAdapter()

# 최근 대화 컨텍스트로 LLM에 보낼 최대 메시지 수 (토큰 제한 대응)
# ⚠️ 턴 한도(12)를 넘는 순간(13턴째)에도 user 메시지가 13개 남아 있어야
#    user_turns > MAX_ELICIT_TURNS 가 발동한다. 그러려면
#    MAX_HISTORY ≥ 2 × (MAX_ELICIT_TURNS + 1) = 26 필요 → 30으로.
MAX_HISTORY = 30

# 되묻기 최대 턴 수 — 이 턴을 넘으면 LLM 호출 없이 즉시 "접수 완료"로 전환.
# (대화가 길어지면 히스토리가 커져 LLM 생성 시간이 늘어 오픈빌더 스킬 timeout(5초) 위험이 커짐)
# 사용자가 마무리 의사를 밝히면(LLM이 "접수했습니다" 반환) 그보다 먼저 종료된다.
MAX_ELICIT_TURNS = 12

# 접수 완료 시 사용자에게 보낼 고정 응답 (LLM 호출 없음 → timeout 안전)
# LLM이 조기에 "접수했습니다"를 반환하거나 턴 한도 도달 시 사용됨.
COMPLETE_MESSAGE = (
    "지금까지 말씀해 주신 내용으로 상담을 접수했습니다. "
    "변호사님께 전달드리고 검토 후 연락드릴게요. 감사합니다."
)

# ── 콜백 모드 관련 ────────────────────────────────────────────
# 5초 안에 반환하는 대기 메시지 (LLM 호출 없음 → timeout 안전)
WAITING_MESSAGE = "말씀해 주신 내용을 확인하고 있어요. 잠시만 기다려 주세요."

# 처리 중 재발화 시 응답 (선착순 처리, 새 발화는 무시)
BUSY_MESSAGE = "앞서 보내주신 내용을 아직 확인 중이에요. 답변이 곧 도착합니다."

# user_key별 처리 중 플래그 (프로세스 메모리, 단일 워커 컨테이너 전제)
_inflight: dict[str, float] = {}
_inflight_lock = threading.Lock()

# 플래그 TTL(초) — 예외로 해제되지 않아도 이 시간 뒤 자동 만료 (영구 무시 방지)
INFLIGHT_TTL = 60.0


def _acquire_inflight(user_key: str) -> bool:
    """처리 중 플래그 획득. 이미 처리 중이면 False."""
    now = time.monotonic()
    with _inflight_lock:
        started = _inflight.get(user_key)
        if started is not None and now - started < INFLIGHT_TTL:
            return False
        _inflight[user_key] = now
        return True


def _release_inflight(user_key: str) -> None:
    with _inflight_lock:
        _inflight.pop(user_key, None)


def _callback_worker(text: str, user_key: str, callback_url: str) -> None:
    """백그라운드: 추론 모델로 되묻기 질문 생성 → callbackUrl로 전송.

    ⚠️ 요청 스코프 세션은 이미 닫혔으므로 자체 세션을 연다.
    ⚠️ 어떤 예외에도 플래그를 해제해야 사용자가 영구 무시되지 않는다.
    """
    try:
        # ⚠️ conftest가 database.engine을 교체하므로 모듈 속성으로 늦게 참조한다.
        from app import database

        with Session(database.engine) as session:
            result = _process_utterance(
                text, user_key, session, question_fn=reason_next_question
            )
        answer = result["response"]
    except Exception:
        answer = "죄송해요, 처리 중 문제가 발생했어요. 다시 말씀해 주시겠어요?"

    try:
        get_callback_adapter(settings.callback_adapter).send(callback_url, answer)
        logger.info("콜백 전송 성공 user=%s len=%d", user_key, len(answer))
    except Exception as exc:
        # ⚠️ callbackUrl은 5분/1회 한정이므로 재시도 불가 — 실패는 반드시 로그로 남긴다.
        logger.error("콜백 전송 실패 user=%s: %s", user_key, exc)
    finally:
        _release_inflight(user_key)


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
    """가장 최근 '접수 완료' 응답 이후의 사용자 발화 수를 센다.

    한 번 접수 완료(또는 긴급 접수)로 대화가 종료된 적 있으면,
    그다음 대화는 '새 상담 세션'으로 취급해 턴 카운트를 리셋한다.
    (과거 테스트/재방문 누적으로 첫 메시지부터 한도에 걸리는 문제 방지)
    """
    count = 0
    for m in reversed(history):
        # 가장 최근 완료 지점을 만나면 그 이전 발화는 세지 않음
        if m["role"] == "assistant" and "접수했습니다" in m["content"]:
            break
        if m["role"] == "user":
            count += 1
    return count


def _process_utterance(
    text: str,
    user_key: str,
    session: Session,
    question_fn=None,
) -> dict:
    """공용: 되묻기 응답 생성 + 대화 저장. (내부 처리 함수)

    question_fn: 히스토리를 받아 되묻기 질문을 만드는 함수.
        None이면 기존 빠른 모델(`settings.llm_provider`)을 사용한다.
        콜백 경로에서는 추론 모델 체인(`reason_next_question`)을 넘긴다.
    """
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
        # LLM이 사용자의 마무리 의사를 감지하면 "접수했습니다" 응답을 반환한다.
        response = question_fn(history) if question_fn else svc.next_question(history)
        # LLM이 마무리 신호를 감지해 "접수했습니다"를 반환하면 접수 완료로 처리
        if "접수했습니다" in response:
            inquiry_status = InquiryStatus.COMPLETED
        else:
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

    # 접수 완료(또는 긴급) 시 변호사에게 대화 요약 전달.
    # ⚠️ 고객 응답은 즉시 반환해야 오픈빌더 timeout(5초)을 피할 수 있으므로,
    #    변호사 요약(LLM 호출)은 백그라운드 스레드로 분리한다.
    if inquiry_status in (InquiryStatus.COMPLETED, InquiryStatus.URGENT):
        history_snapshot = list(history)
        phone = inquiry.phone
        _thread = threading.Thread(
            target=_summarize_and_notify_lawyer,
            args=(history_snapshot, phone, urgent),
            daemon=True,
        )
        _thread.start()

    return {"response": response, "urgent": urgent, "inquiry_id": inquiry.id}


def _summarize_and_notify_lawyer(history: list[dict], phone: str, urgent: bool) -> None:
    """변호사에게 전달할 대화 요약 생성 + 알림톡 발송. (백그라운드 실행)

    LLM 요약이 느려도 고객 응답과 무관하게 동작하도록 별도 스레드에서 수행한다.
    """
    llm = get_llm_adapter()
    svc = ElicitationService(llm)
    try:
        summary = svc.summarize(history)
    except Exception:
        # 요약 실패 시 원문 그대로 전달 (LLM 호출 실패 방어)
        summary = {
            "summary": " ".join(m["content"] for m in history if m["role"] == "user")
        }
    _alimtalk.send_inquiry_to_lawyer(
        {"summary": summary, "urgent": urgent},
        phone,
    )


@router.post("/webhook")
def chat_webhook(payload: dict, session: Session = Depends(get_session)):
    """(개발/테스트용) 간단한 웹훅: {"utterance": "...", "user_key": "..."}."""
    ob = get_openbuilder_adapter("mock")
    parsed = ob.parse_request(payload)
    return _process_utterance(parsed["text"], parsed["user_key"], session)


@router.post("/openbuilder")
def openbuilder_webhook(payload: dict, session: Session = Depends(get_session)):
    """카카오 i 오픈빌더 실제 웹훅 수신.

    콜백 모드(`settings.use_callback`, 기본 ON):
      1. 5초 안에 LLM 호출 없이 대기 메시지 + `useCallback: true` 반환
      2. 백그라운드에서 추론 모델 체인으로 되묻기 질문 생성
      3. callbackUrl로 실제 답변 POST

    처리 중 같은 사용자가 다시 발화하면 무시(선착순, C안).
    콜백 URL이 없거나 콜백 모드가 꺼져 있으면 기존 동기 응답으로 처리.
    """
    ob = get_openbuilder_adapter("real")
    parsed = ob.parse_request(payload)
    callback_url = payload.get("userRequest", {}).get("callbackUrl", "")

    # 콜백 불가 상황(설정 OFF 또는 오픈빌더가 callbackUrl 미제공) → 기존 동기 경로
    if not settings.use_callback or not callback_url:
        result = _process_utterance(parsed["text"], parsed["user_key"], session)
        return ob.send_response(result)

    user_key = parsed["user_key"]

    # 이미 처리 중이면 무시 (선착순)
    if not _acquire_inflight(user_key):
        return ob.send_response({"response": BUSY_MESSAGE})

    threading.Thread(
        target=_callback_worker,
        args=(parsed["text"], user_key, callback_url),
        daemon=True,
    ).start()

    return {
        "version": "2.0",
        "useCallback": True,
        "data": {"text": WAITING_MESSAGE},
    }


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
