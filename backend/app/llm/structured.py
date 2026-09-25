"""把 LLM 返回的文本解析成 Pydantic 对象。

[P0] 这里是「Structured Output」真正落地的地方。
模型输出的是字符串，我们的程序要的是对象；这个转换必须：
1) 容错（模型经常在 JSON 外面包一层 ```json 代码块）
2) 严格（不符合 schema 就抛错，让上层决定重试还是报错）
"""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.errors import LLMError

T = TypeVar("T", bound=BaseModel)


def _strip_code_fence(text: str) -> str:
    """去掉模型常用的 ```json ... ``` 包裹。"""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _maybe_unwrap(payload: object, schema: type[T]) -> object:
    """模型偶尔把 JSON 再包一层，例如 {"description": {"findings": [...]}}。

    实测 qwen3 会把 JSON Schema 顶层的 "description" 当成要输出的字段名，
    真正的结构被塞进内层，于是校验拿到的是一个没有目标字段的对象
    —— 表现为「模型什么都没输出」，非常难排查。

    规则：外层只有一个键、值是 dict、且这个键不是 schema 的字段 → 解包。
    """
    if not isinstance(payload, dict) or len(payload) != 1:
        return payload
    key, value = next(iter(payload.items()))
    if isinstance(value, dict) and key not in schema.model_fields:
        return value
    return payload


def parse_structured_payload(content: str, schema: type[T]) -> T:
    """把模型输出解析为 schema 实例。失败时抛出可重试的 LLMError。"""
    cleaned = _strip_code_fence(content)

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        # 兜底：模型可能在 JSON 前后加了说明文字，截取第一个 { 到最后一个 }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMError(
                f"模型输出不是 JSON（前 200 字符）：{content[:200]}",
                kind="parse",
                retryable=True,
            ) from None
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"模型输出 JSON 解析失败：{exc}", kind="parse", retryable=True) from exc

    try:
        return schema.model_validate(_maybe_unwrap(payload, schema))
    except ValidationError as exc:
        # 字段缺失或类型不对：把「哪个字段错了」写进日志友好的 message
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()[:5]
        )
        raise LLMError(
            f"模型输出不符合 schema：{problems}",
            kind="parse",
            retryable=True,
        ) from exc
