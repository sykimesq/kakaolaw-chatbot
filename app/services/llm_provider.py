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
