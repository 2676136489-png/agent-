"""Agent endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agent.orchestrator import run_agent
from app.agent.schemas import AgentRunResult
from app.core.errors import AppError, ErrorCode
from app.core.responses import ApiResponse, success_response
from app.llm.client import LLMClient, get_llm_client
from app.llm.errors import LLMError
from app.schemas.agent import AgentRunRequest
from app.tools.registry import ToolRegistry, build_default_registry

router = APIRouter(prefix="/agent", tags=["agent"])


def get_tool_registry() -> ToolRegistry:
    """注册表里有哪些工具是**代码决定的**，模型无法扩充。"""
    return build_default_registry()


@router.post(
    "/run",
    response_model=ApiResponse[AgentRunResult],
    summary="Run the minimal tool-calling agent loop",
)
async def run_agent_endpoint(
    payload: AgentRunRequest,
    client: LLMClient = Depends(get_llm_client),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> ApiResponse[AgentRunResult]:
    """执行一个最小的 Tool Calling 循环并返回完整轨迹。"""
    try:
        result = await run_agent(
            question=payload.question,
            client=client,
            registry=registry,
            max_steps=payload.max_steps,
        )
    except LLMError as exc:
        raise AppError(
            code=ErrorCode.UPSTREAM_ERROR,
            message=f"大模型调用失败：{exc.message}",
            status_code=502,
            details={"kind": exc.kind, "retryable": exc.retryable},
        ) from exc

    return success_response(result)
