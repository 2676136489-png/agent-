"""Agent loop tests (using the offline Mock LLM).

跑法：uv run pytest
"""

from __future__ import annotations

from app.agent.orchestrator import run_agent
from app.llm.client import MockLLMClient
from app.llm.schemas import LLMResponse, StructuredResult, TokenUsage
from app.llm.structured import parse_structured_payload
from app.tools.registry import build_default_registry

QUESTION = "研究 2026 年 AI Agent 开发岗位的主要技术要求，需要引用来源。"


async def test_agent_runs_loop_and_calls_a_tool():
    result = await run_agent(
        question=QUESTION,
        client=MockLLMClient(),
        registry=build_default_registry(),
        max_steps=4,
    )

    # 1) 确实调用了工具
    assert len(result.tool_calls) >= 1
    assert result.tool_calls[0].tool == "search_web"
    assert result.tool_calls[0].ok is True
    # 2) 每一步都记录了耗时
    assert result.tool_calls[0].duration_ms >= 0
    # 3) 最终有答案，且正常结束
    assert result.answer
    assert result.finished_reason == "final_answer"
    # 4) 有 token 与总耗时（可观测性）
    assert result.usage["total_tokens"] >= 0
    assert result.latency_ms >= 0


async def test_agent_stops_within_max_steps():
    result = await run_agent(
        question=QUESTION,
        client=MockLLMClient(),
        registry=build_default_registry(),
        max_steps=2,
    )
    assert len(result.steps) <= 3  # 最多 2 步 + 1 次强制收尾
    assert result.answer


class _UnknownToolLLM:
    """模拟模型编造了一个不存在的工具名。"""

    provider_name = "fake"

    async def complete(self, request: object) -> LLMResponse:
        payload = (
            '{"action": {"tool": "run_shell_command",'
            ' "args": {"cmd": "rm -rf /"}, "reason": "想执行系统命令"}}'
        )
        return LLMResponse(
            content=payload,
            model="fake",
            usage=TokenUsage(),
            latency_ms=0,
        )

    async def complete_structured(self, request: object, schema):
        response = await self.complete(request)
        data = parse_structured_payload(response.content, schema)
        return StructuredResult(data=data, response=response)


async def test_unknown_tool_is_blocked_not_executed():
    """模型提名的工具不在注册表里 → 被拒绝，且循环不崩溃。"""
    result = await run_agent(
        question=QUESTION,
        client=_UnknownToolLLM(),  # type: ignore[arg-type]
        registry=build_default_registry(),
        max_steps=2,
    )

    assert result.tool_calls[0].tool == "run_shell_command"
    assert result.tool_calls[0].ok is False
    assert result.tool_calls[0].error_kind == "blocked"
    # 关键：系统命令从未被执行，Agent 也没有崩
    assert result.answer
