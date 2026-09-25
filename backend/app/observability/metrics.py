"""进程内统计指标采集（PRD §5.3）。

## 为什么是「纯 dict + threading.Lock」，而不是 prometheus_client

PRD §5.3 明确要求**零新依赖**。理由不只是「少一个包」：
`prometheus_client` 的价值在于**跨进程聚合 + 拉取式导出**，而本项目的
生产形态是**单进程单 worker**（见 `app/search/quota.py` 顶部 docstring），
进程内 dict 的语义完全够用。多引一个依赖换来的只是运维成本。

代价必须写明：**进程重启后计数归零**，且多 worker 下每个进程各记一份、
互不可见。所以 `snapshot()` 的语义是「本进程启动以来」，不是「服务启动以来」。

## 三个设计约束（都是被坑出来的）

1. **标签 key 必须是 tuple，不能是 dict。** Python 的 dict 不可哈希，
   拿 dict 当内层 key 会直接 `TypeError: unhashable type: 'dict'`。
   本模块统一用 `_counter_key()` 把标签折成 `tuple[str, ...]`。
   并且**标签名按字母序排序**后再取值 —— 否则同一次业务事件，调用方
   只要写成 `{"depth": .., "result": ..}` 和 `{"result": .., "depth": ..}`
   就会落进两个 key，指标被静默拆成两条。这是本模块最容易踩的坑。

2. **tuple 键不能直接进 JSON。** `json.dumps({(1, 2): 3})` 在默认
   `skipkeys=False` 下会抛 `TypeError: keys must be str, int, float, bool or None`。
   `snapshot()` 是给 `/api/health` 直接塞进响应的，所以必须在**边界处**
   把 tuple 键转成可读的 string 键（`"depth=basic|result=ok"`）。
   测 `snapshot()` 能不能 `json.dumps` 是**必测项**，不是可选项。

3. **锁内只 copy，不做计算。** histogram 的 P95 近似、counter 的比率
   聚合都放在锁外做。否则一个 10ms 的聚合会把所有写指标的线程堵住 ——
   指标是旁路，绝不能让旁路拖慢主路。

## histogram 的 P95 是**近似值**

不保留全量样本（那是无界内存增长，长跑服务必然 OOM），只维护固定分桶计数。
P95 = 「第一个累计计数 ≥ 总计数 95% 的桶上界」。误差上界 = 一个桶宽。
分桶见 `HISTOGRAM_BUCKETS_MS`：毫秒量级，1ms 起步、10s 封顶。

**调用方拿到的是近似 P95，不要当精确分位数用。** 用于「服务是不是整体变慢了」
这类趋势判断完全够（能分辨 50ms 和 500ms），但不要拿它做过 SLA 断言。

## 为什么不用 dataclass 做返回类型

`snapshot()` 的返回值要**直接**进 Pydantic 响应体。dataclass 实例不行
（Pydantic v2 会尝试解析它，字段多一层可能失败），numpy 更不行。
纯 `int/float/str/list/dict` 是唯一不会在边界上炸的选择。
"""

from __future__ import annotations

import logging
import threading
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 指标名常量。写死成常量而不是让调用方传字符串：
# 调用方拼错指标名时是**静默**产生一条新指标，而不是报错 —— 常量能让这类
# typo 在 import 期就被发现（getattr / 覆盖率都能盯住）。
# ---------------------------------------------------------------------------
SEARCH_CALLS_TOTAL = "search_calls_total"
SEARCH_CREDITS_USED_TOTAL = "search_credits_used_total"
QUOTA_WARNING_TOTAL = "quota_warning_total"
TOOL_CALLS_TOTAL = "tool_calls_total"
TOOL_DURATION_MS = "tool_duration_ms"
LLM_CALLS_TOTAL = "llm_calls_total"
LLM_TOKENS_TOTAL = "llm_tokens_total"
GRAPH_RUN_TOTAL = "graph_run_total"
GRAPH_RUN_DURATION_MS = "graph_run_duration_ms"

#: histogram 的固定分桶上界，单位毫秒。最后一个桶是 10s，更慢的一律归入它。
HISTOGRAM_BUCKETS_MS: tuple[float, ...] = (
    1.0,
    5.0,
    10.0,
    25.0,
    50.0,
    100.0,
    250.0,
    500.0,
    1000.0,
    2500.0,
    5000.0,
    10000.0,
)

