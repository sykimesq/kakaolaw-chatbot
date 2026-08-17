import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import admin, chat
from app.routers.admin import require_admin

# ⚠️ uvicorn 기본 설정은 앱 로거(app.*)에 핸들러를 붙이지 않아 logger.info/error가
#    컨테이너 로그에 전혀 나오지 않는다. 콜백은 5분/1회로 재시도가 불가하므로
#    전송 성공/실패를 반드시 볼 수 있어야 한다 → 앱 로거를 명시적으로 설정한다.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("app").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(chat.router)
app.include_router(admin.router)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/admin", response_class=HTMLResponse)
def admin_page(_: None = Depends(require_admin)) -> str:
    return (STATIC_DIR / "admin.html").read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
