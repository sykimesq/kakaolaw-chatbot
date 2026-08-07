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
    raise ValueError(f"Unknown adapter: {kind}")


def get_alimtalk_adapter(kind: str = "mock") -> AlimtalkAdapter:
    if kind == "mock":
        return MockAlimtalkAdapter()
    raise ValueError(f"Unknown adapter: {kind}")
