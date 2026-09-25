"""指标采集模块单元测试（PRD §5.3 / T-metrics）。

覆盖：counter 累加 / 标签顺序无关性 / histogram 统计 / **json 序列化**
/ 快照是拷贝 / reset / 并发不丢更新 / health 端点接入。

跑法（在 backend/ 目录下）：
    .venv/Scripts/python.exe -m pytest tests/test_metrics.py

每个用例开头都 `reset_metrics()`：模块级单例是进程状态，用例之间必须隔离，
否则「concurrent 那个用例跑完 count=8000」会污染后面所有断言。
"""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.observability.metrics import (
    GRAPH_RUN_DURATION_MS,
    SEARCH_CALLS_TOTAL,
    TOOL_CALLS_TOTAL,
    TOOL_DURATION_MS,
    counter_totals_by_label,
    counter_value,
    inc,
    observe,
    reset_metrics,
    snapshot,
)

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_metrics():
    """每个用例前后都清空 —— 模块级单例是跨用例共享的进程状态。"""
    reset_metrics()
    yield
    reset_metrics()


# ---------------------------------------------------------------------------
# counter
# ---------------------------------------------------------------------------


def test_inc_default_adds_one():
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"})
    assert counter_value(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"}) == 1.0


def test_inc_accumulates_same_labels():
    for _ in range(5):
        inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"})
    assert counter_value(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"}) == 5.0


def test_inc_separates_different_labels():
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"})
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "failed"})
    inc(SEARCH_CALLS_TOTAL, {"depth": "advanced", "result": "ok"})

    assert counter_value(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"}) == 1.0
    assert counter_value(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "failed"}) == 1.0
    assert counter_value(SEARCH_CALLS_TOTAL, {"depth": "advanced", "result": "ok"}) == 1.0


