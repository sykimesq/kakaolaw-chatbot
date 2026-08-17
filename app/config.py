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

    # ── 변호사 알림(상담 접수 전달) 설정 ──────────────
    # 접수 완료 시 변호사에게 알리는 채널.
    # alimtalk: 카카오 비즈니스 알림톡 비즈메시지 발송(발신프로필/토큰 필요)
    #          → 없으면 자동으로 mock(로그만)으로 폴백해 운영 중단 없이 동작.
    # admin_page: /admin 페이지에 접수 내역+대화전문 노출(무비용, 기본 ON).
    lawyer_notify_channels: str = "admin_page,alimtalk,slack"
    # 알림톡 수신자(변호사) 전화번호 — 국내 형식 01012345678
    lawyer_phone: str = ""
    # Slack Incoming Webhook URL — 비어있으면 mock(로그만) 폴백
    slack_webhook_url: str = ""
    # 관리자 페이지 공개 URL — Slack 알림에서 클릭 가능한 링크로 표시
    admin_url: str = "https://kakaolaw.lawcalhost.com/admin"
    # ── 관리자 페이지 인증 (HTTP Basic Auth) ──────────────
    # 둘 다 비어있으면 인증 비활성화(기본값). 배포 시 .env에 채우면
    # /admin 페이지와 /admin/* API가 Basic Auth로 보호된다.
    admin_username: str = ""
    admin_password: str = ""
    # 카카오 비즈니스 API
    kakao_biz_api_base: str = "https://api.bizmessage.kakao.com/v2"
    kakao_biz_token: str = ""  # 비즈메시지 토큰(.env 주입). 비어있으면 mock 폴백.
    # 알림톡 발신 프로필(카카오 비즈니스 관리자 '발신프로필 번호')
    kakao_sender_key: str = ""

    model_config = {"env_file": ".env", "env_prefix": ""}


settings = Settings()
