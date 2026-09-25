"""Event bus: 一边落库（可回放），一边推给正在监听的连接（实时）。

[P0] 为什么不是「只推内存」或「只落库」：
- 只推内存：刷新页面就丢历史事件
- 只落库：前端要轮询，不实时

两者结合 = 连接建立时先回放历史，再实时推送新事件。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.events.schemas import EventType
from app.events.store import get_event_store

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        # thread_id -> 所有正在监听的队列
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def emit(
        self,
        thread_id: str,
        event_type: EventType | str,
        payload: dict | None = None,
    ) -> dict:
        """发一个事件：落库 + 分发给所有监听者。

        同步方法（内部无 await），节点里可以随手调用。

        [P0] 终态事件也必须投递**事件本体**（早先投的是一个「关闭哨兵」）：
        否则在线订阅者会收到关闭信号却收不到 task_completed，
        前端就会显示成「连接中断」而不是「已完成」。
        收尾由 event_stream 在发出终态事件后自行完成。
        """
        store = get_event_store()
        event = store.append(thread_id=thread_id, type=str(event_type), payload=payload or {})
        self._broadcast(thread_id, event)
        return event

    def _broadcast(self, thread_id: str, item: Any) -> None:
        for queue in self._subscribers.get(thread_id, []):
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                logger.warning("event queue full, dropping event: %s", thread_id)

    def subscribe(self, thread_id: str, last_event_id: int = 0) -> tuple[asyncio.Queue, list[dict]]:
        """订阅某个任务的事件。返回（队列, 需要补发的历史事件）。"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.setdefault(thread_id, []).append(queue)
        history = get_event_store().list_since(thread_id, after_id=last_event_id)
        return queue, history

    def unsubscribe(self, thread_id: str, queue: asyncio.Queue) -> None:
        listeners = self._subscribers.get(thread_id)
        if not listeners:
            return
        if queue in listeners:
            listeners.remove(queue)
        if not listeners:
            self._subscribers.pop(thread_id, None)


_BUS: EventBus | None = None


def get_event_bus() -> EventBus:
    global _BUS
    if _BUS is None:
        _BUS = EventBus()
    return _BUS


def emit(thread_id: str, event_type: EventType | str, payload: dict | None = None) -> dict:
    """模块级快捷方式，节点里直接 `emit(thread_id, EventType.TOOL_STARTED, {...})`。"""
    return get_event_bus().emit(thread_id, event_type, payload)
