"""Agent decision & trace schemas.

[P0] 这里有两类模型：
1. AgentDecision —— **模型每轮要输出的结构**（约束模型）
2. *Record —— **我们记录的轨迹**（给前端展示、给未来的 Evaluation 用）

区分它们很重要：前者要尽可能严格（防止模型乱来），后者要尽可能完整（方便排查）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ToolCallRequest(BaseModel):
    """模型提名的一次工具调用。注意：只是「提名」，能不能执行由 Registry 决定。"""

    tool: str = Field(description="工具名称，必须是可用工具之一")
    args: dict = Field(default_factory=dict, description="工具参数，必须符合该工具的 schema")
    reason: str = Field(default="", max_length=300, description="为什么在这一步用这个工具")


class AgentDecision(BaseModel):
    """模型每一步的输出：要么调用一个工具，要么给出最终答案。"""

    action: ToolCallRequest | None = None
    final_answer: str | None = None

    @model_validator(mode="after")
    def _exactly_one_choice(self) -> AgentDecision:
        """[P0] 必须二选一。

        为什么要这条校验：模型经常「既要又要」（同时给 action 和 final_answer）
        或者「都不要」（两个都空）。前者会让我们白跑一轮，后者会让循环卡死。
        校验失败会抛可重试错误，让模型重新生成一次，通常就好了。
        """
        has_action = self.action is not None
        has_answer = bool(self.final_answer and self.final_answer.strip())
        if has_action == has_answer:
            raise ValueError(
                "必须且只能选择一项：调用一个工具(action) 或 给出最终答案(final_answer)"
            )
        return self


class ToolCallRecord(BaseModel):
    """一次工具调用的完整记录（可观测性的原子单位）。"""

    index: int
    tool: str
    args: dict
    ok: bool
    error: str | None = None
    error_kind: str | None = None  # invalid_args | timeout | execution_error | blocked
    output_preview: str = ""
    duration_ms: int = 0


class AgentStepRecord(BaseModel):
    """Agent 循环中的一步。"""

    index: int
    reason: str | None = None
    tool_call: ToolCallRecord | None = None
    final_answer: str | None = None


class AgentRunResult(BaseModel):
    """一次 Agent 运行的最终结果 + 完整轨迹。"""

    question: str
    answer: str
    steps: list[AgentStepRecord]
    tool_calls: list[ToolCallRecord]
    finished_reason: str  # final_answer | max_steps_reached | timeout | llm_error
    # 本次运行中，工具实际引用到的来源（document_id / chunk_id / page / quote）
    citations: list[dict] = []
    usage: dict
    latency_ms: int
    mock: bool
