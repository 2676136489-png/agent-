import { apiPost } from './client'
import type { AgentRunResult } from '../types/agent'

export interface RunAgentInput {
  question: string
  maxSteps?: number
}

/** 运行一次最小 Agent 循环，返回答案 + 完整工具调用轨迹 */
export function runAgent(input: RunAgentInput): Promise<AgentRunResult> {
  return apiPost<AgentRunResult>('/api/agent/run', {
    question: input.question,
    max_steps: input.maxSteps ?? 6,
  })
}
