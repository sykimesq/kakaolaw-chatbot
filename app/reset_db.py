"""챗봇 DB 대화·접수 내역 리셋 CLI.

테스트 시 이전 대화가 컨텍스트로 남아 이상하게 동작하는 문제를 해결하기 위한 도구.
특정 사용자(user_key) 또는 전체 데이터를 DB에서 삭제한다.

카카오 오픈빌더는 user_key를 자동 생성하므로 관리자가 본인 ID를 모른다.
→ `--list`로 DB에 저장된 user_key 목록과 대화 수를 먼저 확인하라.

사용법:
  python -m app.reset_db --list             # DB에 저장된 user_key 목록 표시
  python -m app.reset_db --user abc123      # 특정 user_key의 대화·접수만 삭제
  python -m app.reset_db                    # 전체 대화·접수 삭제 (채팅·인쿼리·예약 전부)
  python -m app.reset_db --dry-run          # 삭제 전 삭제될 건수만 출력
  python -m app.reset_db --messages         # ChatMessage(대화)만 삭제
  python -m app.reset_db --inquiries        # Inquiry(접수)만 삭제

주의: 예약(Reservation)도 기본 삭제 대상. 테스트 데이터를 지우는 도구이므로
      실제 운영 데이터에는 신중히 사용할 것.
"""
import argparse

from sqlmodel import Session, delete, select

from app.database import engine, init_db
from app.models import ChatMessage, Inquiry, Reservation


def _count(session: Session, model, user_key: str | None) -> int:
    stmt = select(model)
    if user_key:
        stmt = stmt.where(model.user_key == user_key)
    return len(session.exec(stmt).all())


def list_users() -> None:
    """DB에 저장된 user_key별 대화·접수 수를 표시."""
    init_db()
    with Session(engine) as s:
        msg_counts = {}
        for uk in s.exec(
            select(ChatMessage.user_key).where(ChatMessage.user_key != "")
        ).all():
            msg_counts[uk] = msg_counts.get(uk, 0) + 1

        inq_counts = {}
        for uk in s.exec(
            select(Inquiry.user_key).where(Inquiry.user_key != "")
        ).all():
            inq_counts[uk] = inq_counts.get(uk, 0) + 1

        all_keys = set(msg_counts) | set(inq_counts)
    if not all_keys:
        print("저장된 사용자 데이터가 없습니다.")
        return
    print("저장된 사용자(user_key) 목록:")
    for uk in sorted(all_keys):
        msgs = msg_counts.get(uk, 0)
        inqs = inq_counts.get(uk, 0)
        print(f"  {uk}  (대화 {msgs}건, 접수 {inqs}건)")


def reset(user_key: str | None, messages: bool, inquiries: bool) -> dict:
    """조건에 맞는 데이터 삭제. 모델별 삭제 건수 반환."""
    init_db()
    results = {}
    with Session(engine) as session:
        if messages:
            stmt = delete(ChatMessage)
            if user_key:
                stmt = stmt.where(ChatMessage.user_key == user_key)
            result = session.exec(stmt)
            results["chatmessage"] = result.rowcount
        if inquiries:
            stmt = delete(Inquiry)
            if user_key:
                stmt = stmt.where(Inquiry.user_key == user_key)
            result = session.exec(stmt)
            results["inquiry"] = result.rowcount
        # 예약은 user_key가 없으므로 특정 user 삭제 시에는 제외
        if not user_key:
            result = session.exec(delete(Reservation))
            results["reservation"] = result.rowcount
        session.commit()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="챗봇 DB 리셋")
    parser.add_argument("--list", action="store_true", help="저장된 user_key 목록 표시")
    parser.add_argument("--user", help="특정 user_key만 삭제 (지정 안 하면 전체)")
    parser.add_argument("--dry-run", action="store_true", help="삭제 없이 건수만 표시")
    parser.add_argument("--messages", action="store_true", help="대화(ChatMessage)만 삭제")
    parser.add_argument("--inquiries", action="store_true", help="접수(Inquiry)만 삭제")
    args = parser.parse_args()

    # --list는 목록만 보여주고 종료
    if args.list:
        list_users()
        return

    # 아무 타입도 지정 안 하면 기본으로 전부 삭제
    messages = args.messages or not (args.messages or args.inquiries)
    inquiries = args.inquiries or not (args.messages or args.inquiries)

    if args.dry_run:
        init_db()
        with Session(engine) as s:
            counts = {}
            if messages:
                counts["chatmessage"] = _count(s, ChatMessage, args.user)
            if inquiries:
                counts["inquiry"] = _count(s, Inquiry, args.user)
            if not args.user:
                counts["reservation"] = _count(s, Reservation, None)
        print("삭제될 건수(dry-run):")
        for k, v in counts.items():
            print(f"  {k}: {v}")
        return

    target = f"user_key='{args.user}'" if args.user else "전체"
    print(f"삭제 대상: {target}")
    results = reset(args.user, messages, inquiries)
    for k, v in results.items():
        print(f"  {k}: {v}건 삭제")


if __name__ == "__main__":
    main()
