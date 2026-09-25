"""Application entry point.

[P0] create_app() 是「应用工厂」模式：
不在模块导入时就构造好 app，而是提供一个函数来创建。
好处：
1. 测试里可以用不同配置创建多个 app 实例，互不干扰
2. 启动参数（CORS、路由、中间件）集中在一处，不会出现「改了这里忘了那里」
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.events.store import get_event_store
from app.graph.run_store import get_run_store
from app.rag.store import get_knowledge_store


class UTF8JSONResponse(JSONResponse):
    """强制声明 charset=utf-8,避免中文 Windows 浏览器按 GBK 解码 JSON 导致乱码."""

    media_type = "application/json; charset=utf-8"


def _close_sqlite_handles() -> None:
    """[B10] SQLite 连接是进程级单例，应用关闭时显式释放（WAL 才能正常收尾）。

    单个连接关闭失败不能影响其余连接，所以逐个 try。
    """
    for name, closer in (
        ("events", lambda: get_event_store().close()),
        ("agent_runs", lambda: get_run_store().close()),
        ("knowledge", lambda: get_knowledge_store().close()),
    ):
        try:
            closer()
        except Exception:  # noqa: BLE001 - 关闭阶段不应再抛出
            logging.getLogger(__name__).exception("关闭 SQLite 连接失败：%s", name)


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    # 启动阶段没有需要初始化的资源；关闭时释放 SQLite 连接
    yield
    _close_sqlite_handles()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="AI Research Workspace backend (Phase 1 skeleton)",
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        default_response_class=UTF8JSONResponse,
        lifespan=_lifespan,
    )

    # [P0] 中间件执行顺序：后注册的在外层。
    # CORS 必须在最外层，否则带错误状态码的响应（401/500）不会带 CORS 头，
    # 浏览器会以「CORS 错误」的形式报错，掩盖真正的错误原因。
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    return app


# uvicorn 的入口：uvicorn app.main:app
app = create_app()
