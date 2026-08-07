from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """애플리케이션 설정."""

    app_name: str = "Kakao Law Chatbot"
    database_url: str = "sqlite:///./kakaolaw.db"
    # 어댑터 선택 (mock: 실제 API 키 없이 테스트용)
    llm_adapter: str = "mock"
    alimtalk_adapter: str = "mock"
    openbuilder_adapter: str = "mock"

    model_config = {"env_file": ".env", "env_prefix": ""}


settings = Settings()
