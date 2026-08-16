# 카카오 법률 챗봇 — 프로덕션 배포용 Dockerfile
# python:3.12-slim (glibc, 안정적). SQLite는 파일 DB이므로 별도 DB 컨테이너 불필요.
FROM python:3.12-slim

WORKDIR /app

# 의존성 먼저 설치 (레이어 캐시 최적화)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY app /app/app

# ⚠️ .env는 이미지에 복사하지 않는다 — compose의 environment:로 주입.
#    (로컬 .env의 배포 변수 WEB_PORT 등이 pydantic Settings extra_forbidden 유발)

# SQLite DB 파일이 저장될 디렉토리 (named volume으로 영속화)
RUN mkdir -p /app/data

EXPOSE 8000

# uvicorn으로 서빙. --host 0.0.0.0 (컨테이너 내부), 포트 8000.
# SQLite DB 경로는 config의 database_url (sqlite:///./kakaolaw.db) → /app/kakaolaw.db
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
