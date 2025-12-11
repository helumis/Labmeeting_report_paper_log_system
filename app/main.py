"""
主應用入口 - 簡化版
負責應用初始化和路由註冊
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path

from .config import settings
from .db import create_db_and_tables
from .routes import auth, reports, filters, comments, profiles ,meetings

# 應用初始化
app = FastAPI(
    title="Lab Paper Report System",
    description="實驗室論文報告管理系統",
    version="1.0.0"
)

# 靜態檔案與模板
BASE_DIR = Path(__file__).resolve().parent
app.mount("/css", StaticFiles(directory="app/css"), name="css")
templates = Jinja2Templates(directory="templates")

# 中介軟體
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# 資料庫初始化
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# 註冊路由
app.include_router(auth.router, tags=["Authentication"])
app.include_router(reports.router, tags=["Reports"])
app.include_router(filters.router, tags=["Filters"])
app.include_router(meetings.router, tags=["Meetings"])  # 新增
app.include_router(comments.router, tags=["Comments"])
app.include_router(profiles.router, tags=["Profiles"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)