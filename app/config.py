from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """애플리케이션 설정."""

    app_name: str = "Kakao Law Chatbot"
    database_url: str = "sqlite:///./kakaolaw.db"

    # ── LLM 어댑터 설정 ──────────────────────────────
    # llm_provider: "mock" | "openrouter"
    llm_provider: str = "mock"
    # llm_model: provider별 모델 ID (예: nvidia/nemotron-3-super-120b-a12b:free)
    llm_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str = ""  # .env에서 주입

    # ── 카카오 어댑터 설정 ────────────────────────────
    alimtalk_adapter: str = "mock"
    openbuilder_adapter: str = "mock"

    model_config = {"env_file": ".env", "env_prefix": ""}


settings = Settings()
