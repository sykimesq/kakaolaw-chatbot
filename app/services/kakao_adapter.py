from abc import ABC, abstractmethod


class OpenBuilderAdapter(ABC):
    """카카오 i 오픈빌더 연동 인터페이스."""

    @abstractmethod
    def parse_request(self, payload: dict) -> dict:
        """오픈빌더 웹훅 payload를 내부 구조로 파싱."""
        ...

    @abstractmethod
    def send_response(self, response: dict) -> dict:
        """고객에게 채팅 응답 전송."""
        ...


class AlimtalkAdapter(ABC):
    """알림톡 발송 인터페이스."""

    @abstractmethod
    def send_inquiry_to_lawyer(self, summary: dict, phone: str) -> dict:
        """질의 요약을 변호사에게 알림톡 전송."""
        ...

    @abstractmethod
    def send_reservation(self, phone: str, message: str) -> dict:
        """고객에게 예약 확정/불가 알림톡 전송."""
        ...


class MockOpenBuilderAdapter(OpenBuilderAdapter):
    def parse_request(self, payload: dict) -> dict:
        return {
            "user_key": payload.get("user_key", ""),
            "text": payload.get("utterance", ""),
        }

    def send_response(self, response: dict) -> dict:
        # mock: 전송 없음, 로그만
        return {"sent": True, "response": response}


class RealOpenBuilderAdapter(OpenBuilderAdapter):
    """실제 카카오 i 오픈빌더 웹훅 요청/응답 파싱.

    오픈빌더 스킬(웹훅)이 보내는 실제 payload 형식:
    {
      "userRequest": {
        "utterance": "...",
        "user": {"id": "..."},
        "params": {...}
      },
      "bot": {...}
    }

    우리가 돌려줘야 하는 응답 형식:
    {
      "version": "2.0",
      "template": {"outputs": [{"simpleText": {"text": "..."}}]}
    }
    """

    def parse_request(self, payload: dict) -> dict:
        user_request = payload.get("userRequest", {})
        user = user_request.get("user", {}) or {}
        return {
            "user_key": user.get("id", ""),
            "text": user_request.get("utterance", ""),
        }

    def send_response(self, response: dict) -> dict:
        # 오픈빌더 응답 형식으로 감싸기
        text = response.get("response", "")
        return {
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": text}}]},
        }


class CallbackAdapter(ABC):
    """오픈빌더 콜백(useCallback) 응답 전송 인터페이스."""

    @abstractmethod
    def send(self, callback_url: str, text: str) -> dict:
        """callbackUrl로 실제 답변을 POST."""
        ...


class MockCallbackAdapter(CallbackAdapter):
    """테스트용 — 전송하지 않고 기록만."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, callback_url: str, text: str) -> dict:
        record = {"sent": True, "url": callback_url, "text": text}
        self.sent.append(record)
        return record


class RealCallbackAdapter(CallbackAdapter):
    """오픈빌더 callbackUrl로 실제 답변 POST.

    payload는 일반 스킬 응답과 같은 형식:
    {"version": "2.0", "template": {"outputs": [{"simpleText": {"text": "..."}}]}}
    """

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def send(self, callback_url: str, text: str) -> dict:
        import httpx

        payload = {
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": text}}]},
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(callback_url, json=payload)
            resp.raise_for_status()
        return {"sent": True, "url": callback_url, "status": resp.status_code}


def get_callback_adapter(kind: str = "mock") -> CallbackAdapter:
    if kind == "mock":
        return MockCallbackAdapter()
    if kind == "real":
        return RealCallbackAdapter()
    raise ValueError(f"Unknown callback adapter: {kind}")


class MockAlimtalkAdapter(AlimtalkAdapter):
    def send_inquiry_to_lawyer(self, summary: dict, phone: str) -> dict:
        return {
            "sent": True,
            "to": phone,
            "type": "inquiry",
            "summary": summary,
        }

    def send_reservation(self, phone: str, message: str) -> dict:
        return {
            "sent": True,
            "to": phone,
            "type": "reservation",
            "message": message,
        }


def get_openbuilder_adapter(kind: str = "mock") -> OpenBuilderAdapter:
    if kind == "mock":
        return MockOpenBuilderAdapter()
    if kind == "real":
        return RealOpenBuilderAdapter()
    raise ValueError(f"Unknown adapter: {kind}")


def get_alimtalk_adapter(kind: str = "mock") -> AlimtalkAdapter:
    if kind == "mock":
        return MockAlimtalkAdapter()
    raise ValueError(f"Unknown adapter: {kind}")
