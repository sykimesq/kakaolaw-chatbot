"""오픈빌더 콜백(useCallback) 2단계 응답 테스트.

설계: docs/specs/2026-08-16-callback-reasoning-design.md
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.routers import chat as chat_router
from app.services.llm_adapter import LLMAdapter
from app.services.llm_provider import get_reasoning_adapters

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_inflight():
    chat_router._inflight.clear()
    yield
    chat_router._inflight.clear()


def _payload(text: str, user_key: str, callback_url: str | None = None) -> dict:
    user_request: dict = {"utterance": text, "user": {"id": user_key}}
    if callback_url is not None:
        user_request["callbackUrl"] = callback_url
    return {"userRequest": user_request}


def test_callback_first_response_uses_callback_and_no_llm(monkeypatch):
    """1차 응답은 useCallback=true + 대기 메시지이며 LLM을 호출하지 않는다."""
    calls = []

    def _boom(history):
        calls.append(history)
        raise AssertionError("1차 응답에서 LLM을 호출하면 안 된다")

    monkeypatch.setattr(chat_router, "reason_next_question", _boom)
    # 백그라운드 스레드가 실제로 돌지 않게 스레드 시작을 무력화
    monkeypatch.setattr(
        chat_router.threading, "Thread", lambda *a, **k: type(
            "T", (), {"start": lambda self: None}
        )()
    )

    resp = client.post(
        "/chat/openbuilder",
        json=_payload("상간소송을 당했습니다", "u1", "https://cb.kakao/x"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["useCallback"] is True
    assert body["data"]["text"] == chat_router.WAITING_MESSAGE
    assert calls == []


def test_duplicate_utterance_while_inflight_is_ignored(monkeypatch):
    """처리 중 재발화는 무시(선착순) — BUSY 메시지 반환."""
    monkeypatch.setattr(
        chat_router.threading, "Thread", lambda *a, **k: type(
            "T", (), {"start": lambda self: None}
        )()
    )
    url = "https://cb.kakao/x"
    first = client.post("/chat/openbuilder", json=_payload("첫 발화", "u2", url))
    assert first.json()["useCallback"] is True

    second = client.post("/chat/openbuilder", json=_payload("두번째 발화", "u2", url))
    body = second.json()
    # 두번째는 콜백을 쓰지 않고 즉시 BUSY 안내
    assert "useCallback" not in body
    text = body["template"]["outputs"][0]["simpleText"]["text"]
    assert text == chat_router.BUSY_MESSAGE


def test_no_callback_url_falls_back_to_sync():
    """오픈빌더가 callbackUrl을 주지 않으면 기존 동기 응답으로 처리."""
    resp = client.post("/chat/openbuilder", json=_payload("이혼 상담이요", "u3"))
    body = resp.json()
    assert "useCallback" not in body
    assert body["template"]["outputs"][0]["simpleText"]["text"]


def test_callback_worker_sends_answer(monkeypatch):
    """워커가 추론 결과를 콜백으로 전송하고 플래그를 해제한다."""
    sent = []

    class _Adapter:
        def send(self, callback_url, text):
            sent.append((callback_url, text))
            return {"sent": True}

    monkeypatch.setattr(chat_router, "get_callback_adapter", lambda kind: _Adapter())
    monkeypatch.setattr(
        chat_router, "reason_next_question", lambda history: "추론 질문입니다"
    )

    chat_router._acquire_inflight("u4")
    chat_router._callback_worker("상간소송 당했습니다", "u4", "https://cb/y")

    assert sent == [("https://cb/y", "추론 질문입니다")]
    assert "u4" not in chat_router._inflight


def test_callback_worker_releases_flag_on_error(monkeypatch):
    """추론이 실패해도 플래그는 해제되고 안내 문구가 전송된다."""
    sent = []

    class _Adapter:
        def send(self, callback_url, text):
            sent.append(text)
            return {"sent": True}

    def _fail(history):
        raise RuntimeError("추론 실패")

    monkeypatch.setattr(chat_router, "get_callback_adapter", lambda kind: _Adapter())
    monkeypatch.setattr(chat_router, "reason_next_question", _fail)

    chat_router._acquire_inflight("u5")
    chat_router._callback_worker("내용", "u5", "https://cb/z")

    assert sent and "문제가 발생" in sent[0]
    assert "u5" not in chat_router._inflight


def test_reasoning_chain_falls_back_to_next_model(monkeypatch):
    """체인 앞 모델이 실패하면 다음 모델이 사용된다."""
    from app.services import reasoning

    class _Fail(LLMAdapter):
        def next_question(self, history):
            raise RuntimeError("무료 티어 지연")

        def summarize(self, history):
            return {}

    class _Ok(LLMAdapter):
        def next_question(self, history):
            return "두번째 모델 답변"

        def summarize(self, history):
            return {}

    monkeypatch.setattr(
        reasoning, "get_reasoning_adapters", lambda: [_Fail(), _Ok()]
    )
    assert reasoning.reason_next_question([]) == "두번째 모델 답변"


def test_reasoning_chain_all_fail_falls_back_to_fast_model(monkeypatch):
    """체인 전부 실패 시 기존 빠른 모델(mock)로 폴백한다."""
    from app.services import reasoning

    monkeypatch.setattr(reasoning, "get_reasoning_adapters", lambda: [])
    result = reasoning.reason_next_question(
        [{"role": "user", "content": "이혼 문제입니다"}]
    )
    assert result  # mock 어댑터가 질문을 반환


def test_reasoning_model_spec_parsing(monkeypatch):
    """"provider:model" 스펙이 올바르게 파싱되고 키/base_url이 주입된다."""
    monkeypatch.setattr(
        settings,
        "reasoning_models",
        "nous:hy3:free,openrouter:nvidia/nemotron-3-ultra-550b-a55b:free,bad-spec",
    )
    monkeypatch.setattr(settings, "nous_portal_api_key", "NOUSKEY")
    monkeypatch.setattr(settings, "openrouter_api_key", "ORKEY")

    adapters = get_reasoning_adapters()
    # 잘못된 스펙(bad-spec)은 건너뛴다
    assert len(adapters) == 2
    assert adapters[0].model == "hy3:free"
    assert adapters[0].api_key == "NOUSKEY"
    assert adapters[0].base_url == settings.nous_base_url
    assert adapters[1].model == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert adapters[1].api_key == "ORKEY"
