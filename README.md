# 카카오톡 법률사무소 챗봇

카카오 채널 + 카카오 i 오픈빌더 기반 법률사무소 상담 접수 챗봇.
**법률 자문을 직접 제공하지 않고**, 문의자의 질의를 충분히 되물어 모호성을 낮춘 뒤,
질의를 요약해 변호사에게 전달하고, 상담 예약을 접수·관리한다.

> ⚠️ **핵심 원칙**: 챗봇은 절대 법률 답변/자문을 직접 제공하지 않는다.
> (변호사법상 무자격 법률사무취급 저촉 방지)

## 주요 기능

- **법률 상담 접수** — 문의자의 질의를 되묻기(LLM 에이전트)로 수집, 요약 후 변호사에게 전달
- **상담 예약 접수** — 고객 예약 정보 수집, 관리자 화면에서 확정/불가 처리
- **예약 확정/불가 알림** — 관리자 버튼 클릭 시 고객 연락처로 알림톡 발송

## 아키텍처

```
고객 카카오톡
    │
    ▼
카카오 채널 (챗봇) ── 카카오 i 오픈빌더 스킬/시나리오
    │                              │
    │ 시나리오 응답(되묻기/안내)    │ 질의/예약 데이터 수신(웹훅/API)
    │                              ▼
    │                    백엔드 (저장소 + 알림톡 발송)
    │                              │
    │                              ▼
    │                    관리자 화면 (질의확인/확정/불가)
    │                              │
    │                              ▼
    │                    알림톡(Alimtalk) → 변호사(상담 접수)
    │                    알림톡(Alimtalk) → 고객(예약 확정/불가)
    └─────────────────────────────────────────────┘
```

## 실행 방법

```bash
# 1. 가상환경 생성 및 의존성 설치
python -m venv .venv
source .venv/Scripts/activate   # Windows git-bash
pip install -r requirements.txt

# 2. (선택) LLM 설정 — .env.example을 복사해 .env로 생성
cp .env.example .env
# .env에서 OPENROUTER_API_KEY 설정, LLM_PROVIDER=openrouter로 변경

# 3. 서버 실행
uvicorn app.main:app --reload

# 4. 접속
#  - 관리자 화면: http://localhost:8000/admin
#  - API 문서:    http://localhost:8000/docs
```

### LLM Provider/Model 변경

`app/config.py` 또는 `.env`에서 변경한다.

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `LLM_PROVIDER` | `mock` | `mock` 또는 `openrouter` |
| `LLM_MODEL` | `nvidia/nemotron-3-super-120b-a12b:free` | OpenRouter 모델 ID |
| `OPENROUTER_API_KEY` | (빈 값) | OpenRouter 키 (필수) |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | API 엔드포인트 |

provider/model은 어댑터 팩토리(`app/services/llm_provider.py`)를 통해
config 기반으로 자동 선택된다. 다른 provider 추가 시 해당 어댑터 클래스를
구현하고 팩토리에 등록하면 된다.

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/chat/webhook` | 오픈빌더 웹훅 수신 → 되묻기 응답 |
| POST | `/chat/reservations` | 고객 예약 접수 |
| GET | `/admin/inquiries` | 상담 질의 목록 |
| GET | `/admin/reservations` | 예약 목록 |
| POST | `/admin/reservations/{id}/confirm` | 예약 확정 (+알림톡) |
| POST | `/admin/reservations/{id}/reject` | 예약 불가 (+알림톡) |
| POST | `/admin/inquiries/{id}/resolve` | 질의 완료 처리 |
| GET | `/health` | 헬스체크 |

## 실제 연동 시 교체 지점 (현재 mock)

실제 카카오/LLM 키 확보 후 어댑터를 교체한다. 각 어댑터 인터페이스는 이미 mock과 동일한 시그니처로 정의되어 있다.

| 어댑터 | 파일 | 실제 연동 시 |
|--------|------|--------------|
| LLM (되묻기) | `app/services/llm_adapter.py` | `LLMAdapter` 구현체 (`OpenRouterLLMAdapter` 등) |
| LLM 팩토리 | `app/services/llm_provider.py` | `llm_provider` config로 어댑터 선택 |
| 오픈빌더 | `app/services/kakao_adapter.py` | `OpenBuilderAdapter` 구현체를 오픈빌더 API로 교체 |
| 알림톡 | `app/services/kakao_adapter.py` | `AlimtalkAdapter` 구현체를 비즈메시지 API로 교체 |

- `app/config.py`의 `llm_adapter` / `openbuilder_adapter` / `alimtalk_adapter` 값으로 어댑터 선택
- `.env` 파일에 API 키/설정 주입

## 설계 문서

- [상위 설계](docs/specs/2026-08-07-kakao-law-chatbot-design.md)
- [되묻기 시나리오 상세](docs/specs/2026-08-07-kakao-law-chatbot-elicitation-design.md)

## 테스트

```bash
python -m pytest -q
```
