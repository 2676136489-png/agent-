"""Research plan endpoint tests.

这些测试在没有 API Key 的机器上也能跑：
LLM_PROVIDER=auto + 空 Key → 自动使用 MockLLMClient。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

QUESTION = "研究 2026 年 AI Agent 开发岗位的主要技术要求，并分析不同公司的岗位要求有什么共同点。"


def test_plan_endpoint_returns_structured_plan():
    client = TestClient(create_app())
    response = client.post("/api/research/plan", json={"question": QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    data = body["data"]
    plan = data["plan"]
    # 契约：这四个字段一个都不能少
    assert {"goal", "questions", "steps", "expected_sources"} <= plan.keys()
    assert len(plan["steps"]) >= 1
    assert plan["steps"][0]["index"] == 1
    # 可观测性：模型名、token、耗时都要有
    assert data["model"]
    assert "total_tokens" in data["usage"]
    assert data["latency_ms"] >= 0


def test_plan_endpoint_rejects_too_short_question():
    client = TestClient(create_app())
    response = client.post("/api/research/plan", json={"question": "hi"})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"
    # 必须能看出是哪个字段错了
    assert body["error"]["details"][0]["field"]


def test_plan_endpoint_rejects_too_many_steps():
    client = TestClient(create_app())
    response = client.post("/api/research/plan", json={"question": QUESTION, "max_steps": 99})

    assert response.status_code == 422
