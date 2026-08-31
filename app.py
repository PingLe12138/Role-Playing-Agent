"""FastAPI application entry point.

/ FastAPI 应用入口。

Wires up the lifespan (DB schema + auth boot), the auth middleware, CORS, and
mounts all routers from the `routers/` package. The per-domain endpoint logic
lives in those routers; this file only owns the app lifecycle.
/ 负责应用生命周期（数据库建表 + 认证引导）、认证中间件、CORS，并挂载 `routers/`
  包中的全部路由。各领域端点逻辑位于路由模块内，本文件只负责应用生命周期。
"""

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api_error_logger import log_exception
import auth as auth_module
from routers import (
    auth_router,
    characters_router,
    chat_router,
    config_router,
    misc_router,
    sessions_router,
    worldview_router,
)
from routers.deps import db, db_mgr, executor


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create/migrate tables, drop legacy raw-text user messages, load
    # the auth password (if any) from config.json.
    # / 启动：建表/迁移，清理遗留的纯文本 user 消息，从 config.json 加载认证密码。
    db_mgr.create_tables()
    db.execute("DELETE FROM session_history WHERE role = 'user' AND createdBy = 'user' AND content NOT LIKE '{%'")
    auth_module.load_auth_config()
    yield

    # Shutdown: stop the graph-execution thread pool. The ChromaDB collections
    # are intentionally NOT wiped on shutdown — they are persistent caches and
    # deleting them would force a full re-embedding on next start.
    # / 关闭：停止图执行线程池。刻意不清空 ChromaDB 集合——它们是持久化缓存，
    #   删除会导致下次启动需重新全量嵌入。
    executor.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log_exception(request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)


@app.middleware("http")
async def auth_middleware(request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    # Login and status probes are reachable without a token so the frontend can
    # decide whether to show the login page.
    # / 登录与状态探测可免令牌访问，便于前端决定是否展示登录页。
    if path in ("/api/auth/login", "/api/auth/status"):
        return await call_next(request)
    token = request.headers.get("Authorization", "")
    if token.startswith("Bearer "):
        token = token[7:]
    else:
        token = request.query_params.get("token", "")
    if not auth_module.check_token(token):
        return JSONResponse(status_code=401, content={"msg": "未登录或登录已过期"})
    return await call_next(request)


app.include_router(auth_router)
app.include_router(characters_router)
app.include_router(chat_router)
app.include_router(config_router)
app.include_router(misc_router)
app.include_router(sessions_router)
app.include_router(worldview_router)

# Serve generated scene images (and any other static assets) under /static.
# The dir is created lazily so a fresh checkout works without manual setup.
# Note: the auth middleware only guards /api/* — /static stays public so the
# browser <img> tags can load scene images directly.
# / 在 /static 提供生成的场景图片（及其它静态资源）。目录惰性创建，
#   新检出无需手动初始化。认证中间件只保护 /api/*，/static 保持公开以便
#   浏览器 <img> 直接加载场景图片。
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_STATIC_DIR = os.path.join(_BASE_DIR, "static")
os.makedirs(_STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)