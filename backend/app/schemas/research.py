"""Research domain schemas.

[P0] ResearchPlan 是本阶段的核心数据结构：
它既是「LLM 的输出约束」（通过 model_json_schema 传给模型），
也是「前端要渲染的结构」，还是「后面 Agent 要执行的输入」。
一处定义，三处复用 —— 这就是用 Pydantic 建模的收益。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PlanStep(BaseModel):
    """研究计划中的一步。"""

    index: int = Field(default=1, ge=1, description="步骤序号，从 1 开始")
    title: str = Field(default="", min_length=1, max_length=100, description="步骤标题")
    instruction: str = Field(
        default="", min_length=1, max_length=500, description="这一步具体要做什么"
    )

    @field_validator("title", "instruction", mode="before")
    @classmethod
    def _ensure_str(cls, value: object) -> str:
        return str(value) if value is not None else ""


class ResearchPlan(BaseModel):
    """一份研究计划。

    [P0] 四个字段全部必填：模型漏掉任何一个都视为「输出不符合 schema」，
    由上层决定是否重试。这样能保证前端拿到的 plan 一定有目标、子问题、步骤与来源。
    """

    goal: str = Field(min_length=1, max_length=500, description="这项研究要达成的目标")
    questions: list[str] = Field(description="需要回答的子问题")
    steps: list[PlanStep] = Field(description="有序的执行步骤")
    expected_sources: list[str] = Field(description="期望的来源类型（不要写具体 URL）")

    @field_validator("goal", mode="before")
    @classmethod
    def _ensure_goal(cls, value: object) -> str:
        return str(value) if value is not None else ""

    @field_validator("questions", "expected_sources", mode="before")
    @classmethod
    def _coerce_str_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return []

    @field_validator("steps", mode="before")
    @classmethod
    def _normalize_steps(cls, value: object) -> list[dict]:
        if value is None:
            return []
        if isinstance(value, dict):
            # 模型偶尔把 steps 包成 {"step": [...]} 之类的 dict，尝试兜底
            for key in ("steps", "items", "list"):
                if key in value:
                    value = value[key]
                    break
            else:
                return []
        if not isinstance(value, list):
            return []
        normalized: list[dict] = []
        for i, item in enumerate(value, start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "") or f"步骤 {i}")
            instruction = str(item.get("instruction", "") or "模型未给出具体说明")
            normalized.append(
                {
                    "index": item.get("index") if item.get("index") is not None else i,
                    "title": title,
                    "instruction": instruction,
                }
            )
        return normalized


class PlanRequest(BaseModel):
    """POST /api/research/plan 的请求体。"""

    question: str = Field(
        min_length=8,
        max_length=2000,
        description="用户的研究问题",
        examples=["研究 2026 年 AI Agent 开发岗位的主要技术要求"],
    )
    max_steps: int = Field(default=6, ge=3, le=10, description="计划最多包含几步")


class PlanResponse(BaseModel):
    """POST /api/research/plan 的响应 data。"""

    plan: ResearchPlan
    model: str
    provider: str
    # 明确告诉前端「这是假数据」，避免把 Mock 结果当成真实模型输出
    mock: bool
    usage: dict
    latency_ms: int
