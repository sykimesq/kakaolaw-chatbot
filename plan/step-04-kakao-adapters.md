# Step 04: 오픈빌더/알림톡 어댑터 (mock)

## 목표
카카오 오픈빌더 연동과 알림톡 발송을 위한 어댑터 인터페이스와 mock 구현을 생성한다. 실제 키 확보 후 교체 가능한 구조.

## 사전 조건
- [ ] Step 03 완료 (서비스 구조 이해)

## 변경할 파일
- 생성: `app/services/kakao_adapter.py` (오픈빌더 + 알림톡 어댑터)

## 구현 내용

### 1. `app/services/kakao_adapter.py`

오픈빌더로부터 질의/예약 수신, 알림톡 발송을 담당하는 어댑터.

```python
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
        return {"sent": True, "to": phone, "type": "inquiry", "summary": summary}

    def send_reservation(self, phone: str, message: str) -> dict:
        return {"sent": True, "to": phone, "type": "reservation", "message": message}

def get_openbuilder_adapter(kind: str = "mock") -> OpenBuilderAdapter:
    if kind == "mock":
        return MockOpenBuilderAdapter()
    raise ValueError(f"Unknown adapter: {kind}")

def get_alimtalk_adapter(kind: str = "mock") -> AlimtalkAdapter:
    if kind == "mock":
        return MockAlimtalkAdapter()
    raise ValueError(f"Unknown adapter: {kind}")
```

## 검증
```bash
python -c "from app.services.kakao_adapter import MockOpenBuilderAdapter, MockAlimtalkAdapter; print('OK')"
```

## 완료 조건
- [ ] 어댑터 import 성공
- [ ] mock 구현 동작
- [ ] 실제 키 확보 시 교체 가능한 인터페이스 확인
