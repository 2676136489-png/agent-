import { useCallback, useRef, useState } from 'react'
import { subscribeRunEvents } from '../../api/events'
import { isTerminalEvent, type RunEvent } from '../../types/events'

export type StreamStatus = 'idle' | 'connecting' | 'open' | 'error' | 'closed'

type Listener = {
  onEvent: (event: RunEvent) => void
  onOpen?: () => void
  onError?: () => void
}

/**
 * [F5] 模块级连接管理器：一次运行对应**一条** SSE 连接，连接生命周期与组件
 * 挂载周期解耦。
 *
 * 之前连接由 useRunEvents 独占持有，组件卸载（切换导航）就 close()，
 * 于是页面文案写的「你可切到其他模块同步查看，进度不会中断」根本不成立 ——
 * 一切走就断流，回来只剩手动刷新。
 *
 * 现在：
 * - 组件只注册/注销「监听器」，不拥有连接
 * - 连接只在终态事件、显式 closeStream() 或切换到新 thread 时关闭
 * - 新加入的监听器会先拿到已缓存的事件，所以切回来时进度是完整的
 */
const listeners = new Map<string, Set<Listener>>()
const sources = new Map<string, EventSource>()
const eventCache = new Map<string, RunEvent[]>()

function broadcast(threadId: string, fn: (listener: Listener) => void): void {
  const snapshot = [...(listeners.get(threadId) ?? [])]
  for (const listener of snapshot) fn(listener)
}

function attach(threadId: string): void {
  if (sources.has(threadId)) return

  const source = subscribeRunEvents(threadId, {
    onOpen: () => broadcast(threadId, (l) => l.onOpen?.()),
    onEvent: (event) => {
      const cache = eventCache.get(threadId) ?? []
      if (!cache.some((e) => e.id === event.id)) {
        cache.push(event)
        eventCache.set(threadId, cache)
      }
      broadcast(threadId, (l) => l.onEvent(event))
      if (isTerminalEvent(event.type)) {
        closeStream(threadId)
      }
    },
    onError: () => broadcast(threadId, (l) => l.onError?.()),
  })
  sources.set(threadId, source)
}

/** 关闭某个 thread 的连接并清空其监听器 */
export function closeStream(threadId: string): void {
  sources.get(threadId)?.close()
  sources.delete(threadId)
  listeners.delete(threadId)
  eventCache.delete(threadId)
}

/** 切换到新的 thread：关掉其它连接，避免连接数无限增长 */
export function switchStream(threadId: string): void {
  for (const id of [...sources.keys()]) {
    if (id !== threadId) closeStream(id)
  }
}

function addListener(threadId: string, listener: Listener): () => void {
  const set = listeners.get(threadId) ?? new Set<Listener>()
  set.add(listener)
  listeners.set(threadId, set)

  // 补发已经收到的事件（刷新页面 / 切回本页时进度不丢）
  for (const event of eventCache.get(threadId) ?? []) listener.onEvent(event)

  // 连接可能早已处于 OPEN（模块级连接，切页重挂载时复用同一条），
  // 此时 onOpen 不会再触发，需要给新监听器补发一次，否则状态会停在"连接中…"
  if (sources.get(threadId)?.readyState === EventSource.OPEN) {
    listener.onOpen?.()
  }

  // 注意：取消订阅时刻意**不**关闭连接 —— 组件卸载不应中断后台运行
  return () => {
    listeners.get(threadId)?.delete(listener)
  }
}

/**
 * 订阅一次运行的事件流。
 *
 * 组件只负责渲染；连接由上面的模块级管理器持有，
 * 因此切换到其他页面再回来，进度是连续的。
 */
export function useRunEvents() {
  const [events, setEvents] = useState<RunEvent[]>([])
  const [status, setStatus] = useState<StreamStatus>('idle')
  const unsubscribeRef = useRef<(() => void) | null>(null)

  const close = useCallback(() => {
    unsubscribeRef.current?.()
    unsubscribeRef.current = null
  }, [])

  const subscribe = useCallback((threadId: string) => {
    unsubscribeRef.current?.()
    setEvents([])
    setStatus('connecting')
    switchStream(threadId)

    unsubscribeRef.current = addListener(threadId, {
      onOpen: () => setStatus('open'),
      onEvent: (event) => {
        // 事件可能因重连/补发而重复，按 id 去重
        setEvents((prev) => (prev.some((e) => e.id === event.id) ? prev : [...prev, event]))
        if (isTerminalEvent(event.type)) {
          setStatus('closed')
        }
      },
      onError: () => setStatus((prev) => (prev === 'closed' ? prev : 'error')),
    })

    attach(threadId)
  }, [])

  return { events, status, subscribe, close }
}
