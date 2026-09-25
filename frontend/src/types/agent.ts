/** 与后端 app/agent/schemas.py 对应的前端类型。 */
import type { Citation } from './knowledge'

export interface ToolCallRecord {
  index: number
  tool: string
  args: Record<string, unknown>
  ok: boolean
  error: string | null
  error_kind: string | null
  output_preview: string
  duration_ms: number
}

export interface AgentStepRecord {
  index: number
  reason: string | null
  tool_call: ToolCallRecord | null
  final_answer: string | null
}

export interface AgentRunResult {
  question: string
  answer: string
  steps: AgentStepRecord[]
  tool_calls: ToolCallRecord[]
  finished_reason: string
  citations: Citation[]
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
  latency_ms: number
  mock: boolean
}
