import logging
import re
import threading
import time

from fastapi import APIRouter, Depends
from sqlmodel import Session, delete, select

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
    get_callback_adapter,
    get_openbuilder_adapter,
)
from app.services.legal_guard import sanitize
from app.services.llm_provider import get_llm_adapter
from app.services.reasoning import reason_next_question

router = APIRouter(prefix="/chat", tags=["chat"])

logger = logging.getLogger(__name__)

# 변호사 알림은 app/services/notify.py 가 담당 (alimtalk/slack/admin_page 멀티채널)
# — 채널별 키/URL 미설정 시 자동 mock 폴백.

# 최근 대화 컨텍스트로 LLM에 보낼 최대 메시지 수 (토큰 제한 대응)
# 요건사실 수집이 완료될 때까지 대화가 이어지므로, 안전한 상한으로 넉넉히 둔다.
MAX_HISTORY = 60

# 접수 완료 시 사용자에게 보낼 고정 응답 (LLM 호출 없음 → timeout 안전)
# LLM이 요건사실 수집 완료를 감지해 "접수했습니다"를 반환하거나,
# 긴급 신호 시 사용됨.
# ⚠️ "접수했습니다"가 반드시 포함돼야 세션 리셋(_count_user_turns)이 동작한다.
COMPLETE_MESSAGE = (
    "말씀해 주신 내용은 잘 접수했습니다. "
    "변호사님과 직접 상담을 원하시면 도와드릴까요? "
    "원하시면 '상담 원해요'라고 말씀해 주세요."
)

# 사용자가 변호사 상담을 원한다고 밝혔을 때의 최종 응답
CONSULT_ACCEPTED_MESSAGE = (
    "네, 접수했습니다. 변호사님께 전달드리고 검토 후 연락드릴게요. 감사합니다."
)

# 상담 동의 후 연락처를 요청하는 메시지
ASK_PHONE_MESSAGE = (
    "네, 접수했습니다. 변호사님이 연락드릴 수 있도록 "
    "연락 가능한 전화번호를 남겨주시겠어요? (예: 010-1234-5678)"
)

# 연락처를 받지 못하고 최종 마무리할 때
PHONE_SKIPPED_MESSAGE = (
    "네, 접수했습니다. 변호사님께 전달드리고 검토 후 연락드릴게요. 감사합니다."
)

# 상담 희망 의사로 판정할 키워드
CONSULT_YES_KEYWORDS = [
    "상담 원해", "상담원해", "상담 받고", "상담받고", "상담 부탁", "상담부탁",
    "네", "예", "좋아요", "부탁드립니다", "부탁해요", "해주세요", "원합니다",
    "연락주세요", "연락 주세요", "만나고", "예약",
]

# ── 콜백 모드 관련 ────────────────────────────────────────────
# 5초 안에 반환하는 대기 메시지 (LLM 호출 없음 → timeout 안전)
WAITING_MESSAGE = "말씀해 주신 내용을 확인하고 있어요. 잠시만 기다려 주세요."

# 처리 중 재발화 시 응답 (선착순 처리, 새 발화는 무시)
BUSY_MESSAGE = "앞서 보내주신 내용을 아직 확인 중이에요. 답변이 곧 도착합니다."

# /reset 명령 응답 — 이전 대화·접수 삭제 후 새로 시작 안내
RESET_MESSAGE = (
    "지금까지의 대화 기록을 초기화했습니다. "
    "처음부터 다시 상담을 시작하겠습니다. 어떤 일로 상담을 원하시는지 알려주세요."
)

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


def _delete_user_data(session: Session, user_key: str) -> None:
    """해당 user_key의 대화·접수를 DB에서 삭제. (/reset 명령용)

    사용자 세션(user_key)을 초기화해 다음 대화를 '새 상담'으로 시작하게 한다.
    """
    session.exec(delete(ChatMessage).where(ChatMessage.user_key == user_key))
    session.exec(delete(Inquiry).where(Inquiry.user_key == user_key))
    # Reservation은 user_key 필드가 없어 사용자 단위 삭제 대상에서 제외된다.
    # (예약 내역은 남겨두고, 대화·접수만 초기화한다는 의도)


def _is_consult_accept(history: list[dict]) -> bool:
    """직전 챗봇 응답이 '변호사 상담을 원하시나요?'였고, 사용자가 동의했는지 판정.

    ⚠️ 마지막 항목이 방금 들어온 사용자 발화라고 가정한다(_process_utterance에서
       history에 append한 뒤 호출).
    직전 챗봇 질문 없이 단순히 "네"만 온 경우는 동의로 보지 않는다(오종료 방지).
    """
    if len(history) < 2:
        return False
    last = history[-1]
    prev = history[-2]
    if last.get("role") != "user" or prev.get("role") != "assistant":
        return False
    # 직전 응답이 상담 희망을 물은 마감 멘트인지 확인
    if "상담을 원하시면" not in prev.get("content", ""):
        return False
    text = last.get("content", "").strip()
    return any(kw in text for kw in CONSULT_YES_KEYWORDS)