#: 哪些指标是 histogram、哪些是 counter。`inc()` 调用 histogram、
#: `observe()` 调用 counter 都是编程错误，这里显式拒绝 + 记 warning。
_HISTOGRAM_NAMES: frozenset[str] = frozenset({TOOL_DURATION_MS, GRAPH_RUN_DURATION_MS})

#: 每个 counter 的合法标签名（顺序无关，集合比较）。空集合 = 无标签。
#:
#: 为什么要白名单：标签名拼错（`depht`）会静默开一条新序列，一晚上下来
#: 指标表里全是拼写变体。显式校验让错误在第一次写入时就炸出来。
_COUNTER_LABEL_NAMES: dict[str, frozenset[str]] = {
    SEARCH_CALLS_TOTAL: frozenset({"depth", "result"}),
    SEARCH_CREDITS_USED_TOTAL: frozenset({"depth"}),
    QUOTA_WARNING_TOTAL: frozenset({"level"}),
    TOOL_CALLS_TOTAL: frozenset({"tool", "ok"}),
    LLM_CALLS_TOTAL: frozenset({"purpose", "kind"}),
    LLM_TOKENS_TOTAL: frozenset({"purpose", "token_type"}),
    GRAPH_RUN_TOTAL: frozenset({"status", "finished_reason"}),
}

_HISTOGRAM_LABEL_NAMES: dict[str, frozenset[str]] = {
    TOOL_DURATION_MS: frozenset({"tool"}),
    GRAPH_RUN_DURATION_MS: frozenset(),
}


# ---------------------------------------------------------------------------
# 内部存储
# ---------------------------------------------------------------------------


class _Histogram:
    """固定分桶的直方图。只存计数，不存样本 —— 内存 O(桶数)，与调用量无关。

    同时维护 `count/sum/min/max`：平均耗时用 sum/count 精确算，
    只有 P95 是近似的（桶上界）。min/max 是精确的（逐条比较）。
    """

    __slots__ = ("bucket_counts", "count", "sum", "min", "max")

    def __init__(self, bucket_count: int) -> None:
        # 下标 i 对应 HISTOGRAM_BUCKETS_MS[i] 这个**上界**（含）。
        # bucket_count = len(buckets) + 1，最后一个是 +inf 溢出桶。
        self.bucket_counts: list[int] = [0] * (bucket_count + 1)
        self.count: int = 0
        self.sum: float = 0.0
        self.min: float = 0.0
        self.max: float = 0.0

    def record(self, value: float) -> None:
        """记一个样本。调用方必须已持有全局锁。"""
        index = len(HISTOGRAM_BUCKETS_MS)  # 默认落进溢出桶
        for i, upper in enumerate(HISTOGRAM_BUCKETS_MS):
            if value <= upper:
                index = i
                break
        self.bucket_counts[index] += 1
        self.count += 1
        self.sum += value
        if self.count == 1:
            self.min = value
            self.max = value
        else:
            if value < self.min:
                self.min = value
            if value > self.max:
                self.max = value


# 全局状态。`_lock` 同时保护两个 dict。
_lock = threading.Lock()
_counters: dict[tuple[str, tuple[str, ...]], float] = {}
_histograms: dict[tuple[str, tuple[str, ...]], _Histogram] = {}


# ---------------------------------------------------------------------------
# 标签归一化
# ---------------------------------------------------------------------------


def _counter_key(labels: dict[str, Any] | None) -> tuple[str, ...]:
    """把标签折成**顺序无关**的稳定 key：`("depth=basic", "result=ok")`。

    两个关键点：

    1. **排序**。`sorted(labels.items())` 保证 `{"a":1,"b":2}` 与
       `{"b":2,"a":1}` 落到同一个 key。不排序就会静默拆成两条指标 ——
       这是指标模块最隐蔽的 bug，因为它不报错、只是数字对不上。
    2. **值转 str**。标签值可能是 `bool`（`ok=False`）或 `int`
       （`credits=2`）。统一 `str()` 化，否则同一个语义
       （`ok=False` 与 `ok="False"`）会分叉。

    返回 tuple（可哈希），不是 dict —— dict 不可哈希，做不了 key。
    """
    if not labels:
        return ()
    return tuple(f"{name}={value}" for name, value in sorted(labels.items()))


def _label_names(labels: dict[str, Any] | None) -> frozenset[str]:
    return frozenset(labels.keys()) if labels else frozenset()


