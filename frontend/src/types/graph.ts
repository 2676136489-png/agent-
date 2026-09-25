/** 与后端 app/schemas/graph.py + app/graph/schemas.py 对应。 */
import type { Citation } from './knowledge'
import type { ResearchPlan } from './research'

export type RunStatus = 'running' | 'awaiting_approval' | 'completed' | 'cancelled' | 'failed'

export interface TaskUnderstanding {
  goal: string
  key_questions: string[]
  scope: string
}

export interface AnalysisResult {
  findings: string[]
  gaps: string[]
}

export interface VerificationResult {
  verdict: string
  reasons: string[]
  missing: string[]
}

export interface ReportSection {
  heading: string
  content: string
}

export interface ResearchReport {
  title: string
  summary: string
  sections: ReportSection[]
  limitations: string[]
}

export interface RunStep {
  node: string
  summary: string
}

export interface ResearchRun {
  thread_id: string
  status: RunStatus
  question: string
  understanding: TaskUnderstanding | null
  plan: ResearchPlan | null
  analysis: AnalysisResult | null
  verification: VerificationResult | null
  report: ResearchReport | null
  steps: RunStep[]
  tool_calls: {
    tool: string
    args: Record<string, unknown>
    ok: boolean
    error: string | null
    error_kind: string | null
    duration_ms: number
  }[]
  citations: Citation[]
  evidence_count: number
  iteration: number
  verify_attempts: number
  usage_total_tokens: number
  error: string | null
  finished_reason: string
}

/** GET /api/graph/runs 返回的轻量摘要（不含完整 state） */
export interface ResearchRunSummary {
  id: string
  thread_id: string
  question: string
  status: RunStatus
  updated_at: string
}
