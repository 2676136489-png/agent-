"""Health check payload."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthData(BaseModel):
    """GET /api/health 的 data 部分。

    为什么要包含 environment / version：
    部署后最容易出的低级错误是「跑的不是我以为的那份代码」。
    把环境和版本暴露出来，一眼就能确认连对了服务。

    为什么要包含 metrics（PRD §5.3）：
    存活探针顺带就能看出「服务是不是在降级运行」—— 搜索失败率、额度预警、
    LLM 失败率都在这一个字段里，不用再加一个 `/metrics` 端点。类型故意放宽成
    `dict` 而不是定死 schema：指标维度后续会增删，定死只会逼着每次加一个
    counter 就动一次响应契约。`default_factory=dict` 保证老代码不传也能构造
    （向后兼容），健康检查因此永远不会因为「没喂 metrics」而解析失败。
    """

    status: str = Field(description="Service status, 'ok' when healthy")
    app_name: str
    environment: str
    version: str
    timestamp: datetime = Field(description="Server time in UTC")
    metrics: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "本进程启动以来的指标快照（counter + histogram 聚合）。"
            "进程内累计、重启归零；采集失败时为空 dict，不影响存活判定。"
        ),
    )
