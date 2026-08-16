# 오픈빌더 콜백 + 추론 모델 2단계 응답 — 설계 문서

> 작성일: 2026-08-16
> 상태: 승인 대기

## 목적

무료 빠른 모델(laguna-xs)이 법률 용어(예: '상간')를 이해하지 못해 헛다리 되묻기를
하는 문제를, 오픈빌더 **콜백(useCallback)** 기능으로 해결한다. 5초 안에는 대기
메시지만 보내고, 실제 되묻기 질문은 추론 모델이 생성해 콜백으로 보낸다.

## 접근법 (확정)

- 1차 응답: **placeholder 전용** (LLM 호출 없음) → 헛질문 리스크 0
- 2차 응답: 추론 모델 결과를 callbackUrl로 POST (최대 1분 여유)
- 동시 발화: **선착순 처리, 진행 중이면 새 메시지 무시**

## 아키텍처

```
고객 발화
  ▼
POST /chat/openbuilder  (5초 내)
  ├─ user_key 처리중 플래그 있으면 → "아직 확인 중입니다" 반환 후 종료 (무시)
  └─ 히스토리 저장 + 플래그 set
     → {"version":"2.0","useCallback":true,"data":{"text":"내용 확인 중입니다…"}}
     → threading.Thread(daemon=True) 로 백그라운드 시작
                       ▼
        추론 모델 폴백 체인으로 되묻기 질문/요약 생성
          1. nous  hy3:free
          2. nous  Solar Pro4:free
          3. openrouter nvidia/nemotron-3-ultra-550b-a55b:free
          4. (전부 실패) 기존 laguna-xs
                       ▼
        POST callbackUrl  {"version":"2.0","template":{"outputs":[{"simpleText":{"text": 답변}}]}}
                       ▼
                 플래그 해제
```

## 컴포넌트

| 파일 | 변경 |
|------|------|
| `app/config.py` | `nous_portal_api_key`, `nous_base_url`, `reasoning_models`(체인), `use_callback` 플래그 추가 |
| `app/services/llm_provider.py` | 체인용 어댑터 리스트 생성 함수 추가 (provider별 base_url/키 분기) |
| `app/services/llm_adapter.py` | 기존 `OpenRouterLLMAdapter` 재사용 — base_url/api_key/model 주입만 일반화 |
| `app/services/reasoning.py` (신규) | 폴백 체인 순회 실행 + 타임아웃(각 25초) |
| `app/services/kakao_adapter.py` | `CallbackAdapter.send(callback_url, text)` + mock 추가 |
| `app/routers/chat.py` | `useCallback` 응답 분기, 처리중 플래그(in-memory dict + lock), 백그라운드 워커 |
| `tests/` | 콜백 응답 형태 / 중복 발화 무시 / 폴백 체인 순회 / mock 강제 |

## 에러 처리

- 체인 전부 실패 → 기존 빠른 모델 결과를 콜백으로 전송 (무응답 방지)
- 콜백 POST 실패 → 로그만 남기고 플래그 해제 (고객은 재발화 가능)
- 백그라운드 예외 → 반드시 finally 로 플래그 해제 (영구 무시 상태 방지)
- 플래그는 프로세스 메모리 + 60초 TTL (워커 단일 컨테이너 전제)

## 테스트 전략

- 외부 API는 autouse fixture로 mock 강제 (Cost Rule 준수, 실키 미사용)
- 검증 항목: (1) 1차 응답에 `useCallback: true` 존재 (2) 1차 응답에서 LLM 호출 0회
  (3) 처리 중 재발화 시 무시 응답 (4) 1·2순위 실패 시 3순위 호출 (5) 전부 실패 시 폴백

## 비고

- 오픈빌더 관리자에서 해당 스킬의 **콜백 사용 설정을 ON** 해야 동작 (사용자 작업 1건)
- 서버 재배포: 호스트 소스 패치 → `docker compose build web && docker compose up -d --force-recreate web`
