# Step 01: 프로젝트 구조 + 백엔드 뼈대

## 목표
FastAPI 백엔드의 기본 구조와 설정 파일을 생성한다.

## 사전 조건
- [ ] 작업 디렉토리: `D:\Projects\Kakaotalk-chatbot`
- [ ] Python 3.11 사용 가능
- [ ] `docs/specs/2026-08-07-kakao-law-chatbot-design.md` 존재 (설계)

## 변경할 파일
- 생성: `app/__init__.py`
- 생성: `app/main.py` (FastAPI 앱 엔트리포인트)
- 생성: `app/config.py` (설정)
- 생성: `requirements.txt`
- 생성: `pyproject.toml`
- 생성: `.gitignore`

## 구현 내용

### 1. 프로젝트 구조
```
Kakaotalk-chatbot/
├── app/
│   ├── __init__.py
│   ├── main.py
│   └── config.py
├── tests/
│   └── __init__.py
├── requirements.txt
├── pyproject.toml
└── .gitignore
```

### 2. `requirements.txt`
```
fastapi==0.115.*
uvicorn[standard]==0.30.*
pydantic==2.*
pydantic-settings==2.*
sqlmodel==0.0.22
python-multipart==0.0.*
pytest==8.*
httpx==0.27.*
```

### 3. `app/config.py`
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """애플리케이션 설정."""
    app_name: str = "Kakao Law Chatbot"
    database_url: str = "sqlite:///./kakaolaw.db"
    # 어댑터 선택 (mock: 실제 API 키 없이 테스트용)
    llm_adapter: str = "mock"
    alimtalk_adapter: str = "mock"
    openbuilder_adapter: str = "mock"

    model_config = {"env_file": ".env", "env_prefix": ""}

settings = Settings()
```

### 4. `app/main.py`
```python
from fastapi import FastAPI
from app.config import settings

app = FastAPI(title=settings.app_name)

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
```

### 5. `pyproject.toml`
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

### 6. `.gitignore`
```
__pycache__/
*.pyc
.env
*.db
.venv/
```

## 검증
```bash
cd D:/Projects/Kakaotalk-chatbot
python -m venv .venv
source .venv/Scripts/activate  # Windows git-bash
pip install -r requirements.txt
python -c "from app.main import app; print('OK', app.title)"
```

## 완료 조건
- [ ] FastAPI 앱 import 성공
- [ ] `app.config` import 성공
- [ ] ruff 통과 (설치 시)
- [ ] py_compile 통과
