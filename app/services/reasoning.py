"""추론 모델 폴백 체인 — 오픈빌더 콜백 응답용.

오픈빌더 스킬은 5초 timeout이지만, 콜백(useCallback)을 쓰면 최대 1분 여유가 있다.
이 모듈은 이해력 좋은 추론 모델들을 순서대로 시도해 되묻기 질문을 생성한다.
전부 실패하면 기존 빠른 모델로 폴백해 최소한 무응답은 피한다.
"""

import logging

from app.services.elicitation import ElicitationService
from app.services.llm_adapter import EMPTY_CONTENT_FALLBACK
from app.services.llm_provider import get_llm_adapter, get_reasoning_adapters

logger = logging.getLogger(__name__)


def reason_next_question(history: list[dict]) -> str:
    """폴백 체인으로 되묻기 질문 1개 생성.

    1. `settings.reasoning_models` 체인을 앞에서부터 시도
    2. 전부 실패하면 기존 빠른 모델(`settings.llm_provider`)로 폴백
    3. 그것도 실패하면 고정 문구 반환 (무응답 방지)
    """
    for adapter in get_reasoning_adapters():
        try:
            result = ElicitationService(adapter).next_question(history)
            # 빈 응답 방어 문구가 나오면 그 모델은 실질 실패 → 다음 모델로
            if result and result.strip() and result.strip() != EMPTY_CONTENT_FALLBACK:
                return result.strip()
            logger.warning("추론 모델이 빈 응답 반환, 다음 모델로 폴백")
        except Exception as exc:  # 무료 티어 지연/오류 → 다음 모델로
            logger.warning("추론 모델 실패, 다음 모델로 폴백: %s", exc)
            continue

    # 체인 전부 실패 → 기존 빠른 모델
    try:
        return ElicitationService(get_llm_adapter()).next_question(history)
    except Exception as exc:
        logger.warning("빠른 모델 폴백도 실패: %s", exc)
        return "말씀해 주신 내용을 좀 더 자세히 알려주시겠어요?"
