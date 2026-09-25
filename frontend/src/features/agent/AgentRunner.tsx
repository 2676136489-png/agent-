import { useState } from 'react'
import { runAgent } from '../../api/agent'
import { ApiClientError } from '../../api/client'
import { ChevronRightIcon } from '../../components/icons'
import { StatusBadge } from '../../components/StatusBadge'
import { CollapsibleCard } from '../../components/CollapsibleCard'
import { ProcessTimeline, type ProcessTimelineItem } from '../../components/ProcessTimeline'
import { ToolCallCard } from '../../components/ToolCallCard'
import { EmptyState } from '../../components/EmptyState'
import { LoadingState } from '../../components/LoadingState'
import { ErrorState } from '../../components/ErrorState'
import type { AgentRunResult, AgentStepRecord, ToolCallRecord } from '../../types/agent'

const EXAMPLE_QUESTION = '向量数据库有哪些主流选择？各自适用场景是什么？'

// [F4] 键名必须与后端 app/agent/schemas.py 的 finished_reason 实际取值一致：
// final_answer | max_steps_reached | timeout | llm_error。
// 之前写的是 completed / max_steps / tool_error / cancelled —— 一个都对不上，
// 界面永远显示英文原始值 + 中性样式。
const FINISH_REASON_LABEL: Record<string, string> = {
  final_answer: '已给出结论',
  max_steps_reached: '已达最大步数',
  timeout: '已超时',
  llm_error: '模型调用失败',
}

const FINISH_VARIANT: Record<string, 'ok' | 'warn' | 'error'> = {
  final_answer: 'ok',
  max_steps_reached: 'warn',
  timeout: 'warn',
  llm_error: 'error',
}

type RunState =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'ok'; data: AgentRunResult }
  | { status: 'error'; message: string; code: string }

export function AgentRunner() {
  const [question, setQuestion] = useState('')
  const [maxSteps, setMaxSteps] = useState(6)
  const [state, setState] = useState<RunState>({ status: 'idle' })

  async function handleRun() {
    setState({ status: 'running' })
    try {
      const data = await runAgent({ question, maxSteps })
      setState({ status: 'ok', data })
    } catch (error) {
      if (error instanceof ApiClientError) {
        setState({ status: 'error', message: error.message, code: error.code })
      } else {
        setState({ status: 'error', message: '未知错误，请查看浏览器控制台', code: 'unknown' })
      }
    }
  }

  const canRun = question.trim().length >= 8 && state.status !== 'running'

  return (
    <section className="page">
      <header className="page__head panel__header">
        <div>
          <p className="eyebrow">智能体工作台</p>
          <h2 className="panel__title">让智能体自己跑研究</h2>
          <p className="panel__subtitle">
            输入一个研究任务，智能体自主决定调用哪些工具——联网搜索、抓取网页、计算，并把每一条结论都附上来源。
          </p>
        </div>
      </header>

      {/* ============ 主操作区（首屏必达） ============ */}
      <section className="page__primary">
        <div className="input-card">
          <div className="field">
            <label className="field__label" htmlFor="agent-question">
              研究任务
            </label>
            <textarea
              id="agent-question"
              className="textarea"
              rows={3}
              value={question}
              placeholder="例如：向量数据库有哪些主流选择？各自适用场景是什么？"
              onChange={(event) => setQuestion(event.target.value)}
            />
            <div className="field__footer">
              <button className="link-button" onClick={() => setQuestion(EXAMPLE_QUESTION)}>
                填入示例
              </button>
              <span className="hint">
                {question.trim().length < 8 ? '至少 8 个字' : `${question.trim().length} 字`}
              </span>
            </div>
          </div>

          <div className="field field--inline">
            <label className="field__label" htmlFor="agent-steps">
              最大步数：{maxSteps}
            </label>
            <input
              id="agent-steps"
              type="range"
              min={1}
              max={12}
              value={maxSteps}
              onChange={(event) => setMaxSteps(Number(event.target.value))}
            />
          </div>

          <button className="button button--primary" onClick={handleRun} disabled={!canRun}>
            {state.status === 'running' ? 'Agent 执行中…' : '运行 Agent'}
          </button>

          <p className="tip">
            <span className="tip__label">提示</span>
            <span>Agent 会自己决定搜索与抓取，达到足够证据后给出带引用的答案。</span>
          </p>
        </div>

        {state.status === 'error' && (
          <div className="stack-gap">
            <ErrorState code={state.code} message={state.message} onRetry={() => void handleRun()} />
          </div>
        )}
      </section>

      {/* ============ 内容区：加载 / 结果 / 空态 ============ */}
      <section className="page__content">
        {state.status === 'running' && <LoadingState variant="list" label="Agent 正在执行…" />}

        {state.status === 'ok' && <RunView data={state.data} />}

        {state.status === 'idle' && (
          <EmptyState
            title="还没有运行 Agent"
            description="在上方输入研究任务并点「运行 Agent」，这里会显示最终答案、引用来源与执行轨迹。"
            actionLabel="填入示例"
            onAction={() => setQuestion(EXAMPLE_QUESTION)}
          />
        )}
      </section>

      {/* ============ 折叠说明区（沉底，默认收起） ============ */}
      <section className="page__aside">
        <details className="fold card--fold">
          <summary className="fold__summary">
            <ChevronRightIcon size={14} />
            <span>这个模块能做什么？</span>
          </summary>
          <div className="fold__body">
            <div className="module-section__body">
              <p>
                「智能体」是一个<strong>端到端的自主研究执行器</strong>。你只需给出一个研究任务，智能体会自己决定什么时候搜索、抓取网页、调用什么工具，
                并在达到足够证据后给出带引用来源的最终答案。它适合希望一次性拿到结论、同时保留可追溯执行过程的场合。
              </p>
            </div>
            <div className="module-section__grid">
              <div className="module-card">
                <h4 className="module-card__title">自主决策</h4>
                <p className="module-card__text">模型根据当前证据决定下一步动作，不需要你手动指定每一步。</p>
              </div>
              <div className="module-card">
                <h4 className="module-card__title">工具调用</h4>
                <p className="module-card__text">内置联网搜索、网页抓取等工具，每次调用都会记录参数、结果和耗时。</p>
              </div>
              <div className="module-card">
                <h4 className="module-card__title">可溯源结论</h4>
                <p className="module-card__text">最终答案会附带引用片段，方便你核对结论是否有证据支撑。</p>
              </div>
              <div className="module-card">
                <h4 className="module-card__title">执行轨迹</h4>
                <p className="module-card__text">完整展示智能体每一步的思考、工具调用与结果，便于排查和审计。</p>
              </div>
            </div>
          </div>
        </details>

        <details className="fold card--fold">
          <summary className="fold__summary">
            <ChevronRightIcon size={14} />
            <span>使用方式</span>
          </summary>
          <div className="fold__body">
            <div className="panel__notes">
              <div>
                <b>适用场景</b>
                <span>想快速拿到一个可溯源的研究结论，或观察智能体如何自主决策与调用工具。</span>
              </div>
              <div>
                <b>操作路径</b>
                <span>输入任务 → 设定最大步数 → 运行 Agent → 查看最终答案、引用来源与执行轨迹。</span>
              </div>
            </div>
          </div>
        </details>
      </section>
    </section>
  )
}