def _validate_counter_labels(name: str, labels: dict[str, Any] | None) -> bool:
    """校验 counter 的标签名是否在该指标的名单里。不合法返回 False（调用方丢弃）。"""
    allowed = _COUNTER_LABEL_NAMES.get(name)
    if allowed is None:
        logger.warning("未知的 counter 指标名 name=%s，本次计数被忽略", name)
        return False
    actual = _label_names(labels)
    if actual != allowed:
        logger.warning(
            "counter %s 的标签不匹配：期望 %s，收到 %s，本次计数被忽略",
            name,
            sorted(allowed),
            sorted(actual),
        )
        return False
    return True


def _validate_histogram_labels(name: str, labels: dict[str, Any] | None) -> bool:
    """校验 histogram 的标签名。不合法返回 False。"""
    allowed = _HISTOGRAM_LABEL_NAMES.get(name)
    if allowed is None:
        logger.warning("未知的 histogram 指标名 name=%s，本次观测被忽略", name)
        return False
    actual = _label_names(labels)
    if actual != allowed:
        logger.warning(
            "histogram %s 的标签不匹配：期望 %s，收到 %s，本次观测被忽略",
            name,
            sorted(allowed),
            sorted(actual),
        )
        return False
    return True


# ---------------------------------------------------------------------------
# 写入侧
# ---------------------------------------------------------------------------


def inc(name: str, labels: dict[str, Any] | None = None, value: float = 1.0) -> None:
    """counter 自增。

    设计取舍：
    - **标签非法时丢弃并 log warning，不抛异常。** 指标是旁路，一个统计 bug
      不该把主业务打挂。这与 `get_search_quota_or_none()` 的降级哲学一致。
    - **counter 只增不减。** `value` 为负数时记 warning 并按 0 处理 ——
      允许减的「counter」会让上游的 `rate()` 语义失效，也掩盖记账 bug。
      需要减的场景（如额度退款）应该用两条不同标签的 counter，而不是负数。
    """
    if value < 0:
        logger.warning("counter %s 收到负增量 value=%s，按 0 处理", name, value)
        return
    if not _validate_counter_labels(name, labels):
        return

    key = (name, _counter_key(labels))
    with _lock:
        _counters[key] = _counters.get(key, 0.0) + value


def observe(name: str, value_ms: float, labels: dict[str, Any] | None = None) -> None:
    """histogram 记一次观测。`value_ms` 单位毫秒。

    与 `inc()` 同样的降级策略：标签非法只 warning，不抛。
    负值按 0 处理 —— 负耗时一定是上游的 bug（时钟回拨 / 单位搞错），
    记进去会污染 min 和 P95，所以夹到 0 并 warning。
    """
    if value_ms < 0:
        logger.warning("histogram %s 收到负值 value_ms=%s，按 0 处理", name, value_ms)
        value_ms = 0.0
    if not _validate_histogram_labels(name, labels):
        return

    key = (name, _counter_key(labels))
    with _lock:
        hist = _histograms.get(key)
        if hist is None:
            hist = _Histogram(len(HISTOGRAM_BUCKETS_MS))
            _histograms[key] = hist
        hist.record(float(value_ms))


# ---------------------------------------------------------------------------
# 读取侧
# ---------------------------------------------------------------------------


def _format_key(name: str, label_key: tuple[str, ...]) -> str:
    """tuple key -> 人类可读的字符串 key，用于 JSON 序列化。

    `"search_calls_total{depth=basic,result=ok}"` —— 把指标名也编进去，
    因为 `/api/health` 的 `metrics` 会按「指标名 -> 各标签组合」两层组织，
    但 counter 在一个扁平 dict 里时名字是唯一区分度。
    """
    if not label_key:
        return name
    return f"{name}{{{','.join(label_key)}}}"


def counters_snapshot() -> dict[str, float]:
    """所有 counter 的扁平快照：`{"search_calls_total{depth=basic,result=ok}": 3.0}`。

    锁内只做 copy，不排序、不聚合。返回**深拷贝后的新 dict** ——
    调用方改了它不影响内部状态（有测试盯着这条）。
    """
    with _lock:
        raw = dict(_counters)
    return {
        _format_key(name, label_key): float(value) for (name, label_key), value in raw.items()
    }


