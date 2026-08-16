from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """애플리케이션 설정."""

    app_name: str = "Kakao Law Chatbot"
    database_url: str = "sqlite:///./kakaolaw.db"

    # ── LLM 어댑터 설정 ──────────────────────────────
    # llm_provider: "mock" | "openrouter"
    llm_provider: str = "mock"
    # llm_model: provider별 모델 ID
    # 오픈빌더 스킬 timeout(5초) 안에 응답해야 하므로 빠른 무료 모델 사용
    # laguna-xs-2.1:free — 사무실 서버 ~2.2초, timeout 안전 (최종 선택)
    llm_model: str = "poolside/laguna-xs-2.1:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str = ""  # .env에서 주입

    # ── 추론(콜백) 모델 설정 ──────────────────────────
    # 오픈빌더 콜백(useCallback)을 쓰면 최대 1분 여유가 생기므로,
    # 느리지만 이해력이 좋은 추론 모델로 되묻기 질문을 생성한다.
    use_callback: bool = True
    # 폴백 체인: "provider:model" 형식, 콤마 구분. 앞에서부터 시도.
    reasoning_models: str = (
        "nous:upstage/solar-pro4:free,"
        "nous:tencent/hy3:free,"
        "openrouter:nvidia/nemotron-3-ultra-550b-a55b:free"
    )
    # 체인 내 각 모델 호출 타임아웃(초)
    # 오픈빌더 callbackUrl은 5분/1회 유효 → 40초×3회=120초로 여유 있게 잡아도 안전.
    reasoning_timeout: float = 40.0
    nous_base_url: str = "https://inference-api.nousresearch.com/v1"
    nous_portal_api_key: str = ""  # .env에서 주입

    # ── 카카오 어댑터 설정 ────────────────────────────
    alimtalk_adapter: str = "mock"
    openbuilder_adapter: str = "mock"
    # 콜백 전송 어댑터: "real"(실제 POST) | "mock"(테스트)
    callback_adapter: str = "real"

    model_config = {"env_file": ".env", "env_prefix": ""}


settings = Settings()
