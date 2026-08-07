# Step 07: 통합 검증 + README

## 목표
전체 시스템을 통합 검증하고, 실행 방법과 아키텍처를 README에 정리한다.

## 사전 조건
- [ ] Step 01~06 완료 (전체 코드 존재)

## 변경할 파일
- 생성: `README.md`
- 생성: `tests/test_integration.py` (통합 테스트)

## 구현 내용

### 1. `tests/test_integration.py`

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_full_flow():
    # 1. 웹훅으로 질의 수신
    r = client.post("/chat/webhook", json={"utterance": "이혼 문의"})
    assert r.status_code == 200

    # 2. 질의가 저장됐는지 (또는 예약 생성)
    # 3. 관리자 API 동작 확인
    r = client.get("/admin/reservations")
    assert r.status_code == 200
```

### 2. `README.md`

- 프로젝트 개요
- 아키텍처 요약 (설계 문서 링크)
- 실행 방법
- 실제 연동 시 교체 지점 (LLM/오픈빌더/알림톡 어댑터)

## 검증
```bash
cd D:/Projects/Kakaotalk-chatbot
python -m pytest -q                      # 전체 테스트
python -m compileall app tests           # 컴파일 확인
# 수동: uvicorn app.main:app --reload 후 /admin, /health 확인
```

## 완료 조건
- [ ] 전체 pytest 통과
- [ ] compileall 통과
- [ ] README 작성
- [ ] 수동 실행 확인
