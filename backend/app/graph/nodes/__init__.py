"""Graph nodes: 每个节点只做一件事。

[P0] Node 是什么：
一个节点就是一个函数，签名为 (state, config) -> 局部更新。
它不调用下一个节点，也不知道自己后面是谁 —— 流程由 Edge 决定。
这是「图」和「一串 if/else」的本质区别：节点可复用、可重排、可被条件边跳过或重复执行。

本阶段刻意**不拆成多个 Agent**：所有节点共享同一份 State 和同一个 LLM client，
它们是「一个 Agent 的多个阶段」，而不是多个互相通信的 Agent。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from app.agent.schemas import AgentDecision
from app.core.config import get_settings
from app.core.security import wrap_untrusted_block
from app.events.bus import emit
from app.events.schemas import EventType
from app.graph import prompts
from app.graph.nodes.common import NodeDeps, resolve_deps
from app.graph.schemas import (
    AnalysisResult,
    ResearchReport,
    TaskUnderstanding,
    VerificationResult,
)
from app.graph.state import ResearchState
from app.llm.client import LLMClient, get_llm_client
from app.llm.errors import LLMError
from app.llm.schemas import LLMRequest
from app.schemas.research import ResearchPlan
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry, build_default_registry

logger = logging.getLogger(__name__)

_EVIDENCE_PREVIEW = 600
_ARGS_SNAPSHOT_CHARS = 500

# [A8] 只有完全由我们本地生成、不含任何外部内容的工具可以免标记。
# 其余（联网搜索 / 网页抓取 / 知识库文档）一律当作不可信数据包裹后再进上下文：
# 知识库文档虽然由用户上传，但仍可能来自第三方，不能默认可信。
_TRUSTED_TOOLS = frozenset({"calculate"})


def _safe_args(args: object) -> dict:
    """落库前把模型给出的 args 规范化：只保留 JSON 基本类型，并限制体积。

    [A8] args 完全由模型生成，直接落库再回显给前端有两条风险：
    一是嵌套过深/超大对象的存储膨胀，二是非 JSON 类型导致序列化后失真。
    """
    if not isinstance(args, dict):
        return {}
    cleaned: dict = {}
    for key, value in list(args.items())[:20]:
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[str(key)[:50]] = (
                value[:_ARGS_SNAPSHOT_CHARS] if isinstance(value, str) else value
            )
        else:
            cleaned[str(key)[:50]] = json.dumps(value, ensure_ascii=False, default=str)[
                :_ARGS_SNAPSHOT_CHARS
            ]
    return cleaned


def _thread_id(config: RunnableConfig) -> str:
    """节点发事件需要知道自己在哪一次运行里 —— 从 LangGraph 的 config 里取。"""
    return str((config or {}).get("configurable", {}).get("thread_id", "unknown"))


def _deps(config: RunnableConfig | None) -> tuple[LLMClient, ToolRegistry]:
    """从 config 里取依赖，取不到就用默认实现。

    这样做的好处：测试可以注入假 client / 假 registry，节点代码零改动。

    [T03] 具体实现已经搬到 `nodes.common.resolve_deps()` —— 那里是依赖清单的
    唯一出处。本函数只保留「拆成 (client, registry) 二元组」这个老口径，
    等 T04 把 8 个节点拆成 `_xxx_logic(state, deps)` 后连同本函数一起消失。
    """
    deps = resolve_deps(config)
    return deps.llm, deps.registry


async def _ask(
    client: LLMClient,
    messages: list[Any],
    schema: type[BaseModel],
    purpose: str,
    metadata: dict | None = None,
) -> tuple[BaseModel, dict]:
    """统一的结构化 LLM 调用。

    [A7] metadata 用来携带「结构化上下文」（例如当前证据条数），
    Mock client 优先读它而不是去正则匹配 prompt 文案 —— 后者会随着
    prompt 调整悄悄失效，而测试却依然全绿。
    """
    request = LLMRequest(
        messages=messages,
        response_format={"type": "json_object"},
        purpose=purpose,
        metadata=metadata or {},
    )
    result = await client.complete_structured(request, schema)
    return result.data, result.response.usage.model_dump()


def _step(node: str, summary: str) -> dict:
    return {"node": node, "summary": summary}


def _failed(message: str) -> dict:
    """出错时统一收敛：不让异常打断图，而是记录错误并进入收尾。"""
    return {"error": message}


# ------------------------------ nodes ------------------------------


async def understand_task(state: ResearchState, config: RunnableConfig) -> dict:
    thread_id = _thread_id(config)
    client, _ = _deps(config)
    emit(thread_id, EventType.PLANNING, {"node": "understand_task", "summary": "解析研究目标"})
    try:
        data, usage = await _ask(
            client,
            prompts.understanding_messages(state["question"]),
            TaskUnderstanding,
            "understand_task",
        )
    except LLMError as exc:
        return _failed(f"理解任务失败：{exc.message}")

    emit(
        thread_id,
        EventType.PLANNING,
        {"node": "understand_task", "summary": f"{len(data.key_questions)} 个关键问题"},
    )
    return {
        "understanding": data.model_dump(),
        "steps": [_step("understand_task", data.goal)],
        "usage": [{"purpose": "understand_task", **usage}],
    }


async def plan_node(state: ResearchState, config: RunnableConfig) -> dict:
    thread_id = _thread_id(config)
    client, _ = _deps(config)
    understanding = state.get("understanding") or {"goal": state["question"]}
    emit(thread_id, EventType.PLANNING, {"node": "plan", "summary": "生成研究计划"})

    data = None
    usage: dict = {}
    last_err = ""
    # [P0] 计划生成容错：模型偶尔会漏字段。先正常生成，失败再用 repair 提示重试一次；
    # 仍失败则退化为「从理解结果合成的最小可用计划」，保证后续检索/研究流程不中断。
    #
    # [A4] 第二次尝试会把上一次的具体失败原因（哪个字段不合规）回灌给模型，
    # 否则 repair 提示只知道"你错了"，模型大概率原样再错一次。
    for attempt in range(2):
        try:
            data, usage = await _ask(
                client,
                prompts.plan_messages(
                    understanding,
                    repair=attempt > 0,
                    repair_hint=last_err if attempt > 0 else None,
                ),
                ResearchPlan,
                "plan",
            )
            break
        except LLMError as exc:
            last_err = exc.message
            logger.warning("plan 生成失败（第 %s 次）：%s", attempt + 1, exc.message)

    if data is None:
        data = _fallback_plan(understanding)
        emit(
            thread_id,
            EventType.PLAN_CREATED,
            {"steps": len(data.steps), "goal": data.goal, "fallback": True},
        )
        return {
            "plan": data.model_dump(),
            "steps": [_step("plan", f"{len(data.steps)} 步计划（兜底）")],
            "usage": [],
        }

    emit(thread_id, EventType.PLAN_CREATED, {"steps": len(data.steps), "goal": data.goal})
    return {
        "plan": data.model_dump(),
        "steps": [_step("plan", f"{len(data.steps)} 步计划")],
        "usage": [{"purpose": "plan", **usage}],
    }


def _fallback_plan(understanding: dict) -> ResearchPlan:
    """计划生成彻底失败时的兜底：从任务理解里抽出目标/子问题，拼一个最小可运行计划。

    [A3] 这里必须用 **dict** 而不是 PlanStep 对象来构造 steps：
    ResearchPlan 的 steps 校验器只接受 dict，传对象会被静默过滤成空列表，
    导致「兜底计划」反而一份 0 步的计划（曾经的线上问题）。
    """
    goal = understanding.get("goal") or "完成本次研究"
    questions = [str(q) for q in (understanding.get("key_questions") or []) if q] or [goal]
    steps = [
        {
            "index": index,
            "title": f"回答子问题：{question}"[:100],
            "instruction": f"检索并整理关于「{question}」的证据"[:500],
        }
        for index, question in enumerate(questions[:6], start=1)
    ]
    return ResearchPlan(
        goal=goal,
        questions=questions[:7],
        steps=steps,  # type: ignore[arg-type]  # 交给 ResearchPlan 的 validator 规范化
        expected_sources=["招聘网站", "技术博客", "官方文档", "行业报告"],
    )


async def research_node(state: ResearchState, config: RunnableConfig) -> dict:
    """[P0] Tool Calling 与 Graph 的集成点。

    这个节点每执行一次 = 一轮「LLM 决策 → 执行一个工具」。
    是否再来一轮由**条件边**决定（而不是节点内的 for 循环），
    这样每一轮都会被 checkpoint 记录下来，中断后可以从断点继续。
    """
    thread_id = _thread_id(config)
    client, registry = _deps(config)
    settings = get_settings()

    try:
        decision, usage = await _ask(
            client,
            prompts.research_messages(
                tool_schemas=registry.function_schemas(),
                evidence=state.get("evidence", []),
                plan=state.get("plan"),
            ),
            AgentDecision,
            "research_decision",
            metadata={"evidence_count": len(state.get("evidence", []))},
        )
    except LLMError as exc:
        # [P0] 决策失败不要直接致命：累加失败计数，交给条件边决定是再来一轮还是进入检索。
        # 这样即使模型连续决策失败，也一定会走到 retrieve 节点做联网搜索，不会整图空转。
        return {
            "failure_streak": state.get("failure_streak", 0) + 1,
            "iteration": state.get("iteration", 0) + 1,
            "research_done": False,
            "steps": [_step("research", f"研究决策失败（重试）：{exc.message[:60]}")],
        }

    usage_record = {"purpose": "research_decision", **usage}

    # 模型认为信息够了 → 结束 research 阶段
    if decision.final_answer:
        return {
            "research_done": True,
            "failure_streak": 0,
            "iteration": state.get("iteration", 0) + 1,
            "evidence": [f"初步结论：{decision.final_answer[:_EVIDENCE_PREVIEW]}"],
            "steps": [_step("research", "模型判定信息已充分")],
            "usage": [usage_record],
        }

    action = decision.action
    if action is None:
        return _failed("模型既没有选择工具也没有给出结论")

    ctx = ToolContext(
        run_id=str((config or {}).get("configurable", {}).get("thread_id", "graph")),
        max_output_chars=settings.tool_output_max_chars,
        allowed_domains=settings.fetch_allowed_domains_list,
        step_index=state.get("iteration", 0) + 1,
    )

    args_summary = json.dumps(action.args, ensure_ascii=False)[:200]
    emit(
        thread_id,
        EventType.TOOL_STARTED,
        {"tool": action.tool, "input_summary": args_summary, "reason": action.reason},
    )

    try:
        tool = registry.get(action.tool)
    except Exception as exc:  # 未知工具：记录为一次被拒绝的调用，不崩溃
        emit(
            thread_id,
            EventType.TOOL_COMPLETED,
            {"tool": action.tool, "ok": False, "error_kind": "blocked", "error": str(exc)},
        )
        return {
            "failure_streak": state.get("failure_streak", 0) + 1,
            "iteration": state.get("iteration", 0) + 1,
            # 重置「已完成」标记：若本轮是被 verify 打回的补充研究，要重新积累
            "research_done": False,
            "tool_calls": [
                {
                    "tool": action.tool,
                    "args": _safe_args(action.args),
                    "ok": False,
                    "error": str(exc),
                    "error_kind": "blocked",
                    "duration_ms": 0,
                }
            ],
            "steps": [_step("research", f"工具被拒绝：{action.tool}")],
            "usage": [usage_record],
        }

    result = await tool.execute(action.args, ctx)

    emit(
        thread_id,
        EventType.TOOL_COMPLETED,
        {
            "tool": result.tool,
            "ok": result.ok,
            "duration_ms": result.duration_ms,
            "output_summary": result.summary,
            "error": result.error,
            "error_kind": result.error_kind,
        },
    )

    observation = result.to_observation()
    if result.ok:
        # [A8] 除纯本地计算外，所有工具输出都标记为不可信数据后再进上下文
        if action.tool in _TRUSTED_TOOLS:
            evidence_text = f"[内部工具] {observation[:_EVIDENCE_PREVIEW]}"
        else:
            evidence_text = (
                f"[{action.tool}] "
                f"{wrap_untrusted_block(observation[:_EVIDENCE_PREVIEW])}"
            )
    else:
        evidence_text = None

    safe_args = _safe_args(action.args)
    update: dict = {
        "iteration": state.get("iteration", 0) + 1,
        "failure_streak": (state.get("failure_streak", 0) + 1) if not result.ok else 0,
        "research_done": False,
        "tool_calls": [
            {
                "tool": result.tool,
                "args": safe_args,
                "ok": result.ok,
                "error": result.error,
                "error_kind": result.error_kind,
                "duration_ms": result.duration_ms,
            }
        ],
        "steps": [_step("research", f"{result.tool}：{result.summary}")],
        "usage": [usage_record],
    }
    if result.citations:
        update["citations"] = result.citations
    if evidence_text:
        update["evidence"] = [evidence_text]
    return update


async def retrieve_node(state: ResearchState, config: RunnableConfig) -> dict:
    """固定动作：先查自己的知识库，知识库没命中时回退到真实联网搜索。

    这里不需要 LLM 决策（规则驱动），所以直接调用工具。
    当知识库为空或未命中时，自动调用 search_web 拿到真实网页证据，
    保证研究工作流「默认就走真实联网」，而不只是查私有资料。
    """
    thread_id = _thread_id(config)
    _, registry = _deps(config)
    settings = get_settings()

    understanding = state.get("understanding") or {}
    questions = understanding.get("key_questions") or []
    query = questions[0] if questions else state["question"]

    ctx = ToolContext(
        run_id=str((config or {}).get("configurable", {}).get("thread_id", "graph")),
        max_output_chars=settings.tool_output_max_chars,
        # [B15] 之前这里漏了 allowed_domains，导致域名白名单在 retrieve 节点失效
        allowed_domains=settings.fetch_allowed_domains_list,
    )
    emit(thread_id, EventType.RETRIEVAL_STARTED, {"query": query, "top_k": 3})

    evidence: list[str] = []
    tool_calls: list[dict] = []
    citations = None

    # 1) 先查知识库
    try:
        kb_tool = registry.get("search_knowledge_base")
        kb_result = await kb_tool.execute({"query": query, "top_k": 3}, ctx)
    except Exception:
        kb_result = None

    if kb_result and kb_result.ok and kb_result.citations:
        citations = kb_result.citations
        evidence.append(f"[知识库] {kb_result.output[:_EVIDENCE_PREVIEW]}")
        tool_calls.append(
            {
                "tool": kb_result.tool,
                "args": {"query": query, "top_k": 3},
                "ok": kb_result.ok,
                "error": kb_result.error,
                "error_kind": kb_result.error_kind,
                "duration_ms": kb_result.duration_ms,
            }
        )

    # 2) 知识库没命中 → 回退真实联网搜索（search_web 背后已是 Tavily）
    if not citations:
        try:
            web_tool = registry.get("search_web")
            web_result = await web_tool.execute({"query": query, "max_results": 3}, ctx)
        except Exception:
            web_result = None
        if web_result and web_result.ok:
            evidence.append(
                f"[联网搜索] {wrap_untrusted_block(web_result.output[:_EVIDENCE_PREVIEW])}"
            )
            tool_calls.append(
                {
                    "tool": web_result.tool,
                    "args": {"query": query, "max_results": 3},
                    "ok": web_result.ok,
                    "error": web_result.error,
                    "error_kind": web_result.error_kind,
                    "duration_ms": web_result.duration_ms,
                }
            )

    primary = kb_result if citations else web_result
    used_source = "知识库" if citations else ("联网搜索" if evidence else "无命中")
    emit(
        thread_id,
        EventType.RETRIEVAL_COMPLETED,
        {
            "ok": bool(citations or evidence),
            "hits": len(citations or []),
            "duration_ms": primary.duration_ms if primary else 0,
            "output_summary": primary.summary if primary else "无命中",
            "source": used_source,
        },
    )

    update: dict = {
        "tool_calls": tool_calls,
        "steps": [_step("retrieve", f"{used_source}：补充证据")],
    }
    if citations:
        update["citations"] = citations
    if evidence:
        update["evidence"] = evidence
    return update


async def analyze_node(state: ResearchState, config: RunnableConfig) -> dict:
    thread_id = _thread_id(config)
    client, _ = _deps(config)
    emit(thread_id, EventType.ANALYSIS_STARTED, {"evidence_count": len(state.get("evidence", []))})
    try:
        data, usage = await _ask(
            client,
            prompts.analyze_messages(state["question"], state.get("evidence", [])),
            AnalysisResult,
            "analyze",
        )
    except LLMError as exc:
        return _failed(f"分析失败：{exc.message}")

    emit(
        thread_id,
        EventType.ANALYSIS_COMPLETED,
        {"findings": len(data.findings), "gaps": len(data.gaps)},
    )
    return {
        "analysis": data.model_dump(),
        "steps": [_step("analyze", f"{len(data.findings)} 条结论 / {len(data.gaps)} 处缺口")],
        "usage": [{"purpose": "analyze", **usage}],
    }


async def verify_node(state: ResearchState, config: RunnableConfig) -> dict:
    thread_id = _thread_id(config)
    client, _ = _deps(config)
    analysis = state.get("analysis") or {}
    emit(
        thread_id,
        EventType.VERIFICATION_STARTED,
        {"attempt": state.get("verify_attempts", 0) + 1},
    )
    try:
        data, usage = await _ask(
            client,
            prompts.verify_messages(
                state["question"],
                analysis,
                len(state.get("evidence", [])),
            ),
            VerificationResult,
            "verify",
            metadata={"evidence_count": len(state.get("evidence", []))},
        )
    except LLMError as exc:
        return _failed(f"验证失败：{exc.message}")

    emit(
        thread_id,
        EventType.VERIFICATION_COMPLETED,
        {"verdict": data.verdict, "reasons": data.reasons},
    )
    return {
        "verification": data.model_dump(),
        "verify_attempts": state.get("verify_attempts", 0) + 1,
        "steps": [_step("verify", f"判定：{data.verdict}")],
        "usage": [{"purpose": "verify", **usage}],
    }


async def write_node(state: ResearchState, config: RunnableConfig) -> dict:
    """生成最终报告。这是图的中断点（interrupt_before=["write"]）。"""
    thread_id = _thread_id(config)
    client, _ = _deps(config)
    emit(thread_id, EventType.REPORT_STARTED, {"has_feedback": bool(state.get("feedback"))})
    try:
        data, usage = await _ask(
            client,
            prompts.write_messages(
                state["question"],
                state.get("analysis") or {},
                state.get("evidence", []),
                state.get("feedback"),
            ),
            ResearchReport,
            "write",
        )
    except LLMError as exc:
        return _failed(f"撰写报告失败：{exc.message}")

    return {
        "report": data.model_dump(),
        "status": "completed",
        "finished_reason": "completed",
        "steps": [_step("write", data.title)],
        "usage": [{"purpose": "write", **usage}],
    }


async def fail_node(state: ResearchState, config: RunnableConfig) -> dict:
    """[A5] 失败终态节点。

    之前 `route_after_analyze` / `route_after_verify` 在 error 时直接跳 write，
    结果是在 analysis 为空、evidence 可能也不足的情况下硬写一份空壳报告，
    用户看到的却是 `completed`。这里改成显式走失败终态：
    终态事件由 service._announce 统一广播（避免与这里重复发一条）。
    """
    error = state.get("error") or "未知错误"
    logger.warning("research graph failed: thread=%s error=%s", _thread_id(config), error)
    return {
        "status": "failed",
        "finished_reason": state.get("finished_reason") or "node_error",
        "steps": [_step("fail", f"流程失败：{error[:80]}")],
    }
