"""节点公共件：依赖注入容器（T03）。

## 为什么要有这一层

改造前，每个节点都要自己 `get_llm_client()` / `build_default_registry()`（见
`nodes.py:_deps`），这三个「进程级单例」的构造逻辑散落在多处：

| 工厂 | 位置 | 被谁调用 |
| --- | --- | --- |
| `get_llm_client()` | `app/llm/client.py:446` | 每个需要 LLM 的节点 |
| `build_default_registry()` | `app/tools/registry.py:39` | 每个需要工具集的节点 |
| `get_search_quota_or_none()` | `app/search/quota.py:702` | 每次真实联网搜索 |

`NodeDeps` 把它们收成一个对象，好处有三条，缺一条这个重构就不成立：

1. **测试不用碰全局单例**：想换假 LLM，构造一个 `NodeDeps(llm=FakeLLMClient(), ...)`
   即可，不用去 patch `app.llm.client` 的函数，也不用构造 `RunnableConfig`。
2. **依赖清单只有一处**：以后新增 `embedder` / `vectorstore`，改这个 dataclass 就够，
   不会出现「某个节点多取了一个依赖、另一个忘了取」。
3. **换 DI 容器只改一个函数**：`resolve_deps()` 是唯一的入口。

⚠️ **单 worker 语义**：`default_deps()` 的 `lru_cache` 是进程内的，
配额锁同样是进程内的 —— 请勿用 `--workers>1` 启动（配额会低估）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Protocol, runtime_checkable

from langchain_core.runnables import RunnableConfig

from app.llm.client import LLMClient, get_llm_client
from app.tools.registry import ToolRegistry, build_default_registry


@runtime_checkable
class Tracer(Protocol):
    """事件打点接口。

    本期只定义不实现：`app/observability/` 尚不存在（PRD §11.1 记为欠账），
    等它落地时按这个 Protocol 填一个实现即可，节点侧一行不用改。
    """

    def event(self, name: str, **fields: object) -> None: ...


class _NoopTracer:
    """什么都不做的 tracer。默认依赖，保证 `NodeDeps` 永远可用。"""

    def event(self, name: str, **fields: object) -> None:
        del name, fields


@dataclass(frozen=True)
class NodeDeps:
    """一个节点运行所需的一切外部依赖。

    - `llm` / `registry`：核心两个
    - `quota: None` = 不计费（离线语料 / 配额关闭）——**测试红线 B 的落点**
    - `tracer`：默认 no-op，预留给 observability
    """

    llm: LLMClient
    registry: ToolRegistry
    quota: object = None  # SearchQuotaStore | None；用 object 避免 import 循环
    tracer: Tracer = _NoopTracer()


@lru_cache(maxsize=1)
def default_deps() -> NodeDeps:
    """进程级单例依赖。替换原先散落三处的工厂调用。

    注意这里**不**传 `tracer`：默认就是 no-op，等 observability 落地后再填。
    """
    from app.search.quota import get_search_quota_or_none

    return NodeDeps(
        llm=get_llm_client(),
        registry=build_default_registry(),  # 复用 registry.py 里已有的 lru_cache
        quota=get_search_quota_or_none(),  # 配额关闭 / DB 不可用 -> None
    )


def resolve_deps(config: RunnableConfig | None) -> NodeDeps:
    """兼容垫片：把旧的 `configurable['client' | 'registry']` 通道继续认账。

    存在的两个理由：
    1. 现有 `tests/test_graph.py` 端到端调用不传 configurable，必须落到 `default_deps()`；
    2. 后续换真正的 DI 容器时，只需改这一个函数。
    """
    configurable = (config or {}).get("configurable") or {}
    base = default_deps()
    injected = configurable.get("deps")
    if isinstance(injected, NodeDeps):
        return injected
    return replace(
        base,
        llm=configurable.get("client") or base.llm,
        registry=configurable.get("registry") or base.registry,
    )
