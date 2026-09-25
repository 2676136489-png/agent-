/** 与后端 app/schemas/research.py 一一对应的前端类型。 */

export interface PlanStep {
  index: number
  title: string
  instruction: string
}

export interface ResearchPlan {
  goal: string
  questions: string[]
  steps: PlanStep[]
  expected_sources: string[]
}

export interface TokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface PlanResponse {
  plan: ResearchPlan
  model: string
  provider: string
  /** true 表示这是离线假数据，不是真实模型输出 */
  mock: boolean
  usage: TokenUsage
  latency_ms: number
}
