/** 与后端 app/events/schemas.py 的 EventType 一一对应。
 *
 * SSE 的每条消息都带 `event: <type>` 字段，浏览器会按这个名字分发事件，
 * 所以前端必须有一份完整的类型清单（用来逐个 addEventListener）。
 */
export const RUN_EVENT_TYPES = [
  // 生命周期
  'task_started',
  'approval_required',
  'task_completed',
  'task_failed',
  'task_cancelled',
  // 各阶段
  'planning',
  'plan_created',
  'tool_started',
  'tool_completed',
  'retrieval_started',
  'retrieval_completed',
  'analysis_started',
  'analysis_completed',
  'verification_started',
  'verification_completed',
  'report_started',
] as const

export type RunEventType = (typeof RUN_EVENT_TYPES)[number]

/** 收到这些事件后，事件流会关闭（任务已到终态）。 */
const TERMINAL_EVENT_TYPES: readonly RunEventType[] = [
  'task_completed',
  'task_failed',
  'task_cancelled',
]

export function isTerminalEvent(type: RunEventType): boolean {
  return TERMINAL_EVENT_TYPES.includes(type)
}

export interface RunEvent {
  id: number
  thread_id: string
  type: RunEventType
  ts: string
  payload: Record<string, unknown>
}
