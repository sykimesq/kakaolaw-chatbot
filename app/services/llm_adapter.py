from abc import ABC, abstractmethod


class LLMAdapter(ABC):
    """되묻기 LLM 인터페이스."""

    @abstractmethod
    def next_question(self, history: list[dict]) -> str:
        """대화 기록을 보고 다음 되묻기 질문 1개 반환."""
        ...

    @abstractmethod
    def summarize(self, history: list[dict]) -> dict:
        """수집된 대화를 구조화된 질의 요약으로 반환."""
        ...


class MockLLMAdapter(LLMAdapter):
    """실제 LLM 없이 테스트용 mock."""

    def next_question(self, history: list[dict]) -> str:
        return "어떤 일이 있었는지 자세히 말씀해주세요."

    def summarize(self, history: list[dict]) -> dict:
        return {
            "summary": "대화 요약 (mock)",
            "field": None,
            "urgent": False,
        }
