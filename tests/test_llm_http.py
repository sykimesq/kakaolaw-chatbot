from unittest import mock

from app.services.llm_adapter import OpenRouterLLMAdapter


def test_openrouter_next_question_calls_api():
    """OpenRouter 어댑터가 올바른 엔드포인트/payload로 호출하는지 검증.

    실제 네트워크 없이 httpx.Client를 mock으로 대체.
    """
    adapter = OpenRouterLLMAdapter(
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        model="nvidia/nemotron-3-super-120b-a12b:free",
    )

    fake_response = mock.MagicMock()
    fake_response.json.return_value = {
        "choices": [{"message": {"content": "어떤 사유로 이혼을 고려하시나요?"}}]
    }
    fake_client = mock.MagicMock()
    # httpx.Client는 컨텍스트 매니저로 사용되므로 __enter__() 반환값에 post() 연결
    fake_client.__enter__.return_value.post.return_value = fake_response

    with mock.patch("app.services.llm_adapter.httpx.Client", return_value=fake_client):
        result = adapter.next_question(
            [{"role": "user", "content": "이혼하려고 합니다"}]
        )

    assert result == "어떤 사유로 이혼을 고려하시나요?"

    # 호출 검증
    fake_client.__enter__.return_value.post.assert_called_once()
    args, kwargs = fake_client.__enter__.return_value.post.call_args
    url = args[0]
    assert "chat/completions" in url
    assert kwargs["json"]["model"] == "nvidia/nemotron-3-super-120b-a12b:free"
    # 시스템 프롬프트(접수 상담사 톤 + 법률 답변 금지) 포함 확인
    system_msgs = [
        m for m in kwargs["json"]["messages"] if m["role"] == "system"
    ]
    assert any("상담 접수 상담사" in m["content"] for m in system_msgs)
    assert any("법률 답변/자문/예측/판단을 제공하지 마라" in m["content"] for m in system_msgs)


def test_openrouter_summarize_parses_json():
    """summarize가 JSON 응답을 파싱해 구조화된 요약을 반환."""
    adapter = OpenRouterLLMAdapter(api_key="test-key")

    fake_response = mock.MagicMock()
    fake_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": (
                        '```json\n{"summary": "배우자 부정으로 이혼 고려",'
                        ' "field": "가정", "position": "당사자",'
                        ' "urgent": false}\n```'
                    )
                }
            }
        ]
    }
    fake_client = mock.MagicMock()
    fake_client.__enter__.return_value.post.return_value = fake_response

    with mock.patch("app.services.llm_adapter.httpx.Client", return_value=fake_client):
        result = adapter.summarize(
            [{"role": "user", "content": "이혼 문의"}]
        )

    assert result["summary"] == "배우자 부정으로 이혼 고려"
    assert result["field"] == "가정"
    assert result["urgent"] is False
