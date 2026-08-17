"""기존 Inquiry에 transcript 백필 + user_key 정리.

이전 버전에서는:
- Inquiry.user_key가 비어있고 phone에 user_key가 들어감
- 같은 user_key로 Inquiry가 여러 개 생성됨 (user_key당 1건 유지 로직 없음)
- transcript가 저장되지 않음

이 스크립트는 ChatMessage에서 대화를 재구성해 transcript를 채우고,
user_key를 phone에서 복사한다. (중복 Inquiry는 남겨두되, 각각 transcript를 채운다)

사용법:
  docker compose exec -T web python -m app.backfill_transcript
"""
import logging

from sqlmodel import Session, select

from app.database import engine, init_db
from app.models import ChatMessage, Inquiry

logger = logging.getLogger(__name__)


def _build_transcript(session: Session, user_key: str) -> str:
    """ChatMessage에서 해당 user_key의 대화를 transcript 형식으로 재구성."""
    msgs = session.exec(
        select(ChatMessage)
        .where(ChatMessage.user_key == user_key)
        .order_by(ChatMessage.id.asc())
    ).all()
    lines = []
    for m in msgs:
        who = "고객" if m.role == "user" else "상담사"
        lines.append(f"{who}: {m.content}")
    return "\n".join(lines)


def backfill() -> dict:
    """transcript가 비어있는 Inquiry에 대화를 채운다."""
    init_db()
    filled = 0
    skipped = 0
    with Session(engine) as session:
        inqs = session.exec(select(Inquiry)).all()
        for inq in inqs:
            # user_key가 비어있으면 phone에서 복사 (이전 버전 호환)
            uk = inq.user_key or inq.phone
            if not uk:
                skipped += 1
                continue
            if inq.user_key != uk:
                inq.user_key = uk
            if not inq.transcript:
                transcript = _build_transcript(session, uk)
                if transcript:
                    inq.transcript = transcript
                    filled += 1
                else:
                    skipped += 1
            session.add(inq)
        session.commit()
    return {"filled": filled, "skipped": skipped}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = backfill()
    print(f"백필 완료: {result['filled']}건 채움, {result['skipped']}건 건너뜀")
