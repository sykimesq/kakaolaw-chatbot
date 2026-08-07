from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

engine = create_engine(settings.database_url, echo=False)


def init_db() -> None:
    """DB 테이블 생성."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI 의존성용 세션."""
    with Session(engine) as session:
        yield session
