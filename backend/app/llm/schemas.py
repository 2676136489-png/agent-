"""LLM request/response schemas.

[P0] 这一层是「我们和 LLM 之间的契约」：
上层（Planner / Writer）只构造 LLMRequest、消费 LLMResponse，
不关心底层是 OpenAI、DeepSeek 还是 Mock。
"""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

# 消息角色只有这三种。用 Literal 而不是 str，写错角色时 Pydantic 会直接报错。
Role = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    """一条对话消息。

    [P0] system / user / assistant 的区别：
    - system：给模型的「角色设定与规则」，优先级最高，用户看不到
    - user：用户说的话（本项目中也包括我们拼装的任务输入）
    - assistant：模型之前说过的话（多轮对话时用来带上下文）
    """

    role: Role
    content: str


class LLMRequest(BaseModel):
    """一次 LLM 调用的输入。"""

    messages: list[ChatMessage]
    model: str | None = Field(default=None, description="覆盖默认模型")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, gt=0)

    # 结构：{"type": "json_object"} 要求模型输出合法 JSON
    response_format: dict[str, Any] | None = None

    # 调用目的，用于日志与后续成本核算（planning / extraction / writing ...）
    purpose: str = "chat"

    # 追踪信息（task_id 等），只进日志，不进 prompt
    metadata: dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    """[P0] Token 用量。

    token 不是字符，也不是单词，而是模型用来计数的「片段」。
    中文通常 1 个字 ≈ 1~2 个 token。它直接决定两件事：
    1) 费用（输入 + 输出分别计价）
    2) 上下文长度上限（超出会被截断或报错）
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    """一次 LLM 调用的输出（已归一化，与具体厂商无关）。"""

    content: str
    model: str
    usage: TokenUsage
    latency_ms: int
    finish_reason: str | None = None
    # 厂商原始响应（调试用）；注意不要在这里放 API Key
    raw: dict[str, Any] | None = None


T = TypeVar("T", bound=BaseModel)


class StructuredResult(BaseModel, Generic[T]):
    """结构化调用的结果：既给解析后的对象，也给原始响应（含 token 与耗时）。"""

    data: T
    response: LLMResponse
