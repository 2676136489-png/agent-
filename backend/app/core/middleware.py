"""HTTP middlewares.

[P2] 当前只需知道它做了两件事：给每个请求生成 request_id、打印访问日志。

request_id 的作用：前端报错时只要把这个 ID 给你，
你就能在后端日志里精确定位到那一次请求（后面 Agent 有几十次工具调用时，这个是刚需）。

注意：这里用 BaseHTTPMiddleware 是为了可读性（写法接近普通函数）。
后面做 SSE 长连接时会换成纯 ASGI 中间件，因为 BaseHTTPMiddleware
对流式响应有已知的性能与行为问题——这是明确的「技术债」，先欠着。
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger("access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # 如果调用方（例如前端或网关）已经传了 request_id 就沿用，方便跨服务串联
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # 异常会交给 exception handler 处理，这里只负责记录耗时
            logger.error("request_id=%s %s %s failed", request_id, request.method, request.url.path)
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_id=%s %s %s -> %s (%.2fms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
