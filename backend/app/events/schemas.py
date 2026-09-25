"""Agent 事件定义。

[P0] 事件设计的第一原则：**只暴露可公开的执行事实，不暴露模型的隐藏推理**。

可以展示：状态、节点名、工具名、入参摘要、结果摘要、耗时、错误、重试次数。
绝不展示：模型内部 Chain of Thought、完整 prompt、API Key、堆栈细节。

下面每个事件都有一个「前端要展示什么」的明确用途，没有用途的事件不发。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class EventType(StrEnum):
    # --- 生命周期 ---
    TASK_STARTED = "task_started"          # 一次运行开始
    APPROVAL_REQUIRED = "approval_required"  # 需要人工确认（写报告前）
    TASK_COMPLETED = "task_completed"      # 终态：成功
    TASK_FAILED = "task_failed"            # 终态：失败
    TASK_CANCELLED = "task_cancelled"      # 终态：人工拒绝

    # --- 各阶段（都带 started / completed，前端才能算耗时与展示结果摘要）---
    PLANNING = "planning"                  # 生成计划中
    PLAN_CREATED = "plan_created"          # 计划已生成（带步骤数）
    TOOL_STARTED = "tool_started"          # 工具开始（带工具名与入参摘要）
    TOOL_COMPLETED = "tool_completed"      # 工具结束（带 ok / 耗时 / 结果摘要 / 错误）
    RETRIEVAL_STARTED = "retrieval_started"
    RETRIEVAL_COMPLETED = "retrieval_completed"
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETED = "analysis_completed"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    REPORT_STARTED = "report_started"      # 开始撰写报告


# 收到这些事件后，SSE 连接应当关闭（任务已结束）
TERMINAL_EVENTS = frozenset(
    {EventType.TASK_COMPLETED, EventType.TASK_FAILED, EventType.TASK_CANCELLED}
)


class AgentEvent(BaseModel):
    """一次「可观察的事实」。"""

    id: int = Field(description="自增序号，同时用作 SSE 的 Last-Event-ID")
    thread_id: str
    type: str
    ts: str = Field(description="ISO-8601 UTC 时间")
    payload: dict = Field(default_factory=dict)
