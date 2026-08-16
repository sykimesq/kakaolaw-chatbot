from app.config import settings
from app.services.llm_adapter import (
    LLMAdapter,
    MockLLMAdapter,
    OpenRouterLLMAdapter,
)


def get_llm_adapter(provider: str | None = None) -> LLMAdapter:
    """config의 `llm_provider` 설정에 따라 LLM 어댑터를 생성한다.

    provider는 `settings.llm_provider`를 기본으로 사용하며,
    인자로 전달하면 이를 우선한다.
    """
    provider = (provider or settings.llm_provider or "mock").strip().lower()

    if provider == "mock":
        return MockLLMAdapter()
    if provider == "openrouter":
        return OpenRouterLLMAdapter()
    raise ValueError(f"Unknown LLM provider: {provider}")


def _build_reasoning_adapter(spec: str) -> LLMAdapter:
    """"provider:model" 스펙 하나를 어댑터로 변환.

    provider는 `nous` 또는 `openrouter`. 모델 ID에 콜론이 포함될 수 있으므로
    (예: `hy3:free`) 첫 콜론만 기준으로 분리한다.
    """
    provider, _, model = spec.strip().partition(":")
    provider = provider.strip().lower()
    model = model.strip()
    if not model:
        raise ValueError(f"Invalid reasoning model spec: {spec!r}")

    if provider == "nous":
        return OpenRouterLLMAdapter(
            api_key=settings.nous_portal_api_key,
            base_url=settings.nous_base_url,
            model=model,
            timeout=settings.reasoning_timeout,
        )
    if provider == "openrouter":
        return OpenRouterLLMAdapter(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=model,
            timeout=settings.reasoning_timeout,
        )
    if provider == "mock":
        return MockLLMAdapter()
    raise ValueError(f"Unknown reasoning provider: {provider}")


def get_reasoning_adapters() -> list[LLMAdapter]:
    """`settings.reasoning_models` 폴백 체인을 어댑터 리스트로 생성.

    콜백 응답용. 앞에서부터 시도하고 실패 시 다음 모델로 넘어간다.
    잘못된 스펙은 조용히 건너뛴다(체인 전체가 죽는 것을 방지).
    """
    adapters: list[LLMAdapter] = []
    for spec in (settings.reasoning_models or "").split(","):
        if not spec.strip():
            continue
        try:
            adapters.append(_build_reasoning_adapter(spec))
        except ValueError:
            continue
    return adapters