def histogram_stats() -> dict[str, dict[str, Any]]:
    """所有 histogram 的聚合快照（平均 / 近似 P95 / min / max）。

    锁内只 copy 桶计数与汇总值，P95 的**近似计算放在锁外** ——
    遍历 13 个桶虽快，但没有理由把它塞进临界区去堵写线程。
    """
    with _lock:
        raw = {
            _format_key(name, label_key): (
                list(hist.bucket_counts),
                hist.count,
                hist.sum,
                hist.min,
                hist.max,
            )
            for (name, label_key), hist in _histograms.items()
        }

    result: dict[str, dict[str, Any]] = {}
    for key, (bucket_counts, count, total, minimum, maximum) in raw.items():
        result[key] = {
            "count": int(count),
            "sum": float(total),
            "avg": round(total / count, 4) if count > 0 else 0.0,
            "min": float(minimum),
            "max": float(maximum),
            "p95_approx": _approximate_p95(bucket_counts, count),
            "p95_is_approximate": True,
        }
    return result


def _approximate_p95(bucket_counts: list[int], count: int) -> float:
    """P95 近似：返回「第一个使累计计数 ≥ ceil(count * 0.95) 的桶上界」。

    - `count == 0` -> 返回 0.0（不是 None，JSON 里 null 会让前端分支变多）。
    - 落进溢出桶（最后一个）-> 返回最后一个桶的上界（10000.0），这是**下界**
      而不是上界，但比返回 `inf`（JSON 里非法）安全。
    """
    if count <= 0:
        return 0.0
    threshold = max(1, -(-count * 95 // 100))  # 向上取整的 95%，纯整数运算避免浮点误差
    cumulative = 0
    for index, bucket_count in enumerate(bucket_counts):
        cumulative += bucket_count
        if cumulative >= threshold:
            if index < len(HISTOGRAM_BUCKETS_MS):
                return float(HISTOGRAM_BUCKETS_MS[index])
            return float(HISTOGRAM_BUCKETS_MS[-1])
    # 理论上走不到这里（cumulative 最终必等于 count >= threshold）
    return float(HISTOGRAM_BUCKETS_MS[-1])


def snapshot() -> dict[str, Any]:
    """返回**纯 JSON 可序列化**的全量指标快照。

    形状（两层结构，前端好渲染）：
        {
          "counters": {"search_calls_total{depth=basic,result=ok}": 3.0, ...},
          "histograms": {"tool_duration_ms{tool=search_web}": {...}, ...},
          "meta": {"histogram_buckets_ms": [...], "p95_is_approximate": True}
        }

    **所有 key 都是 str、所有叶子都是 int/float/str/list/dict。** 没有 tuple key、
    没有 dataclass 实例、没有 numpy —— 因为它会被直接塞进 `/api/health` 的
    JSON 响应，任何非 JSON 类型都会在序列化那一刻 500。
    """
    return {
        "counters": counters_snapshot(),
        "histograms": histogram_stats(),
        "meta": {
            "histogram_buckets_ms": [float(b) for b in HISTOGRAM_BUCKETS_MS],
            "p95_is_approximate": True,
            "scope": "process",  # 单 worker 单进程；重启归零
        },
    }


def counter_value(
    name: str, labels: dict[str, Any] | None = None
) -> float:
    """查单个 counter 的当前值（测试与断言用，不必解构 snapshot）。

    不存在的 key 返回 0.0 —— counter 的「未出现」与「出现过 0 次」数值上等价，
    让调用方少写一次 `.get(key, 0)`。
    """
    key = (name, _counter_key(labels))
    with _lock:
        return float(_counters.get(key, 0.0))


def counter_totals_by_label(name: str, label_name: str) -> dict[str, float]:
    """把某个 counter 按指定标签名聚合：返回 `{标签值: 合计}`。

    给「搜索失败率」这类派生指标用 —— 失败率 = failed / (ok+failed+...)，
    需要按 `result` 分组求和，但调用方不该自己解析 tuple key。
    """
    prefix = f"{label_name}="
    with _lock:
        raw = dict(_counters)
    totals: Counter[str] = Counter()
    for (metric_name, label_key), value in raw.items():
        if metric_name != name:
            continue
        for part in label_key:
            if part.startswith(prefix):
                totals[part[len(prefix) :]] += value
                break
    return {label_value: float(total) for label_value, total in totals.items()}


def reset_metrics() -> None:
    """清空全部计数。

    **只应在测试里调用。** 生产环境没有任何调用点：指标是「本进程启动以来」的
    累计值，运行期清零会让 `/api/health` 上的数字凭空倒退，把「一直在失败」
    伪装成「突然变好了」。测试里每个用例开头调一次，避免用例互相污染。
    """
    with _lock:
        _counters.clear()
        _histograms.clear()
