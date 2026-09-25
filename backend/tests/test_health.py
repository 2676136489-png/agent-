"""Phase 1 smoke tests.

跑法（在 backend/ 目录下）：
    pytest
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_unified_success_envelope():
    client = TestClient(create_app())
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["error"] is None
    assert body["data"]["status"] == "ok"
    assert body["data"]["environment"] == "development"


def test_unknown_route_returns_unified_error_envelope():
    """验证「统一错误处理」确实生效：404 也必须是统一格式。"""
    client = TestClient(create_app())
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "not_found"


def test_response_carries_request_id_header():
    client = TestClient(create_app())
    response = client.get("/api/health")

    assert response.headers.get("X-Request-ID")
