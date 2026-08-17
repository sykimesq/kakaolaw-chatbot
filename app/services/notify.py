"""변호사 알림 — 접수 완료 시 상담 내용을 변호사에게 전달.

채널:
  - admin_page: DB에 Inquiry로 저장 → /admin 페이지에서 대화 전문과 함께 확인 (무비용)
  - alimtalk: 카카오 비즈니스 비즈메시지 발송 (발신프로필/토큰 필요, 없으면 mock 폴백)
  - slack: Slack Incoming Webhook으로 즉시 알림 (URL 있으면 실전송, 없으면 mock 폴백)

⚠️ 키/URL이 없으면 각 채널이 silently mock으로 폴백되어 운영이 멈추지 않는다.
   단, 알림이 실제로 갔는지 여부는 로그로 남기므로 누락을 인지할 수 있다.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _enabled(channel: str) -> bool:
    return channel in [c.strip() for c in settings.lawyer_notify_channels.split(",")]


def _format_message(inquiry_id: int, summary: dict, urgent: bool, phone: str | None = None) -> str:
    """변호사에게 보낼 본문 텍스트 (모든 채널 공통, 요건사실론 구조)."""
    tag = "🚨 긴급접수" if urgent else "📥 상담접수"
    lines = [f"{tag} #{inquiry_id}", ""]
    if phone:
        lines.append(f"📞 의뢰인 연락처: {phone}")
    if summary.get("field"):
        lines.append(f"분야: {summary['field']}")
    if summary.get("position"):
        lines.append(f"입장: {summary['position']}")
    if summary.get("intent"):
        lines.append(f"의도: {summary['intent']}")
    if summary.get("claim_facts"):
        lines.append(f"권리근거사실: {summary['claim_facts']}")
    if summary.get("defense_facts"):
        lines.append(f"상대방 반대측: {summary['defense_facts']}")
    if summary.get("evidence"):
        lines.append(f"증빙·간접사실: {summary['evidence']}")
    if summary.get("missing"):
        lines.append(f"미확인(추가필요): {summary['missing']}")
    lines.append("")
    lines.append(f"→ 전체 대화 확인: {settings.admin_url}")
    if urgent:
        lines.append("⚠️ 긴급 신호가 감지되어 즉시 확인이 필요합니다.")
    return "\n".join(lines)


def notify_lawyer(inquiry_id: int, summary: dict, urgent: bool, phone: str | None = None) -> dict:
    """활성화된 모든 채널로 변호사 알림 발송. 채널별 결과 반환."""
    msg = _format_message(inquiry_id, summary, urgent, phone)
    results = {}

    if _enabled("admin_page"):
        # DB 저장은 chat.py에서 이미 완료. 여기서는 "노출 가능" 표시만.
        results["admin_page"] = "stored"

    if _enabled("alimtalk"):
        results["alimtalk"] = _send_alimtalk(msg, urgent)

    if _enabled("slack"):
        results["slack"] = _send_slack(inquiry_id, msg, urgent)

    return results


# ── 알림톡 (카카오 비즈니스 비즈메시지) ──────────────────────────────
def _send_alimtalk(msg: str, urgent: bool) -> str:
    token = settings.kakao_biz_token
    sender_key = settings.kakao_sender_key
    lawyer_phone = settings.lawyer_phone

    if not (token and sender_key and lawyer_phone):
        logger.warning(
            "알림톡 미설정(mock 폴백): kakao_biz_token/sender_key/lawyer_phone 중 "
            "누락 → 실제 발송 안 됨. 메시지: %s", msg[:80]
        )
        return "mock"

    try:
        # 카카오 비즈니스 비즈메시지 API (알림톡) 스펙
        # 참고: 실운영은 템플릿 승인이 필요하나, 여기서는 자유형 비즈메시지 형태로 전송.
        payload = {
            "senderKey": sender_key,
            "tel": lawyer_phone,
            "msg": msg,
            "msgType": "AT",  # 알림톡
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{settings.kakao_biz_api_base}/sender/send",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            resp.raise_for_status()
        logger.info("알림톡 발송 성공 → %s", lawyer_phone)
        return "sent"
    except Exception as exc:
        logger.error("알림톡 발송 실패: %s", exc)
        return f"error:{exc}"


# ── Slack (Incoming Webhook) ──────────────────────────────────────────
def _send_slack(inquiry_id: int, msg: str, urgent: bool) -> str:
    url = settings.slack_webhook_url
    if not url:
        logger.warning("Slack webhook 미설정(mock 폴백). 메시지: %s", msg[:80])
        return "mock"

    try:
        color = "#d00000" if urgent else "#2e6cff"
        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"법률 상담 접수 #{inquiry_id}"
                    + (" (긴급)" if urgent else ""),
                    "text": msg,
                }
            ]
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
        logger.info("Slack 알림 발송 성공")
        return "sent"
    except Exception as exc:
        logger.error("Slack 알림 발송 실패: %s", exc)
        return f"error:{exc}"


# ── 예약 확정/불가 알림 (고객에게 알림톡/Slack) ──────────────────────────
def notify_reservation(phone: str, message: str) -> dict:
    """예약 확정/불가 시 고객에게 알림. 채널별 결과 반환."""
    results = {}
    if _enabled("alimtalk"):
        results["alimtalk"] = _send_alimtalk(f"[예약안내] {message}", urgent=False)
    if _enabled("slack"):
        results["slack"] = _send_slack(0, f"[예약안내] {message}", urgent=False)
    return results