function RunView({ data }: { data: AgentRunResult }) {
  const timelineItems: ProcessTimelineItem[] = data.steps.map((step) => buildStepItem(step))

  return (
    <div className="result-stack">
      <div className="card card--interactive">
        <div className="run-card__head">
          <h3 className="run-card__title">运行结果</h3>
          <div className="badge-row">
            <StatusBadge variant={data.mock ? 'warn' : 'ok'}>
              {data.mock ? 'Mock 数据' : '真实模型'}
            </StatusBadge>
            <StatusBadge variant={FINISH_VARIANT[data.finished_reason] ?? 'info'}>
              {FINISH_REASON_LABEL[data.finished_reason] ?? data.finished_reason}
            </StatusBadge>
          </div>
        </div>

        <div className="run-card__metrics">
          <div className="run-metric">
            <span className="run-metric__value">{data.steps.length}</span>
            <span className="run-metric__label">执行步数</span>
          </div>
          <div className="run-metric">
            <span className="run-metric__value">{data.tool_calls.length}</span>
            <span className="run-metric__label">工具调用</span>
          </div>
          <div className="run-metric">
            <span className="run-metric__value">{data.usage.total_tokens.toLocaleString()}</span>
            <span className="run-metric__label">总 Tokens</span>
          </div>
          <div className="run-metric">
            <span className="run-metric__value">{formatDuration(data.latency_ms)}</span>
            <span className="run-metric__label">耗时</span>
          </div>
        </div>
      </div>

      <CollapsibleCard title="最终答案" defaultOpen>
        <div className="answer-card">{data.answer}</div>
      </CollapsibleCard>

      {data.citations.length > 0 && (
        <CollapsibleCard title="引用来源" badge={<span className="hint">{data.citations.length} 条</span>}>
          <div className="data-list data-list--gap">
            {data.citations.map((citation) => (
              <div key={citation.chunk_id} className="citation">
                <div className="citation__head">
                  <span className="citation__file">
                    {citation.filename}
                    {citation.page ? ` · 第 ${citation.page} 页` : ''}
                  </span>
                  <span className="citation__meta">片段 {citation.chunk_id}</span>
                </div>
                <p className="citation__quote">{citation.quote}</p>
              </div>
            ))}
          </div>
        </CollapsibleCard>
      )}

      <CollapsibleCard title="执行轨迹" badge={<span className="hint">{data.steps.length} 步</span>} defaultOpen>
        <ProcessTimeline items={timelineItems} />
      </CollapsibleCard>
    </div>
  )
}

function buildStepItem(step: AgentStepRecord): ProcessTimelineItem {
  if (step.tool_call) {
    return {
      id: step.index,
      title: `调用 ${step.tool_call.tool}`,
      body: step.reason,
      detail: <ToolCallDetail call={step.tool_call} />,
      status: step.tool_call.ok ? 'done' : 'error',
    }
  }

  if (step.final_answer) {
    return {
      id: step.index,
      title: '给出最终答案',
      body: '智能体认为已有足够证据，生成最终结论。',
      status: 'done',
    }
  }

  return {
    id: step.index,
    title: `步骤 ${step.index}`,
    body: step.reason ?? '正在决策…',
    status: 'done',
  }
}

function ToolCallDetail({ call }: { call: ToolCallRecord }) {
  return (
    <div className="stack-gap-xs">
      <ToolCallCard call={call} />
    </div>
  )
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}
