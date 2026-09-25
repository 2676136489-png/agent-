"""System health endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.responses import ApiResponse, success_response
from app.observability.metrics import snapshot as metrics_snapshot
from app.schemas.health import HealthData

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


def _safe_metrics_snapshot() -> dict[str, Any]:
    """取指标快照；任何异常都降级成空 dict，绝不让健康检查 500。

    为什么必须 try/except：`GET /api/health` 是**存活探针**。探针挂了，
    编排层会把整个服务判定为不可用并重启 —— 而指标只是**增强项**。
    「增强项故障拖垮主功能」是典型的本末倒置，所以这里与
    `app/search/quota.py:get_search_quota_or_none()` 同一个哲学：
    出问题就降级返回空值 + 记日志，把排查线索留在日志里，而不是 500 里。
    """
    try:
        return metrics_snapshot()
    except Exception:  # noqa: BLE001 - 探针绝不能因旁路模块抛异常
        logger.exception("指标快照采集失败，/api/health 降级为不带 metrics 返回")
        return {}


@router.get(
    "/health",
    response_model=ApiResponse[HealthData],
    summary="Service health check",
)
async def get_health(settings: Settings = Depends(get_settings)) -> ApiResponse[HealthData]:
    """返回服务存活状态与环境信息。

    [P0] `Depends(get_settings)` 是 FastAPI 的依赖注入：
    框架会在调用前自动执行 get_settings() 并把结果作为参数传进来。
    好处是这个函数的「依赖」是显式声明的，测试时可以替换掉它（后面会用到）。
    """
    return success_response(
        HealthData(
            status="ok",
            app_name=settings.app_name,
            environment=settings.environment,
            version=settings.version,
            timestamp=datetime.now(UTC),
            metrics=_safe_metrics_snapshot(),
        )
    )
