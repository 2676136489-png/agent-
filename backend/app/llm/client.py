"""LLM clients.

[P0] 三个核心设计：

1. **Protocol（协议）而不是具体类**
   上层只依赖 `LLMClient` 这个接口，所以换厂商、换 Mock 都不用改业务代码。

2. **模板方法（BaseLLMClient）**
   `complete_structured()` 对所有实现都一样：先拿到文本 → 解析 → 校验。
   所以只有 `complete()` 需要每个厂商自己实现。

3. **工厂 + 依赖注入**
   `get_llm_client()` 决定用哪个实现，FastAPI 通过 `Depends` 注入，
   测试里可以一行替换成 Mock。
"""

from __future__ import annotations

import json
import logging
import re
import time
from functools import lru_cache
from typing import Protocol, TypeVar, runtime_checkable

import openai
from pydantic import BaseModel
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import Settings, get_settings
from app.core.security import UNTRUSTED_BLOCK_BEGIN as OBSERVATION_MARKER
from app.llm.errors import LLMError
from app.llm.schemas import ChatMessage, LLMRequest, LLMResponse, StructuredResult, TokenUsage
from app.llm.structured import parse_structured_payload

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class LLMClient(Protocol):
    """LLM 能力的最小接口。"""

    provider_name: str

    async def complete(self, request: LLMRequest) -> LLMResponse: ...

    async def complete_structured(
        self,
        request: LLMRequest,
        schema: type[T],
    ) -> StructuredResult[T]: ...


class BaseLLMClient:
    """所有 client 共享的 structured 逻辑。"""

    provider_name: str = "base"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    async def complete_structured(
        self,
        request: LLMRequest,
        schema: type[T],
    ) -> StructuredResult[T]:
        response = await self.complete(request)
        try:
            data = parse_structured_payload(response.content, schema)
        except LLMError as exc:
            # [B6] 输出被 max_tokens 截断时，解析失败的根因不是"模型乱写"，
            # 而是 token 预算不够（思考型模型尤其常见：推理过程会吃掉预算）。
            # 这种情况重试 N 次也不会变好，必须给出可操作的错误信息。
            if response.finish_reason == "length":
                raise LLMError(
                    f"模型输出被 max_tokens 截断（finish_reason=length），"
                    f"结构化输出不完整，请调大 LLM_MAX_TOKENS。原始错误：{exc.message}",
                    kind="truncated",
                    retryable=False,
                ) from exc
            raise
        return StructuredResult(data=data, response=response)


def _is_ollama(base_url: str | None) -> bool:
    """判断上游是不是 Ollama。

    [B5] `keep_alive` / `think` 是 Ollama 的私有扩展字段。
    之前对所有 OpenAI 兼容厂商无条件下发，对 OpenAI / DeepSeek / 通义等
    属于未知字段，轻则被忽略、重则 400；而且实测 `think:false` 并不能
    真正关闭 qwen3 的思考（仍返回 reasoning），所以更要收窄作用范围。
    """
    lowered = (base_url or "").lower()
    return "11434" in lowered or "ollama" in lowered


class OpenAICompatibleClient(BaseLLMClient):
    """OpenAI 兼容协议的 client。

    之所以叫 Compatible：DeepSeek、通义千问、Moonshot、智谱、混元等都提供
    OpenAI 同构的 /chat/completions 接口，换 base_url + model 即可切换，
    业务代码零改动。
    """

    provider_name = "openai-compatible"

    def __init__(
        self,
        api_key: str,
        base_url: str | None,
        model: str,
        timeout_seconds: float,
        max_attempts: int,
    ) -> None:
        # 注意：api_key 只从这里传入，绝不写进日志
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or None,
            timeout=timeout_seconds,
            max_retries=0,  # SDK 自带重试关掉，统一由 tenacity 控制（便于记录每次重试）
        )
        self._model = model
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        # [B5] 只对 Ollama 下发私有扩展字段
        self._ollama_extra_body = (
            {"keep_alive": 0, "think": False} if _is_ollama(base_url) else None
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        payload: dict = {
            "model": request.model or self._model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format:
            payload["response_format"] = request.response_format
        if self._ollama_extra_body:
            payload["extra_body"] = self._ollama_extra_body

        retryer = AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            # 只对「可重试」错误重试：认证失败、参数非法不重试
            retry=retry_if_exception(lambda exc: isinstance(exc, LLMError) and exc.retryable),
            reraise=True,
        )

        started = time.perf_counter()
        async for attempt in retryer:
            with attempt:
                try:
                    raw = await self._client.chat.completions.create(**payload)
                except Exception as exc:  # 统一把 SDK 异常翻译成 LLMError
                    llm_error = self._to_llm_error(exc)
                    logger.warning(
                        "LLM call failed (purpose=%s, attempt=%s): %s",
                        request.purpose,
                        attempt.retry_state.attempt_number,
                        llm_error,
                    )
                    raise llm_error from exc

                latency_ms = int((time.perf_counter() - started) * 1000)
                return self._to_response(raw, latency_ms)

        raise LLMError("unreachable", kind="unknown", retryable=False)

    @staticmethod
    def _to_llm_error(exc: Exception) -> LLMError:
        """把 openai SDK 的异常映射成我们自己的错误类型，并判定是否值得重试。"""
        if isinstance(exc, openai.APITimeoutError):
            return LLMError("调用超时", kind="timeout", retryable=True)
        if isinstance(exc, openai.APIConnectionError):
            return LLMError("网络连接失败", kind="connection", retryable=True)
        if isinstance(exc, openai.RateLimitError):
            return LLMError("被限流（429）", kind="rate_limit", status_code=429, retryable=True)
        if isinstance(exc, openai.AuthenticationError):
            return LLMError(
                "API Key 无效或已失效", kind="auth", status_code=401, retryable=False
            )
        if isinstance(exc, openai.APIStatusError):
            status = exc.status_code
            return LLMError(
                f"上游返回 {status}",
                kind="server" if status >= 500 else "invalid_request",
                status_code=status,
                retryable=status >= 500 or status == 429,
            )
        if isinstance(exc, openai.APIError):
            return LLMError(f"上游错误：{exc.message}", kind="upstream", retryable=True)
        return LLMError(f"未知错误：{exc}", kind="unknown", retryable=False)

    @staticmethod
    def _to_response(raw, latency_ms: int) -> LLMResponse:
        choice = raw.choices[0]
        usage = getattr(raw, "usage", None)
        return LLMResponse(
            content=choice.message.content or "",
            model=getattr(raw, "model", "unknown"),
            usage=TokenUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                total_tokens=getattr(usage, "total_tokens", 0) or 0,
            ),
            latency_ms=latency_ms,
            finish_reason=getattr(choice, "finish_reason", None),
        )


