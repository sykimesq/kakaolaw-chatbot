import pytest

from app import database
from app.config import settings


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """각 테스트마다 독립된 임시 DB 사용 (테스트 간 데이터 격리).

    TestClient를 컨텍스트로 열지 않아 lifespan이 실행되지 않으므로,
    테이블 생성(init_db)을 직접 보장한다.
    """
    db_path = tmp_path / "test.db"
    settings.database_url = f"sqlite:///{db_path}"
    database.engine = database.create_engine(settings.database_url, echo=False)
    database.init_db()
    yield
