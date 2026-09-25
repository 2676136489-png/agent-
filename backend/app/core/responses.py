"""Unified API response model.

[P0] 前端只需要认识这一种响应形状，就能处理所有接口。

为什么不让路由直接返回裸数据（比如只返回 {"status": "ok"}）？
因为一旦接口变多，前端就必须为每个接口写不同的成功/失败判断。
统一信封（envelope）后，前端只需要写一次判断逻辑：

    if (!body.success) { 处理 body.error } else { 用 body.data }
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """错误信息。code 给程序判断用，message 给人看。"""

    code: str = Field(description="Machine readable error code, e.g. 'not_found'")
    message: str = Field(description="Human readable message")
    details: dict | list | None = Field(default=None, description="Optional structured detail")


class ApiResponse(BaseModel, Generic[T]):
    """所有接口的统一响应结构。

    Generic[T] 让 `ApiResponse[HealthData]` 成为一个具体的类型，
    FastAPI 会据此生成 OpenAPI 文档，前端也能据此生成 TS 类型。
    """

    success: bool
    data: T | None = None
    error: ErrorDetail | None = None


def success_response(data: T) -> ApiResponse[T]:
    """构造成功响应。让路由不必重复写 success=True。"""
    return ApiResponse(success=True, data=data, error=None)
