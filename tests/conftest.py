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


@pytest.fixture(autouse=True)
def _force_mock_llm(monkeypatch):
    """테스트는 실제 네트워크/LLM API에 의존하면 안 되므로 LLM을 mock으로 강제.

    사용자 .env에 openrouter 키가 설정돼 있어도 테스트는 항상 mock을 사용해
    격리된 상태를 유지한다. (웹훅 테스트가 실제 API를 호출해 401이 나는 것 방지)
    """
    monkeypatch.setattr(settings, "llm_provider", "mock")
    # 콜백 경로도 실제 추론 API를 호출하지 않도록 mock 체인 + mock 전송 강제
    monkeypatch.setattr(settings, "reasoning_models", "mock:mock")
    monkeypatch.setattr(settings, "callback_adapter", "mock")
    yield