def test_inc_supports_explicit_delta():
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"}, value=7)
    assert counter_value(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"}) == 7.0


def test_label_order_does_not_matter():
    """标签顺序无关性 —— 本模块最容易静默出错的地方。

    `{"depth": "basic", "result": "ok"}` 与 `{"result": "ok", "depth": "basic"}`
    是同一件事。若不排序折叠 key，会落进两个 key，数字被悄悄拆成两条。
    """
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"})
    inc(SEARCH_CALLS_TOTAL, {"result": "ok", "depth": "basic"})

    assert counter_value(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"}) == 2.0
    # 反向查询同样命中
    assert counter_value(SEARCH_CALLS_TOTAL, {"result": "ok", "depth": "basic"}) == 2.0

    # 快照里只有一条，不是两条
    counters = snapshot()["counters"]
    matching = [k for k in counters if k.startswith(SEARCH_CALLS_TOTAL)]
    assert len(matching) == 1
    assert counters[matching[0]] == 2.0


def test_boolean_and_int_label_values_are_stringified():
    """`ok=False` 与 `ok="False"` 必须归一 —— 否则前端拿到两个看起来一样的键。"""
    inc(TOOL_CALLS_TOTAL, {"tool": "search_web", "ok": False})
    inc(TOOL_CALLS_TOTAL, {"tool": "search_web", "ok": "False"})

    assert counter_value(TOOL_CALLS_TOTAL, {"tool": "search_web", "ok": False}) == 2.0


def test_negative_delta_is_ignored():
    """counter 只增不减：负增量按 0 处理，且不改变已有值。"""
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"})
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"}, value=-100)
    assert counter_value(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"}) == 1.0


def test_wrong_label_names_are_dropped_not_raised():
    """标签名写错（typo）时静默丢弃 + warning，绝不抛异常拖垮业务。"""
    inc(SEARCH_CALLS_TOTAL, {"depht": "basic", "result": "ok"})  # 故意 typo
    assert snapshot()["counters"] == {}


def test_unknown_metric_name_is_dropped():
    inc("no_such_metric_total", {"a": "b"})
    assert snapshot()["counters"] == {}


def test_counter_totals_by_label_aggregates():
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"})
    inc(SEARCH_CALLS_TOTAL, {"depth": "advanced", "result": "ok"})
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "failed"})

    assert counter_totals_by_label(SEARCH_CALLS_TOTAL, "result") == {"ok": 2.0, "failed": 1.0}
    assert counter_totals_by_label(SEARCH_CALLS_TOTAL, "depth") == {"basic": 2.0, "advanced": 1.0}


# ---------------------------------------------------------------------------
# histogram
# ---------------------------------------------------------------------------


def test_observe_basic_stats():
    for value in (10, 20, 30):
        observe(TOOL_DURATION_MS, value, {"tool": "search_web"})

    stats = snapshot()["histograms"]["tool_duration_ms{tool=search_web}"]
    assert stats["count"] == 3
    assert stats["sum"] == 60.0
    assert stats["avg"] == 20.0
    assert stats["min"] == 10.0
    assert stats["max"] == 30.0


def test_p95_lands_in_a_sane_bucket():
    """19 个样本落在 [10,25] 桶，1 个落在 [500,1000] 桶。

    P95 阈值 = 20 个样本的第 19 个。累计到 25ms 桶时正好 19 个 -> 上界 25.0。
    """
    for _ in range(19):
        observe(TOOL_DURATION_MS, 20, {"tool": "search_web"})
    observe(TOOL_DURATION_MS, 800, {"tool": "search_web"})

    stats = snapshot()["histograms"]["tool_duration_ms{tool=search_web}"]
    assert stats["p95_approx"] == 25.0
    # 明确标记为近似 —— 防止调用方误当精确分位数
    assert stats["p95_is_approximate"] is True


def test_p95_of_empty_histogram_is_zero():
    observe(TOOL_DURATION_MS, 5, {"tool": "x"})
    stats = snapshot()["histograms"]["tool_duration_ms{tool=x}"]
    assert stats["p95_approx"] == 5.0

    reset_metrics()
    assert snapshot()["histograms"] == {}


def test_observe_negative_clamped_to_zero():
    observe(TOOL_DURATION_MS, -50, {"tool": "search_web"})
    stats = snapshot()["histograms"]["tool_duration_ms{tool=search_web}"]
    assert stats["min"] == 0.0
    assert stats["sum"] == 0.0


def test_unlabeled_histogram_works():
    observe(GRAPH_RUN_DURATION_MS, 1234.0)
    stats = snapshot()["histograms"][GRAPH_RUN_DURATION_MS]
    assert stats["count"] == 1
    assert stats["max"] == 1234.0


def test_inc_on_histogram_is_rejected():
    """programming error：对 histogram 调 inc 应被丢弃（不炸、不产生 counter）。"""
    inc(TOOL_DURATION_MS, {"tool": "x"})
    assert snapshot()["counters"] == {}


# ---------------------------------------------------------------------------
# snapshot / 序列化 / 拷贝语义
# ---------------------------------------------------------------------------


def test_snapshot_is_json_serializable():
    """**必测项**。tuple key 会让 json.dumps 直接 TypeError。

    这是 PRD 的硬要求：snapshot() 要被塞进 /api/health 的 JSON 响应。
    """
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"})
    inc(TOOL_CALLS_TOTAL, {"tool": "search_web", "ok": True})
    observe(TOOL_DURATION_MS, 42, {"tool": "search_web"})
    observe(GRAPH_RUN_DURATION_MS, 999)

    payload = snapshot()
    text = json.dumps(payload)  # 不抛异常即通过
    assert isinstance(text, str)

    # 所有 key 必须是 str、所有叶子必须是 JSON 原生类型
    reparsed = json.loads(text)
    assert reparsed == payload
    for key in payload["counters"]:
        assert isinstance(key, str)
    for stats in payload["histograms"].values():
        assert isinstance(stats, dict)
        for leaf in stats.values():
            assert isinstance(leaf, (int, float, str, bool))


def test_snapshot_returns_a_copy():
    """改返回值不能影响内部状态 —— 否则 /api/health 的调用方能手滑污染指标。"""
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"})
    observe(TOOL_DURATION_MS, 10, {"tool": "x"})

    first = snapshot()
    # 恶意改快照
    first["counters"].clear()
    first["histograms"].clear()
    first["meta"]["scope"] = "hacked"

    second = snapshot()
    assert second["counters"]["search_calls_total{depth=basic,result=ok}"] == 1.0
    assert "tool_duration_ms{tool=x}" in second["histograms"]
    assert second["meta"]["scope"] == "process"
    # 两次快照互不影响
    assert first is not second


def test_snapshot_bucket_counts_are_not_shared():
    """histogram 内部的 bucket_counts 是 list —— 必须是拷贝，不能泄露引用。"""
    observe(TOOL_DURATION_MS, 10, {"tool": "x"})
    first = snapshot()
    # 统计里没有裸 bucket 列表（已聚合），但重取不应嗅到上次的东西
    second = snapshot()
    assert first["histograms"] == second["histograms"]


def test_reset_metrics_clears_everything():
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"})
    observe(TOOL_DURATION_MS, 10, {"tool": "x"})
    assert snapshot()["counters"] != {}

    reset_metrics()
    empty = snapshot()
    assert empty["counters"] == {}
    assert empty["histograms"] == {}
    assert counter_value(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"}) == 0.0


# ---------------------------------------------------------------------------
# 并发
# ---------------------------------------------------------------------------


def test_concurrent_inc_does_not_lose_updates():
    """8 线程 × 1000 次 = 恰好 8000。锁一旦漏掉，这里会是随机的较小值。"""
    threads = 8
    per_thread = 1000
    barrier = threading.Barrier(threads)

    def worker() -> None:
        barrier.wait()  # 尽量让所有线程同时抢锁
        for _ in range(per_thread):
            inc(TOOL_CALLS_TOTAL, {"tool": "search_web", "ok": True})

    pool = [threading.Thread(target=worker) for _ in range(threads)]
    for thread in pool:
        thread.start()
    for thread in pool:
        thread.join()

    value = counter_value(TOOL_CALLS_TOTAL, {"tool": "search_web", "ok": True})
    assert value == threads * per_thread == 8000.0


def test_concurrent_observe_does_not_lose_updates():
    """histogram 走的是同一把锁，同样必须无丢失。"""
    threads = 4
    per_thread = 500

    def worker() -> None:
        for _ in range(per_thread):
            observe(TOOL_DURATION_MS, 15, {"tool": "search_web"})

    pool = [threading.Thread(target=worker) for _ in range(threads)]
    for thread in pool:
        thread.start()
    for thread in pool:
        thread.join()

    stats = snapshot()["histograms"]["tool_duration_ms{tool=search_web}"]
    assert stats["count"] == threads * per_thread == 2000
    assert stats["sum"] == 2000 * 15.0


# ---------------------------------------------------------------------------
# 端点接入
# ---------------------------------------------------------------------------


def test_health_endpoint_exposes_json_serializable_metrics():
    inc(SEARCH_CALLS_TOTAL, {"depth": "basic", "result": "ok"})
    observe(TOOL_DURATION_MS, 33, {"tool": "search_web"})

    client = TestClient(create_app())
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    metrics = body["data"]["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["counters"]["search_calls_total{depth=basic,result=ok}"] == 1.0
    assert "tool_duration_ms{tool=search_web}" in metrics["histograms"]


def test_health_endpoint_has_metrics_key_even_when_empty():
    """没有指标时 metrics 也必须是 dict（不是 null）—— 前端不用写 null 分支。"""
    client = TestClient(create_app())
    body = client.get("/api/health").json()
    metrics = body["data"]["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["counters"] == {}
    assert metrics["histograms"] == {}


def test_health_endpoint_survives_metrics_failure(monkeypatch):
    """指标模块炸了，健康检查必须仍然 200 —— 探针不能因旁路模块挂掉。"""
    from app.api.routes import health as health_module

    def boom() -> dict:
        raise RuntimeError("simulated metrics failure")

    monkeypatch.setattr(health_module, "metrics_snapshot", boom)

    client = TestClient(create_app())
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["metrics"] == {}
