import pytest

from app.services.llm_adapter import MockLLMAdapter, OpenRouterLLMAdapter
from app.services.llm_provider import get_llm_adapter


def test_get_llm_adapter_mock():
    adapter = get_llm_adapter("mock")
    assert isinstance(adapter, MockLLMAdapter)


def test_get_llm_adapter_openrouter():
    adapter = get_llm_adapter("openrouter")
    assert isinstance(adapter, OpenRouterLLMAdapter)


def test_get_llm_adapter_unknown():
    with pytest.raises(ValueError):
        get_llm_adapter("unknown-provider")


def test_openrouter_default_model():
    adapter = OpenRouterLLMAdapter(
        api_key="dummy", model="nvidia/nemotron-3-super-120b-a12b:free"
    )
    assert adapter.model == "nvidia/nemotron-3-super-120b-a12b:free"
    assert adapter.api_key == "dummy"


def test_parse_json_response_strips_codeblock():
    adapter = OpenRouterLLMAdapter(api_key="dummy")
    raw = '```json\n{"summary": "test", "urgent": false}\n```'
    result = adapter._parse_json_response(raw)
    assert result["summary"] == "test"
    assert result["urgent"] is False
