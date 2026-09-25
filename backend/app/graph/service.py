"""Research graph service: 启动 / 中断 / 恢复 / 查询。

[P0] 中断与恢复的真实价值：
报告是「要交给别人的东西」，发布前必须让人看一眼。
LangGraph 的 checkpointer 让这件事不需要我们自己写状态机：
图在 write 前停下，人确认后再用同一个 thread_id 继续即可。
"""

from __future__ import annotations

import uuid

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.events.bus import emit
from app.events.schemas import EventType
from app.graph.graph import build_initial_state, get_research_graph
from app.graph.run_store import get_run_store
from app.schemas.graph import ResearchRunResponse
from app.search.quota import WARN_LEVEL_LABELS, get_search_quota_or_none

_RECURSION_LIMIT = 50  # LangGraph 层面的最后一道保险

# `warn_level >= 2`（75% / 90%）才值得拿一条 SSE 之外的提示打扰用户；
# level 1（已过半）只在日志和 /settings/usage 里出现。
_USER_FACING_WARN_LEVEL = 2


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": _RECURSION_LIMIT}


def _quota_view(thread_id: str) -> dict:
    """本次 run 的搜索配额消耗。配额不可用时返回全是零值的同一份结构。

    这里是**只读**的：不参与图的执行，也不回填 state。
    run 账本里的 credits/degraded 由 provider 在预扣时写入（app/tools/search_provider.py）。
    """
    quota = get_search_quota_or_none()
    if quota is None:
        # 配额关闭 / DB 不可用：契约要求「字段在、值为零」
        return {
            "credits_used": 0,
            "search_calls": 0,
            "degraded": False,
            "degraded_reason": None,
            "warnings": [],
        }
    run = quota.run_usage(thread_id)
    warnings: list[str] = []
    for event in quota.warn_events():
        level = int(event["level"])
        if level >= _USER_FACING_WARN_LEVEL:
            warnings.append(
                f"搜索额度已用 {int(event['credits_used'])}/{event['period_key']} "
                f"周期额度（{WARN_LEVEL_LABELS.get(level, '已超限')}）"
            )
    return {
        "credits_used": int(run["credits"]),
        "search_calls": int(run["calls"]),
        "degraded": bool(run["degraded"]),
        "degraded_reason": (
            "搜索额度不足，本次运行可能缺少联网证据" if run["degraded"] else None
        ),
        "warnings": warnings,
    }


def _to_response(thread_id: str, values: dict, interrupted: bool) -> ResearchRunResponse:
    usage = values.get("usage") or []
    total_tokens = sum(item.get("total_tokens", 0) for item in usage)

    # [B3] 优先信任 state 里已经落库的派生状态。
    # 进程重启后 checkpointer 是空的，`interrupted` 无从判断，
    # 只有 state["status"] 还记得这次运行当时处在什么阶段（例如 awaiting_approval）。
    persisted = values.get("status")
    if persisted in TERMINAL_STATUSES or persisted == "awaiting_approval":
        status = persisted
    elif interrupted:
        status = "awaiting_approval"
    elif values.get("error"):
        status = "failed"
    else:
        status = "running"

    return ResearchRunResponse(
        thread_id=thread_id,
        status=status,
        question=values.get("question", ""),
        understanding=values.get("understanding"),
        plan=values.get("plan"),
        analysis=values.get("analysis"),
        verification=values.get("verification"),
        report=values.get("report"),
        steps=values.get("steps") or [],
        tool_calls=values.get("tool_calls") or [],
        citations=values.get("citations") or [],
        evidence_count=len(values.get("evidence") or []),
        iteration=values.get("iteration", 0),
        verify_attempts=values.get("verify_attempts", 0),
        usage_total_tokens=total_tokens,
        error=values.get("error"),
        finished_reason=values.get("finished_reason") or "",
        **_quota_view(thread_id),
    )


def _announce(thread_id: str, response: ResearchRunResponse) -> None:
    """广播生命周期事件。终态事件会让 SSE 连接关闭。"""
    if response.status == "awaiting_approval":
        emit(
            thread_id,
            EventType.APPROVAL_REQUIRED,
            {"node": "write", "summary": "报告生成前需要人工确认"},
        )
    elif response.status == "completed":
        emit(
            thread_id,
            EventType.TASK_COMPLETED,
            {"title": (response.report or {}).get("title"), "node": "write"},
        )
    elif response.status == "cancelled":
        emit(thread_id, EventType.TASK_CANCELLED, {"reason": "rejected_by_human"})
    elif response.status == "failed":
        emit(thread_id, EventType.TASK_FAILED, {"error": response.error})


# 终态：进入这些状态后不允许再 resume（人工拒绝必须是终态）
TERMINAL_STATUSES = frozenset({"completed", "cancelled", "failed"})