# 전화번호 정규식 — 010-1234-5678, 01012345678, 02-123-4567 등
_PHONE_RE = re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}")


def _extract_phone(text: str) -> str | None:
    """발화에서 전화번호를 추출. 없으면 None."""
    m = _PHONE_RE.search(text)
    if not m:
        return None
    # 숫자만 남겨 정규화 (01012345678)
    return re.sub(r"[^0-9]", "", m.group(0))


def _is_phone_skip(text: str) -> bool:
    """연락처 요청에 대해 거절/회피하는 응답인지 판정."""
    t = text.strip()
    skip_kw = ["없어요", "없습니다", "몰라요", "모르겠", "싫어요", "안 돼", "안돼",
               "그냥", "괜찮아", "나중에", "다음에", "비밀", "알려주기 싫"]
    return any(kw in t for kw in skip_kw)


def _is_phone_pending(history: list[dict]) -> bool:
    """직전 챗봇 응답이 연락처 요청(ASK_PHONE_MESSAGE)이었는지 판정.

    상담 동의 후 연락처를 물었는데 아직 답을 안 받은 상태인지 확인한다.
    ⚠️ _process_utterance에서 현재 사용자 입력을 history에 append한 뒤 호출하므로,
       직전 assistant 메시지는 history[-2]에 있다.
    """
    if len(history) < 2:
        return False
    last = history[-1]
    prev = history[-2]
    if last.get("role") != "user" or prev.get("role") != "assistant":
        return False
    return "연락 가능한 전화번호를 남겨주시겠어요" in prev.get("content", "")


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

    특수 명령어:
      /reset — 해당 user_key의 대화·접수·예약을 DB에서 삭제하고 새로 시작.
        (카카오 오픈빌더는 user_key를 자동 생성하므로, 테스트 시 이전 대화를
         컨텍스트로 남기고 싶지 않을 때 채팅창에서 바로 초기화한다.)
    """
    # ⚠️ /reset 명령은 저장 로직을 완전히 건너뛰고 즉시 반환한다.
    #    (리셋된 user_key의 과거 대화가 새 대화에 컨텍스트로 남지 않도록)
    if text.strip() == "/reset":
        if not user_key:
            return {"response": "사용자 식별자가 없어 리셋할 수 없습니다.", "reset": False}
        _delete_user_data(session, user_key)
        session.commit()
        logger.info("대화 리셋 user=%s", user_key)
        return {"response": RESET_MESSAGE, "reset": True}

    # config의 llm_provider에 따라 어댑터 선택 (mock/openrouter)
    llm = get_llm_adapter()
    svc = ElicitationService(llm)

    # 긴급 감지
    urgent = svc.is_urgent(text)

    # 현재 입력을 히스토리에 추가
    history = _get_history(session, user_key)
    history.append({"role": "user", "content": text})

    # 긴급이면 즉시 접수 완료 (되묻기 생략)
    if urgent:
        response = COMPLETE_MESSAGE
        inquiry_status = InquiryStatus.URGENT
        _pending_phone = None
        _notify_now = True
    # 직전에 연락처를 물었고, 지금 전화번호를 받았으면 → 저장 + 알림
    elif _is_phone_pending(history):
        phone = _extract_phone(text)
        if phone:
            response = CONSULT_ACCEPTED_MESSAGE
            inquiry_status = InquiryStatus.COMPLETED
            _pending_phone = phone
            _notify_now = True
        elif _is_phone_skip(text):
            # 연락처 거절 → 연락처 없이 마무리
            response = PHONE_SKIPPED_MESSAGE
            inquiry_status = InquiryStatus.COMPLETED
            _pending_phone = None
            _notify_now = True
        else:
            # 전화번호도 아니고 거절도 아니면 다시 요청
            response = ASK_PHONE_MESSAGE
            inquiry_status = InquiryStatus.COMPLETED
            _pending_phone = None
            _notify_now = False
    # 직전에 변호사 상담 여부를 물었고 사용자가 동의했으면 → 연락처 요청 (아직 알림 안 보냄)
    elif _is_consult_accept(history):
        response = ASK_PHONE_MESSAGE
        inquiry_status = InquiryStatus.COMPLETED
        _pending_phone = None
        _notify_now = False
    else:
        # 되묻기 질문 생성 (이전 대화 포함)
        # LLM이 요건사실 수집 완료를 감지해 "접수했습니다"를 반환한다.
        # (①의도+②권리근거사실 충분, 또는 ③④ 더 수집 불가 시 마감)
        response = question_fn(history) if question_fn else svc.next_question(history)
        # ⚠️ 프롬프트만 믿지 않는다 — 법률 판단이 섞이면 안전 문구로 교체 (변호사법)
        response = sanitize(response)
        # LLM이 마무리 신호를 감지해 "접수했습니다"를 반환하면 접수 완료로 처리
        if "접수했습니다" in response:
            inquiry_status = InquiryStatus.COMPLETED
        else:
            inquiry_status = InquiryStatus.COLLECTING
        _pending_phone = None
        _notify_now = inquiry_status == InquiryStatus.COMPLETED

    # 대화 저장: 사용자 입력 + 챗봇 응답
    _save_message(session, user_key, "user", text)
    _save_message(session, user_key, "assistant", response)
    session.commit()

    # Inquiry는 사용자 세션(user_key)당 1건으로 유지.
    # 최초 1회만 생성, 이후엔 상태/긴급 여부만 갱신한다.
    _existing = None
    if user_key:
        _existing = session.exec(
            select(Inquiry).where(Inquiry.user_key == user_key)
        ).first()
    if _existing is None:
        inquiry = Inquiry(
            phone=_pending_phone or user_key or "",
            user_key=user_key or "",
            status=inquiry_status,
            urgent=urgent,
        )
        session.add(inquiry)
    else:
        _existing.status = inquiry_status
        _existing.urgent = urgent
        # 연락처를 받았으면 갱신 (user_key 대신 실제 전화번호)
        if _pending_phone:
            _existing.phone = _pending_phone
        inquiry = _existing
    session.commit()
    inquiry_id = inquiry.id

    # 접수 완료(또는 긴급) 시 → 전체 대화 전문 + 요약을 DB에 저장하고 변호사에게 알림.
    # ⚠️ 고객 응답은 즉시 반환해야 오픈빌더 timeout(5초)을 피할 수 있으므로,
    #    요약(LLM 호출) + 알림 발송은 백그라운드 스레드로 분리한다.
    # ⚠️ 연락처를 받기 전(ASK_PHONE_MESSAGE 직후)에는 알림을 보내지 않는다.
    #    연락처를 받았거나 거절했을 때만 알림을 보낸다.
    if inquiry_status in (InquiryStatus.COMPLETED, InquiryStatus.URGENT):
        # 전체 대화 전문 (지금까지의 history + 방금 입력 + 방금 응답)
        # ⚠️ history에는 방금 생성한 assistant 응답이 아직 없으므로 직접 추가한다.
        #    (추가하지 않으면 transcript가 상담자 메시지에서 끝나 관리자 페이지에서
        #     챗봇 답변이 잘려 보인다 — #151 사례)
        full_history = list(history) + [{"role": "assistant", "content": response}]
        transcript = "\n".join(
            f"{'고객' if m['role'] == 'user' else '상담사'}: {m['content']}"
            for m in full_history
        )
        inquiry.transcript = transcript
        session.add(inquiry)
        session.commit()

        # 연락처를 받았거나 거절했을 때만 알림 (연락처 요청 직후에는 보내지 않음)
        if _notify_now:
            history_snapshot = list(history)
            _thread = threading.Thread(
                target=_summarize_and_notify_lawyer,
                args=(history_snapshot, inquiry_id, urgent, _pending_phone),
                daemon=True,
            )
            _thread.start()

    return {"response": response, "urgent": urgent, "inquiry_id": inquiry_id}


def _summarize_and_notify_lawyer(
    history: list[dict], inquiry_id: int, urgent: bool, phone: str | None = None
) -> None:
    """변호사에게 전달할 대화 요약 생성 + 알림 발송. (백그라운드 실행)

    LLM 요약이 느려도 고객 응답과 무관하게 동작한다.
    요약 실패 시에도 원문 기반 요약으로 대체해 알림은 보장한다.
    phone: 의뢰인 연락처 (수집된 경우). 알림 본문에 포함된다.
    """
    llm = get_llm_adapter()
    svc = ElicitationService(llm)
    try:
        summary = svc.summarize(history)
    except Exception:
        # 요약 실패 시 원문 기반 최소 요약으로 대체 (LLM 호출 실패 방어)
        summary = {
            "intent": None,
            "claim_facts": " ".join(
                m["content"] for m in history if m["role"] == "user"
            ),
            "defense_facts": None,
            "evidence": None,
            "missing": None,
        }
    try:
        from app.services import notify

        results = notify.notify_lawyer(inquiry_id, summary, urgent, phone)
        logger.info("변호사 알림 전송 완료 inquiry=%s 결과=%s", inquiry_id, results)
    except Exception as exc:
        logger.error("변호사 알림 전송 실패 inquiry=%s: %s", inquiry_id, exc)


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

    # ⚠️ /reset 명령은 LLM 호출이 없어 즉시 응답해야 하므로 콜백 우회.
    #    (백그라운드 callback으로 늦게 도착하면 사용자가 기다리게 된다)
    if parsed["text"].strip() == "/reset":
        result = _process_utterance(parsed["text"], parsed["user_key"], session)
        return ob.send_response(result)

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
