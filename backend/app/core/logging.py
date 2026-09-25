"""Logging setup.

[P2] 当前阶段当黑盒使用即可：你只需要知道 `configure_logging(level)` 在启动时被调用一次。
为什么需要结构化格式：后面 Agent 的每一步都要靠日志排查（哪个工具、耗时多久、为什么重试），
统一格式才能让日志可被检索，而不是靠肉眼在杂乱输出里找。
"""

from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str) -> None:
    """配置根 logger。应在应用启动时调用一次。"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        stream=sys.stdout,
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
    )

    # uvicorn 自带的 access log 与我们的 RequestContextMiddleware 重复，
    # 这里把它调高到 WARNING，避免每条请求打两遍。
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
