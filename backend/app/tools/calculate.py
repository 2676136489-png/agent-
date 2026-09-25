"""calculate tool —— 安全的数学表达式求值。

[P0] 为什么绝不能用 eval()：
eval("__import__('os').system('rm -rf /')") 会直接执行系统命令。
模型输出的内容是**不可信的输入**，任何 eval/exec 都等于把服务器交给模型。

正确做法：先用 ast 解析成语法树，只允许数字运算相关的节点类型，
确认安全后再用 eval 执行（此时 builtins 已被清空）。
"""

from __future__ import annotations

import ast

from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolContext

# 白名单：只允许这些语法节点，其余一律拒绝
_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
)

_MAX_EXPRESSION_LENGTH = 100
_MAX_POWER_EXPONENT = 100  # 防止 9**9**9 这类算力 DoS
_MAX_RESULT_BITS = 100_000  # 结果整数的二进制位数上限（约 3 万位十进制）


def _const_eval(node: ast.AST) -> float | None:
    """静态估算一个「纯常量子表达式」的值；估算不出来返回 None。

    [B1] 为什么需要它：只看 Pow 的右操作数是不是字面常量是不够的。
    `9**9**9` 的外层右操作数是一个 BinOp（9**9），旧实现直接放行，
    于是真的去算 9 ** 387420489 —— 一次调用就能把 CPU 占满。
    而 safe_eval 是同步 CPU 计算，asyncio.wait_for 中断不了它，
    结果是整个服务的事件循环被冻结。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _const_eval(node.operand)
        if value is None:
            return None
        return -value if isinstance(node.op, ast.USub) else value

    if isinstance(node, ast.BinOp):
        left = _const_eval(node.left)
        right = _const_eval(node.right)
        if left is None or right is None:
            return None
        try:
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                # 估算本身也不能爆炸：超限直接返回 inf，由调用方判定为"过大"
                if abs(right) > _MAX_POWER_EXPONENT or abs(left) > 1e6:
                    return float("inf")
                return left**right
        except (OverflowError, ValueError, ZeroDivisionError):
            return float("inf")

    return None


class CalculateArgs(BaseModel):
    expression: str = Field(
        min_length=1,
        max_length=_MAX_EXPRESSION_LENGTH,
        description="数学表达式，例如 (1200 + 380) * 0.15",
    )


def safe_eval(expression: str) -> float:
    """在 AST 白名单约束下求值。任何不合规的结构都会抛 ValueError。"""
    tree = ast.parse(expression, mode="eval")

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"不允许的语法：{type(node).__name__}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError("只允许数字常量")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            # [B1] 递归求指数的**值**，而不是只看它是不是字面常量。
            # 这样 9**9**9、9**(9+9)**9 这类嵌套幂都会被拦下。
            exponent = _const_eval(node.right)
            if exponent is None or exponent != exponent:  # 无法估算 / NaN
                raise ValueError("幂运算的指数无法静态估算")
            if exponent > _MAX_POWER_EXPONENT:
                raise ValueError("幂运算的指数过大")

    # builtins 清空：即使有漏网之鱼，也拿不到 __import__ / open / exec
    result = eval(compile(tree, "<calculate>", "eval"), {"__builtins__": {}}, {})  # noqa: S307
    if not isinstance(result, (int, float)):
        raise ValueError("结果不是数字")
    # 最后一道闸：结果本身也不能大到离谱（例如一长串乘法拼出来的巨数）
    if isinstance(result, int) and result.bit_length() > _MAX_RESULT_BITS:
        raise ValueError("计算结果过大")
    return result


class CalculateTool(BaseTool):
    name = "calculate"
    description = "计算数学表达式（仅支持数字与 + - * / // % ** 和括号），用于统计与换算。"
    args_schema = CalculateArgs
    timeout_seconds = 2.0

    async def _run(self, args: BaseModel, ctx: ToolContext) -> str:
        assert isinstance(args, CalculateArgs)
        # 计算失败抛异常，由 BaseTool.execute 统一转成 ok=False 的 ToolResult。
        # 这样模型看到的才是「这个工具失败了」，而不是一段伪装成成功的文本。
        value = safe_eval(args.expression)
        return f"{args.expression} = {value}"
