"""SSE 流构造。

[P0] SSE 的报文格式极简，每一行都是 `key: value`，两个换行结束一条消息：

    id: 42
    event: tool_completed
    data: {"id":42,"type":"tool_completed","ts":"...","payload":{...}}

- `id`：浏览器断线重连时会自动带上 `Last-Event-ID`，服务端据此补发缺失的事件
- `event`：事件名，前端用 addEventListener 监听
- 以 `:` 开头的行是注释，用作心跳（不会触发前端事件）

为什么选 SSE 而不是 WebSocket：见 README §7。一句话版本：
Agent 执行是「服务端单向推送 + 客户端用普通 HTTP 发指令」，
SSE 正好匹配这个形状，而 WebSocket 的双向能力我们用不上，却要多付出连接管理与代理兼容的成本。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from app.core.config import get_settings
from app.events.bus import get_event_bus
from app.events.schemas import TERMINAL_EVENTS

logger = logging.getLogger(__name__)


def format_event(event: dict) -> str:
    payload = json.dumps(event, ensure_ascii=False)
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {payload}\n\n"


async def event_stream(thread_id: str, last_event_id: int = 0) -> AsyncIterator[str]:
    """生成 SSE 报文：先补发历史，再实时推送，任务结束则关闭。"""
    settings = get_settings()
    heartbeat = settings.sse_heartbeat_seconds
    bus = get_event_bus()

    queue, history = bus.subscribe(thread_id, last_event_id)
    sent_ids: set[int] = set()

    try:
        # 1) 补发历史：刷新页面 / 断线重连后能看到完整过程
        for event in history:
            sent_ids.add(event["id"])
            yield format_event(event)
            if event["type"] in TERMINAL_EVENTS:
                return

        # 2) 实时推送
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=heartbeat)
            except TimeoutError:
                # 心跳：保持连接不被代理/浏览器判为超时
                yield ": heartbeat\n\n"
                continue

            if item["id"] in sent_ids:
                continue  # 历史事件已发过，避免重复

            sent_ids.add(item["id"])
            yield format_event(item)
            if item["type"] in TERMINAL_EVENTS:
                return
    finally:
        # 客户端断开或任务结束，都要取消订阅，否则队列会越积越多
        bus.unsubscribe(thread_id, queue)
