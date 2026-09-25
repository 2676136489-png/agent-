"""Search providers.

为什么要有这一层：搜索是外部依赖（Tavily / Brave / Serper...），
但 Agent 只关心「给我结果列表」。抽象出来后：
- 没有 Key 时用离线语料，本地开发和测试照样能跑通整个 Agent 循环
- 配了真实搜索 Key 后自动切换，工具代码一行不用改

选择逻辑（get_search_provider）：
- search_provider="auto"（默认）：有 TAVILY_API_KEY 走 Tavily 真实联网，否则回退离线语料
- search_provider="tavily"：强制 Tavily（没 Key 则告警并回退离线语料）
- search_provider="stub"：始终使用离线示例语料

## 配额（T02）

真实 provider 每次请求前都会 `reserve()`（预扣），请求结束后 `settle()`（确认）或
`release()`（退款）。失败不再 `return []` 冒充成功 —— 那样会让「额度耗尽」和「真的没搜到」
在调用方眼里完全一样（PRD P-1 的病根）。取而代之的是抛出带 error_kind 的异常，
由 `BaseTool.execute` 翻译成 `ToolResult.error_kind`。

`StubSearchProvider.billed = False` 是**测试红线**（架构文档红线 B）：
离线语料路径完全不触碰配额存储，否则 `tests/test_tools.py::test_search_web_returns_results`
会因为「额度为 0」而变红。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Callable, Protocol

import httpx
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.search.errors import QuotaExhaustedError, SearchProviderError
from app.search.quota import (
    CREDITS_BY_DEPTH,
    DEFAULT_DEPTH,
    SearchQuotaStore,
    current_run_id,
    credits_for,
)

logger = logging.getLogger(__name__)

_TAVILY_ENDPOINT = "https://api.tavily.com/search"


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    source: str = "unknown"


class SearchProvider(Protocol):
    async def search(
        self, query: str, limit: int, *, run_key: str | None = None
    ) -> list[SearchResult]: ...
    """`run_key` 用于把这一次搜索记到 run 账本上；离线实现可以忽略它。"""

    @property
    def billed(self) -> bool:
        """是否产生真实计费。

        `StubSearchProvider` → False（测试红线 B：离线语料不计费）；
        `TavilySearchProvider` → True。
        """

    @property
    def depth(self) -> str:
        """本次搜索的 search_depth（'advanced' | 'basic'），仅真实 provider 有意义。"""


# 离线语料（仅用于本地跑通链路，不是真实搜索结果）
_OFFLINE_CORPUS: list[SearchResult] = [
    SearchResult(
        title="AI Agent 开发岗位技能要求综述（示例语料）",
        url="https://example.com/agent-job-skills",
        snippet=(
            "示例语料：AI Agent 岗位普遍要求 Python/TypeScript、LLM API 集成、"
            "Prompt 工程、RAG 与向量检索、工具调用与 Agent 编排、可观测性与评测。"
        ),
    ),
    SearchResult(
        title="Research Agent 的架构实践（示例语料）",
        url="https://example.com/research-agent-architecture",
        snippet=(
            "示例语料：Research Agent 通常拆为 Planner / Researcher / Extractor / "
            "Writer；关键是证据留存与来源追溯，而不是多轮对话本身。"
        ),
    ),
    SearchResult(
        title="RAG 中的 Chunking 与引用策略（示例语料）",
        url="https://example.com/rag-chunking-citation",
        snippet=(
            "示例语料：chunk size 与 overlap 影响召回质量；每条切片应携带 "
            "document_id、page、source，以便回答时给出可点击的引用。"
        ),
    ),
    SearchResult(
        title="Tool Calling 的可靠性问题（示例语料）",
        url="https://example.com/tool-calling-reliability",
        snippet=(
            "示例语料：工具调用失败主要来自参数不合法、超时、以及模型误解工具用途；"
            "需要 schema 校验、超时控制和把错误信息回灌给模型。"
        ),
    ),
    SearchResult(
        title="Agent 评测指标（示例语料）",
        url="https://example.com/agent-evaluation-metrics",
        snippet=(
            "示例语料：常用指标包括任务成功率、工具成功率、引用覆盖率、"
            "答案相关性、延迟、token 用量与成本。"
        ),
    ),
]


class StubSearchProvider:
    """离线搜索：按关键词在内置语料里做简单打分。

    它的唯一目的是让链路可运行。接真实搜索时新增一个 Provider 即可。

    [红线 B] `billed = False`：离线语料不计费，绝不触碰 SearchQuotaStore。
    判断走的是「类型的固有属性」而不是 `isinstance`，避免以后有人改坏了。
    """

    billed = False
    depth = "none"

    async def search(
        self,
        query: str,
        limit: int,
        *,
        run_key: str | None = None,
    ) -> list[SearchResult]:
        # `run_key` 对离线语料毫无意义（`billed = False`，不写 run 账本）。
        # 签名要和 TavilySearchProvider 保持一致，否则工具层的调用点会 TypeError。
        del run_key
        keywords = [word for word in query.lower().replace("的", " ").split() if len(word) >= 2]

        def score(item: SearchResult) -> int:
            text = f"{item.title} {item.snippet}".lower()
            return sum(1 for word in keywords if word in text)

        ranked = sorted(_OFFLINE_CORPUS, key=score, reverse=True)
        return ranked[:limit]


class TavilySearchProvider:
    """Tavily 搜索：Agent 场景最常用的联网搜索，返回干净的结果列表，对中文友好。

    文档：https://docs.tavily.com/  —— 需要 TAVILY_API_KEY。

    配额生命周期（**顺序不能改**）：
        reserve()  -> 发请求 -> settle()（成功/疑似受理）/ release()（上游拒绝受理）

    `search_depth` 由 `SEARCH_DEPTH` 配置决定，默认 `basic`：
    basic = 1 credit/次、advanced = 2 credits/次。默认走 basic 是为了让 Tavily
    免费额度（1000 credits/月）能完整覆盖约 1000 次搜索；切回 advanced 会立刻
    缩水到约 500 次。质量优先的场景可以在 .env 里显式设 `SEARCH_DEPTH=advanced`。
    """

    billed = True

    def __init__(
        self,
        api_key: str,
        *,
        quota: SearchQuotaStore | None = None,
        depth: str | None = None,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self._api_key = api_key
        settings: Settings = get_settings()
        requested = (depth or settings.search_depth or DEFAULT_DEPTH).strip().lower()
        if requested not in CREDITS_BY_DEPTH:
            logger.warning(
                "未知的 SEARCH_DEPTH=%r，退回 %s（%d credits/次）",
                requested,
                DEFAULT_DEPTH,
                credits_for(DEFAULT_DEPTH),
            )
            requested = DEFAULT_DEPTH
        self._depth = requested
        self._credits = credits_for(self._depth)
        self._quota = quota
        # 只给测试用的注入点（httpx.MockTransport 需要），生产路径保持默认。
        self._client_factory = client_factory

    @property
    def depth(self) -> str:
        return self._depth

    @property
    def credits(self) -> int:
        return self._credits

    async def search(
        self,
        query: str,
        limit: int,
        *,
        run_key: str | None = None,
    ) -> list[SearchResult]:
        reservation = self._begin(run_key=run_key or current_run_id())

        try:
            payload = {
                "api_key": self._api_key,
                "query": query,
                "max_results": min(limit, 10),
                "search_depth": self._depth,
                "include_answer": False,
                "include_raw_content": False,
            }
            client = self._client_factory or (lambda: httpx.AsyncClient(timeout=20.0))
            async with client() as http:
                resp = await http.post(_TAVILY_ENDPOINT, json=payload)
            status = resp.status_code
        except httpx.TimeoutException:
            # 超时也可能已被受理，保守处理：不退款，只记一次失败调用
            self._settle_failed(reservation, "timeout")
            return []
        except httpx.TransportError:
            self._settle_failed(reservation, "network")
            return []

        if status >= 400:
            return self._handle_error_status(status, reservation)

        self._settle_ok(reservation)
        data = resp.json()
        results: list[SearchResult] = []
        for item in data.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    source="tavily",
                )
            )
        return results[:limit]

    # ---------------- 配额交互 ----------------

    def _begin(self, *, run_key: str | None) -> object:
        """发起请求前预扣。返回 None 表示不计费（provider 被构造时没给配额）。"""
        if self._quota is None:
            return None
        reservation = self._quota.try_reserve(depth=self._depth, run_key=run_key)
        if reservation is None:
            remaining = self._quota.remaining_credits()
            raise QuotaExhaustedError(
                f"搜索额度不足：本次搜索需要 {self._credits} credits，"
                f"本期剩余 {remaining} credits，下月 1 日重置。"
                f"可在设置里用 search_depth 切换档位（basic = 1 credit/次）以节省额度，"
                f"或等本期额度重置。",
                credits_remaining=remaining,
                deficit=self._credits - remaining,
            )
        return reservation

    def _settle_ok(self, reservation: object) -> None:
        if reservation is None or self._quota is None:
            return
        self._quota.settle(reservation.reservation_id)  # type: ignore[attr-defined]

    def _settle_failed(self, reservation: object, kind: str) -> None:
        if reservation is None or self._quota is None:
            return
        self._quota.settle(reservation.reservation_id, failed=True, kind=kind)  # type: ignore[attr-defined]

    def _release(self, reservation: object, *, degraded: bool) -> None:
        if reservation is None or self._quota is None:
            return
        self._quota.release(reservation.reservation_id, degraded=degraded)  # type: ignore[attr-defined]

    # ---------------- 错误分类（429 的两义性） ----------------

    def _classify_status(self, status: int) -> str:
        """把 HTTP 状态码翻译成 error_kind。

        429 有两义性：Tavily 用同一个码既表示「额度耗尽」也表示「请求太频繁」。
        区别在于**预扣之后余额还够不够**：
        - 余额已被预扣到不足 → 额度耗尽，必须熔断且不重试（重试就是继续烧积分）
        - 余额充足 → 只是被限流，可以重试 1 次
        """
        if status == 402:
            return "quota_exhausted"
        if status == 429:
            if self._quota is not None and self._quota.remaining_credits() < self._credits:
                return "quota_exhausted"
            return "rate_limit"
        if status >= 500:
            return "upstream_5xx"
        return "request_error"

    def _handle_error_status(self, status: int, reservation: object) -> list[SearchResult]:
        kind = self._classify_status(status)
        if kind in ("quota_exhausted", "rate_limit"):
            # 上游没有受理这次请求：把预扣退回去，谁都没花钱
            self._release(reservation, degraded=kind == "quota_exhausted")
            message = (
                f"搜索服务返回 HTTP {status}（{kind}）："
                f"本次搜索额度已用尽，本报告可能缺少联网证据。"
                if kind == "quota_exhausted"
                else f"搜索服务返回 HTTP 429（请求太频繁）：请稍后重试。"
            )
            if kind == "quota_exhausted":
                raise QuotaExhaustedError(message)
            raise SearchProviderError(message, error_kind="rate_limit")

        self._settle_failed(reservation, kind)
        return []


@lru_cache(maxsize=1)
def get_search_provider() -> SearchProvider:
    """按配置选择搜索实现。

    auto 模式下：检测到 TAVILY_API_KEY 就走真实联网，否则静默回退离线语料，
    保证「clone 下来就能跑」且「配了 Key 自动联网」。
    """
    settings: Settings = get_settings()
    provider = settings.search_provider.strip().lower()

    if provider == "stub":
        return StubSearchProvider()

    if provider in ("auto", "tavily"):
        api_key = settings.tavily_api_key.get_secret_value()
        if api_key:
            logger.info("搜索使用 Tavily 真实联网搜索")
            # 配额单例在 DB 不可用时会自动降级成 None（不计费），不在这里判断，
            # 免得把「降级」这个决策散落到调用方。
            from app.search.quota import get_search_quota_or_none

            return TavilySearchProvider(api_key, quota=get_search_quota_or_none())
        if provider == "tavily":
            logger.warning("SEARCH_PROVIDER=tavily 但未配置 TAVILY_API_KEY，回退离线示例语料")
        else:
            logger.info("未配置 TAVILY_API_KEY，搜索回退到离线示例语料")
        return StubSearchProvider()

    logger.warning("未知 SEARCH_PROVIDER=%s，回退离线示例语料", provider)
    return StubSearchProvider()
