"""LLM layer errors.

[P1] 关键设计：错误分「可重试」和「不可重试」两类。
- 超时、限流、5xx：重试有意义，重试可能成功
- 认证失败、参数非法、账户余额不足：重试 100 次也一样失败，只会浪费时间
"""

from __future__ import annotations


class LLMError(Exception):
    def __init__(
        self,
        message: str,
        *,
        kind: str = "upstream",
        status_code: int | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.status_code = status_code
        self.retryable = retryable

    def __str__(self) -> str:
        base = f"[{self.kind}] {self.message}"
        if self.status_code:
            base += f" (status={self.status_code})"
        return base
