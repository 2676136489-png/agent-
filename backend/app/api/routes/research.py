"""Research endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.errors import AppError, ErrorCode
from app.core.responses import ApiResponse, success_response
from app.llm.client import LLMClient, get_llm_client
from app.llm.errors import LLMError
from app.schemas.research import PlanRequest, PlanResponse
from app.services.planning_service import create_research_plan

router = APIRouter(prefix="/research", tags=["research"])


@router.post(
    "/plan",
    response_model=ApiResponse[PlanResponse],
    summary="Generate a structured research plan with LLM",
)
async def generate_plan(
    payload: PlanRequest,
    client: LLMClient = Depends(get_llm_client),
) -> ApiResponse[PlanResponse]:
    """把用户的研究问题交给 LLM，返回结构化研究计划。

    [P1] 错误处理策略：
    LLM 是外部依赖，它失败不能让前端看到 500 堆栈。
    统一翻译成 UPSTREAM_ERROR + 502，并把「是哪一类失败」写进 message。
    """
    try:
        plan = await create_research_plan(
            client=client,
            question=payload.question,
            max_steps=payload.max_steps,
        )
    except LLMError as exc:
        raise AppError(
            code=ErrorCode.UPSTREAM_ERROR,
            message=f"大模型调用失败：{exc.message}",
            status_code=502,
            details={"kind": exc.kind, "retryable": exc.retryable},
        ) from exc

    return success_response(plan)
