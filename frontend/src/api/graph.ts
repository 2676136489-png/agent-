import { apiGet, apiPost } from './client'
import type { ResearchRun, ResearchRunSummary } from '../types/graph'

export interface StartResearchInput {
  question: string
  maxIterations?: number
  maxVerifyAttempts?: number
  threadId?: string
}

export function startResearch(input: StartResearchInput): Promise<ResearchRun> {
  return apiPost<ResearchRun>('/api/graph/research', {
    question: input.question,
    max_iterations: input.maxIterations ?? 3,
    max_verify_attempts: input.maxVerifyAttempts ?? 2,
    thread_id: input.threadId,
  })
}

export function resumeResearch(
  threadId: string,
  approved: boolean,
  feedback?: string,
): Promise<ResearchRun> {
  return apiPost<ResearchRun>(`/api/graph/research/${threadId}/resume`, {
    approved,
    feedback: feedback || null,
  })
}

export function getResearch(threadId: string): Promise<ResearchRun> {
  return apiGet<ResearchRun>(`/api/graph/research/${threadId}`)
}

export function listRuns(
  status?: ResearchRunSummary['status'],
  limit?: number,
): Promise<ResearchRunSummary[]> {
  // [F6] 后端 limit 现在可传（默认 50）。「效果评估」页要统计全量，
  // 之前只能拿到写死的 20 条，"总运行次数"这类指标是失真的。
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (limit) params.set('limit', String(limit))
  const qs = params.toString() ? `?${params.toString()}` : ''
  return apiGet<ResearchRunSummary[]>(`/api/graph/runs${qs}`)
}

export function getSettings(): Promise<Record<string, unknown>> {
  return apiGet<Record<string, unknown>>('/api/settings')
}
