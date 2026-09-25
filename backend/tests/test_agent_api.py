"""Agent run endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

QUESTION = "研究 2026 年 AI Agent 开发岗位的主要技术要求，并说明来源。"


def test_agent_run_returns_trace():
    client = TestClient(create_app())
    response = client.post("/api/agent/run", json={"question": QUESTION, "max_steps": 4})

    assert response.status_code == 200
    body = response.json()
    data = body["data"]

    assert data["answer"]
    assert data["finished_reason"] == "final_answer"
    # Trace：每一步的工具调用都必须可审计
    assert len(data["tool_calls"]) >= 1
    call = data["tool_calls"][0]
    assert {"index", "tool", "args", "ok", "duration_ms"} <= call.keys()


def test_agent_run_rejects_short_question():
    client = TestClient(create_app())
    response = client.post("/api/agent/run", json={"question": "hi"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
