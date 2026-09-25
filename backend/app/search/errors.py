"""搜索配额相关的异常。

分层：
- `SearchProviderError`：provider 抛出的「需要翻译成 ToolResult.error_kind」的错误。
  工具层（`BaseTool.execute`）负责把它翻译成 error_kind，**翻译规则只有这一处**。
- `QuotaExhaustedError`：额度不足。工具层**绝不重试**（重试就是继续烧积分）。
"""

from __future__ import annotations


class SearchProviderError(RuntimeError):
    """搜索 provider 抛出的、需要被工具层翻译成 error_kind 的错误。

    [T02] 为什么用异常而不是返回值：
    当前的 `TavilySearchProvider.search()` 在失败时 `return []`，
    导致「额度耗尽」和「真的没搜到」在调用方眼里完全一样（PRD P-1 的病根）。
    用异常 + 明确的 error_kind，调用方无法「忘记」处理它。
    """

    def __init__(self, message: str, *, error_kind: str = "execution_error") -> None:
        super().__init__(message)
        self.error_kind = error_kind
        self.message = message


class QuotaExhaustedError(SearchProviderError):
    """余额不足以支付本次搜索。

    由 `SearchQuotaStore.reserve()` 或 provider 在收到 402 / 余额不足的 429 时抛出。
    携带 `credits_remaining` / `deficit` 便于给用户可操作的提示。
    """

    def __init__(
        self,
        message: str,
        *,
        error_kind: str = "quota_exhausted",
        credits_remaining: int = 0,
        deficit: int = 0,
    ) -> None:
        super().__init__(message, error_kind="quota_exhausted")
        self.message = message
        self.credits_remaining = credits_remaining
        self.deficit = deficit