class MockLLMClient(BaseLLMClient):
    """离线兜底 client。

    [P2] 存在的真实原因：没有 API Key 也能跑通「前端 → 后端 → Agent 循环」全链路，
    否则本地开发、自动化测试、CI 全都依赖外部付费服务。
    目前覆盖两个 purpose：planning（生成计划）与 agent_step（Agent 循环中的决策）。
    """

    provider_name = "mock"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if request.purpose not in _MOCK_PURPOSES:
            raise LLMError(
                f"MockLLMClient 不支持 purpose='{request.purpose}'，"
                f"支持：{', '.join(sorted(_MOCK_PURPOSES))}",
                kind="invalid_request",
                retryable=False,
            )

        question = _extract_question(request.messages)
        payload = _mock_payload(request, question)
        content = json.dumps(payload, ensure_ascii=False)
        model = f"mock-{request.purpose}"

        return LLMResponse(
            content=content,
            model=model,
            # 粗略估算，仅用于让前端能显示「有数字」
            usage=TokenUsage(
                prompt_tokens=max(1, len(question) // 2),
                completion_tokens=max(1, len(content) // 2),
                total_tokens=max(1, len(question) // 2 + len(content) // 2),
            ),
            latency_ms=0,
            finish_reason="stop",
        )


# Mock 支持的调用目的。每新增一个 LLM 调用点，都要在这里补一份 fixture。
_MOCK_PURPOSES = frozenset(
    {
        "planning",
        "agent_step",
        "understand_task",
        "plan",
        "research_decision",
        "analyze",
        "verify",
        "write",
    }
)


def _extract_question(messages: list[ChatMessage]) -> str:
    """从模板化的 user message 里取出真正的问题文本。"""
    raw = next(
        (m.content for m in reversed(messages) if m.role == "user"),
        "",
    )
    for marker in ("研究问题：", "研究任务：", "任务："):
        if marker in raw:
            return raw.split(marker, 1)[1].strip().split("\n")[0][:200]
    return raw[:200]


def _count_mentioned_evidence(request: LLMRequest) -> int:
    """从请求里读出「已经有 N 条证据」。

    Mock 需要它来决定「还要不要再查一次」，从而让图的循环真的能被观察到。

    [A7] 优先读结构化的 `metadata["evidence_count"]`，读不到再回落到正则。
    之前只有正则一条路：prompt 文案一改，Mock 的收敛判断就悄悄失效，
    而测试仍然全绿（因为断言的是"跑完了"，不是"跑了几轮"）。
    """
    meta = request.metadata or {}
    value = meta.get("evidence_count")
    if isinstance(value, int):
        return value

    raw = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
    match = re.search(r"(?:已经有\s*|证据条数：)\s*(\d+)\s*条?", raw)
    return int(match.group(1)) if match else 0


def _mock_payload(request: LLMRequest, question: str) -> dict:
    """按调用目的返回确定性的假数据。"""
    purpose = request.purpose
    topic = question.strip().rstrip("。.?？") or "未命名研究主题"

    if purpose == "understand_task":
        return {
            "goal": f"搞清楚「{topic}」的现状与关键结论",
            "key_questions": [
                f"{topic} 的关键事实是什么？",
                f"哪些来源对 {topic} 的说法更可信？",
            ],
            "scope": "仅基于可获得的公开资料，不推测未公开信息",
        }

    if purpose in ("plan", "planning"):
        return _build_mock_plan(question)

    # research_decision 走 LangGraph 的 research 节点；agent_step 走 Phase 3 的手写循环
    if purpose in ("research_decision", "agent_step"):
        return _mock_agent_decision(request, question)

    if purpose == "analyze":
        return {
            "findings": [
                f"关于「{topic}」，已检索到的资料提供了初步证据（Mock 数据）。",
                "不同来源在细节上存在差异，需要更多证据才能定论（Mock 数据）。",
            ],
            "gaps": ["缺少一手来源", "样本量不足"],
        }

    if purpose == "verify":
        # 证据少于 2 条判定为不足 —— 这样 verify → research 的循环能在 Mock 下被观察到
        count = _count_mentioned_evidence(request)
        enough = count >= 2
        return {
            "verdict": "pass" if enough else "needs_more",
            "reasons": [f"当前证据 {count} 条，{'足以支撑初步结论' if enough else '尚不充分'}"],
            "missing": [] if enough else ["补充一手来源", "交叉验证关键数据"],
        }

    if purpose == "write":
        return {
            "title": f"{topic} — 研究报告（Mock）",
            "summary": f"（Mock 数据）围绕「{topic}」的初步结论，基于离线语料生成。",
            "sections": [
                {"heading": "结论", "content": "（Mock）已获得的证据支持初步结论，但样本有限。"},
                {"heading": "证据概览", "content": "（Mock）证据来自离线语料，仅用于验证流程。"},
            ],
            "limitations": ["当前为离线 Mock 模式，结论不具备事实效力"],
        }

    return _build_mock_plan(question)


def _mock_agent_decision(request: LLMRequest, question: str) -> dict:
    """模拟 Agent 循环中的一步决策。

    逻辑很简单（也更好调试）：
    - 上下文里还没有任何工具结果 → 先调 search_web
    - 已经有工具结果了 → 收敛，给出 final_answer
    """
    messages = request.messages
    has_observation = any(
        message.role == "user" and OBSERVATION_MARKER in message.content for message in messages
    )
    # research 节点会在 metadata 里写明「已经有 N 条证据」（正则只是兜底），
    # 够 2 条就收尾，这样「research → research → …」的循环在 Mock 下也能被真实跑出来。
    evidence_count = _count_mentioned_evidence(request)

    if not (has_observation or evidence_count >= 2):
        return {
            "action": {
                "tool": "search_web",
                "args": {"query": question[:80], "max_results": 5},
                "reason": "先检索候选来源，再决定是否需要读取正文",
            }
        }

    if has_observation:
        observation = next(
            message.content
            for message in reversed(messages)
            if message.role == "user" and OBSERVATION_MARKER in message.content
        )
        evidence = observation.split("----\n", 1)[-1][:800]
    else:
        evidence = "（已有若干条证据，此处省略）"
    return {
        "final_answer": (
            "（Mock 数据，非真实检索结果）\n\n"
            f"针对「{question}」，检索到的资料摘要如下：\n\n{evidence}\n\n"
            "以上是离线语料，仅用于验证 Agent 循环本身是否跑通。"
        )
    }


def _build_mock_plan(question: str) -> dict:
    """根据问题文本生成一份确定性的研究计划（离线可测）。"""
    topic = question.strip().rstrip("。.?？") or "未命名研究主题"
    return {
        "goal": f"围绕「{topic}」形成有证据支撑、可复核的结论",
        "questions": [
            f"{topic} 的现状与关键事实是什么？",
            f"哪些来源对 {topic} 的描述存在分歧？",
            "基于现有信息，可以给出什么可执行的结论？",
        ],
        "steps": [
            {
                "index": 1,
                "title": "明确研究范围",
                "instruction": f"界定「{topic}」的边界：时间范围、地域范围、对象范围",
            },
            {
                "index": 2,
                "title": "检索核心来源",
                "instruction": "针对每个子问题检索权威来源，记录 URL、标题与发布时间",
            },
            {
                "index": 3,
                "title": "抽取结构化证据",
                "instruction": "从来源中抽取可引用的原文片段，标注来源与位置",
            },
            {
                "index": 4,
                "title": "交叉验证",
                "instruction": "对比不同来源的说法，标出一致点与冲突点",
            },
            {
                "index": 5,
                "title": "形成结论",
                "instruction": "基于证据给出结论，并说明置信度与局限",
            },
        ],
        "expected_sources": [
            "官方一手来源（官网 / 官方文档 / 公告）",
            "行业权威媒体或研究报告",
            "可交叉验证的第三方数据",
        ],
    }


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """根据配置决定用哪个 client。

    provider=auto 时：有 Key 就走真实 API，没 Key 就退化成 Mock，
    保证「clone 下来就能跑」，不会因为缺 Key 直接 500。
    """
    settings: Settings = get_settings()
    provider = settings.llm_provider

    if provider == "auto":
        provider = "openai" if settings.llm_api_key.get_secret_value() else "mock"

    if provider == "mock":
        logger.warning("LLM_PROVIDER=mock：将使用离线假数据，不会产生真实模型调用")
        return MockLLMClient()

    return OpenAICompatibleClient(
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_attempts=settings.llm_max_attempts,
    )