async def _snapshot(thread_id: str, announce: bool = False) -> ResearchRunResponse:
    graph = get_research_graph()
    snapshot = await graph.aget_state(_config(thread_id))
    values = dict(snapshot.values or {})

    if not values:
        # checkpointer 里没有这次运行（InMemorySaver 在进程重启后就是空的）。
        # 这里必须抛错让上层回落到数据库，否则会用空状态把历史记录覆盖掉。
        raise LookupError(f"thread {thread_id} 不在内存 checkpointer 中")

    response = _to_response(thread_id, values, interrupted=bool(snapshot.next))
    if announce:
        _announce(thread_id, response)

    # 落库：产品视角的运行记录（与 checkpointer 互补）
    #
    # [B3] 把**派生状态**（awaiting_approval 等）一并写进 state["status"]。
    # 之前只写图内部的 status 字段（中断时还是 "running"），
    # 导致进程重启后从数据库回落时，一个"等待人工确认"的运行被显示成"运行中"，
    # 用户会一直等下去。
    persisted = dict(values)
    persisted["status"] = response.status
    get_run_store().upsert(
        thread_id=thread_id,
        question=response.question,
        status=response.status,
        state=persisted,
    )
    return response


async def start_research(
    *,
    question: str,
    max_iterations: int | None = None,
    max_verify_attempts: int | None = None,
    thread_id: str | None = None,
) -> ResearchRunResponse:
    settings = get_settings()
    tid = thread_id or f"thread_{uuid.uuid4().hex[:12]}"
    initial = build_initial_state(
        question=question,
        max_iterations=max_iterations or settings.graph_max_iterations,
        max_verify_attempts=max_verify_attempts or settings.graph_max_verify_attempts,
    )
    emit(
        tid,
        EventType.TASK_STARTED,
        {"question": question, "max_iterations": initial["max_iterations"]},
    )
    # 先落一条 running 记录，这样 SSE 端点能立刻校验 thread_id 是否合法
    get_run_store().upsert(thread_id=tid, question=question, status="running", state=initial)
    await get_research_graph().ainvoke(initial, _config(tid))
    return await _snapshot(tid, announce=True)


async def resume_research(
    *,
    thread_id: str,
    approved: bool = True,
    feedback: str | None = None,
) -> ResearchRunResponse:
    graph = get_research_graph()
    config = _config(thread_id)

    # [B3] 先确认这次运行在内存 checkpointer 里还活着。
    # 进程重启后 InMemorySaver 是空的，此时直接 ainvoke(None, ...) 会抛
    # EmptyInputError，被全局兜底 handler 吞成一句毫无信息量的 500。
    # 这里提前给出可操作的错误。
    checkpoint = await graph.aget_state(config)
    if not checkpoint.values:
        raise AppError(
            code=ErrorCode.VALIDATION_ERROR,
            message="这次运行已不可恢复：进程重启后内存中的中断点已丢失，请重新发起一次研究",
            status_code=409,
        )

    # [B4] 终态不可复活。人工拒绝（cancelled）必须是终态：
    # 否则一次 POST /resume {approved:true} 就能把被拒绝的任务重新跑完并出报告。
    # 拦截放在 service 层而不是只放在路由层 —— 状态机正确性不该依赖调用方。
    current_status = (checkpoint.values or {}).get("status")
    if current_status in TERMINAL_STATUSES:
        raise AppError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"这次运行已结束（{current_status}），无需恢复",
            status_code=409,
        )

    if not approved:
        # 人工拒绝：不继续写报告，把状态标记为 cancelled 并保存
        await graph.aupdate_state(
            config,
            {"status": "cancelled", "finished_reason": "rejected_by_human"},
        )
        return await _snapshot(thread_id, announce=True)

    if feedback:
        # 人工意见注入 State，write 节点的 prompt 会带上它
        await graph.aupdate_state(config, {"feedback": feedback, "status": "running"})

    # 输入为 None = 从 checkpoint 断点处继续
    await graph.ainvoke(None, config)
    return await _snapshot(thread_id, announce=True)


async def get_research(thread_id: str) -> ResearchRunResponse | None:
    """优先读图的状态；读不到（例如进程重启后内存 checkpoint 丢失）就用落库记录。"""
    try:
        return await _snapshot(thread_id)
    except Exception:  # noqa: BLE001 - checkpointer 里没有这个 thread
        record = get_run_store().get(thread_id)
        if record is None:
            return None
        return _to_response(thread_id, record["state"] or {}, interrupted=False)


def list_runs(limit: int = 20, status: str | None = None) -> list[dict]:
    return get_run_store().list_runs(limit, status=status)
