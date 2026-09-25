"""可观测性层。

当前只包含进程内指标采集（`metrics.py`）。后续 tracing（架构文档 §6.1）
也会落在这里 —— 那时 `app/search/quota.py` 里 `_run_id_var` / `run_context`
这两个函数会整体迁过来，所以这个包不叫 `metrics` 而叫 `observability`。
"""

from __future__ import annotations

from app.observability.metrics import (
    HISTOGRAM_BUCKETS_MS,
    counters_snapshot,
    histogram_stats,
    inc,
    observe,
    reset_metrics,
    snapshot,
)

__all__ = [
    "HISTOGRAM_BUCKETS_MS",
    "counters_snapshot",
    "histogram_stats",
    "inc",
    "observe",
    "reset_metrics",
    "snapshot",
]
