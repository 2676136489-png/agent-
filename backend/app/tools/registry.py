"""Tool registry.

[P0] 注册表的作用只有一个：把「模型给出的工具名」映射成「我们真实存在的工具对象」。
这一步是安全边界 —— 模型只能提名，能不能执行由这里说了算：
不在注册表里的名字一律拒绝，所以模型永远不可能凭空创造出一个工具（包括系统命令）。
"""

from __future__ import annotations

from functools import lru_cache

from app.tools.base import BaseTool


class ToolNotFoundError(Exception):
    pass


class ToolRegistry:
    def __init__(self, tools: list[BaseTool]) -> None:
        self._tools: dict[str, BaseTool] = {tool.name: tool for tool in tools}

    def get(self, name: str) -> BaseTool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(
                f"未知工具：{name}。可用工具：{', '.join(sorted(self._tools))}"
            )
        return tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def function_schemas(self) -> list[dict]:
        """给 prompt / function calling 用的工具清单。"""
        return [tool.function_schema() for tool in self._tools.values()]


@lru_cache(maxsize=1)
def build_default_registry() -> ToolRegistry:
    """组装默认工具集。新增工具只需要在这里加一行。

    [B15] 每个图节点都会调用一次这个函数，之前每次都重建全部工具实例。
    注册表是无状态的（工具本身不保存请求上下文，上下文由 ToolContext 传入），
    缓存一份即可。
    """
    from app.tools.calculate import CalculateTool
    from app.tools.fetch_webpage import FetchWebpageTool
    from app.tools.search_knowledge_base import SearchKnowledgeBaseTool
    from app.tools.search_web import SearchWebTool

    return ToolRegistry(
        [
            SearchWebTool(),
            FetchWebpageTool(),
            CalculateTool(),
            SearchKnowledgeBaseTool(),
        ]
    )
