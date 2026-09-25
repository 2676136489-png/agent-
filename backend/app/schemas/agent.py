"""Agent run API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    """POST /api/agent/run 的请求体。"""

    question: str = Field(
        min_length=8,
        max_length=2000,
        description="研究任务",
        examples=["研究 2026 年 AI Agent 开发岗位的主要技术要求"],
    )
    max_steps: int = Field(default=6, ge=1, le=12, description="Agent 最多走几步")
