import { apiPost } from './client'
import type { PlanResponse } from '../types/research'

export interface CreatePlanInput {
  question: string
  maxSteps?: number
}

/** 提交研究问题，后端调用 LLM 返回结构化研究计划 */
export function createResearchPlan(input: CreatePlanInput): Promise<PlanResponse> {
  return apiPost<PlanResponse>('/api/research/plan', {
    question: input.question,
    max_steps: input.maxSteps ?? 6,
  })
}
