import { useState } from 'react'
import { createResearchPlan } from '../../api/research'
import { ApiClientError } from '../../api/client'
import type { PlanResponse } from '../../types/research'
import { ChevronRightIcon } from '../../components/icons'
import { StatusBadge } from '../../components/StatusBadge'
import { CollapsibleCard } from '../../components/CollapsibleCard'
import { EmptyState } from '../../components/EmptyState'
import { LoadingState } from '../../components/LoadingState'
import { ErrorState } from '../../components/ErrorState'

const EXAMPLE_QUESTION =
  '研究 2026 年 AI Agent 开发岗位的核心技术要求，并分析不同公司的岗位要求有什么共同点。'

type PlanState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ok'; data: PlanResponse }
  | { status: 'error'; message: string; code: string }

export function ResearchPlanner() {
  const [question, setQuestion] = useState('')
  const [maxSteps, setMaxSteps] = useState(6)
  const [state, setState] = useState<PlanState>({ status: 'idle' })

  async function handleSubmit() {
    setState({ status: 'loading' })
    try {
      const data = await createResearchPlan({ question, maxSteps })
      setState({ status: 'ok', data })
    } catch (error) {
      if (error instanceof ApiClientError) {
        setState({ status: 'error', message: error.message, code: error.code })
      } else {
        setState({
          status: 'error',
          message: '未知错误，请查看浏览器控制台',
          code: 'unknown',
        })
      }
    }
  }

  const canSubmit = question.trim().length >= 8 && state.status !== 'loading'

  return (
    <section className="page">
      <header className="page__head panel__header">
        <div>
          <p className="eyebrow">研究规划</p>
          <h2 className="panel__title">先规划，再行动</h2>
          <p className="panel__subtitle">
            输入一个研究问题，智能体先产出结构化计划——研究目标、关键子问题、执行步骤与预期来源；方向确认后再跑完整研究。
          </p>
        </div>
      </header>

      {/* ============ 主操作区（首屏必达） ============ */}
      <section className="page__primary">
        <div className="input-card">
          <div className="field">
            <label className="field__label" htmlFor="question">
              研究问题
            </label>
            <textarea
              id="question"
              className="textarea"
              rows={3}
              value={question}
              placeholder="例如：研究 2026 年 AI Agent 开发岗位的主要技术要求…"
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

          <div className="field">
            <label className="field__label" htmlFor="steps">
              最多步骤数：{maxSteps}
            </label>
            <input
              id="steps"
              type="range"
              min={3}
              max={10}
              value={maxSteps}
              onChange={(event) => setMaxSteps(Number(event.target.value))}
            />
          </div>

          <button className="button button--primary" onClick={handleSubmit} disabled={!canSubmit}>
            {state.status === 'loading' ? '生成中…' : '生成研究计划'}
          </button>

          <p className="tip">
            <span className="tip__label">提示</span>
            <span>点「生成研究计划」后，会先产出研究目标与关键子问题；确认方向无误，再到「深度研究」跑完整研究。</span>
          </p>
        </div>

        {state.status === 'error' && (
          <div className="stack-gap">
            <ErrorState code={state.code} message={state.message} onRetry={() => void handleSubmit()} />
          </div>
        )}
      </section>

      {/* ============ 内容区：加载 / 结果 / 空态 ============ */}
      <section className="page__content">
        {state.status === 'loading' && <LoadingState variant="card" label="正在生成研究计划…" />}

        {state.status === 'ok' && <PlanView data={state.data} />}

        {state.status === 'idle' && (
          <EmptyState
            title="还没有研究计划"
            description="在上方输入研究问题并点「生成研究计划」，这里会显示研究目标、关键子问题与执行步骤。"
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
                「研究规划」是研究的<strong>起点和骨架</strong>。它不负责直接给出最终答案，而是先把你的研究问题拆成清晰的子问题、执行步骤和预期来源。
                这样你可以在执行前判断方向是否正确、范围是否合理，避免后续检索跑题或重复劳动。
              </p>
            </div>
            <div className="module-section__grid">
              <div className="module-card">
                <h4 className="module-card__title">研究目标</h4>
                <p className="module-card__text">一句话定义这次研究要回答的核心问题，作为后续所有步骤的北极星。</p>
              </div>
              <div className="module-card">
                <h4 className="module-card__title">关键问题</h4>
                <p className="module-card__text">把大问题拆成 3-7 个可独立回答的子问题，覆盖不同维度和潜在争议点。</p>
              </div>
              <div className="module-card">
                <h4 className="module-card__title">研究步骤</h4>
                <p className="module-card__text">按优先级排列的执行计划，每步说明要查什么、怎么查、预期得到什么证据。</p>
              </div>
              <div className="module-card">
                <h4 className="module-card__title">预期来源</h4>
                <p className="module-card__text">建议检索的信息源类型（如招聘站、论文库、行业报告），帮助后续检索少走弯路。</p>
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
                <span>动手前先把研究方向和问题想清楚，避免研究跑偏或遗漏关键子问题。</span>
              </div>
              <div>
                <b>操作路径</b>
                <span>输入研究问题 → 设定最多步骤数 → 生成计划 → 检查目标/子问题/步骤/来源。</span>
              </div>
            </div>
          </div>
        </details>
      </section>
    </section>
  )
}

function PlanView({ data }: { data: PlanResponse }) {
  const { plan } = data
  return (
    <div className="result-stack">
      <div className="card card--interactive">
        <div className="run-card__head">
          <h3 className="run-card__title">计划概览</h3>
          <div className="badge-row">
            <StatusBadge variant={data.mock ? 'warn' : 'ok'}>
              {data.mock ? 'Mock 数据' : '真实模型'}
            </StatusBadge>
          </div>
        </div>
        <div className="run-card__meta">
          <span>{data.provider}</span>
          <span>{data.model}</span>
          <span>{data.usage.total_tokens.toLocaleString()} tokens</span>
          <span>{data.latency_ms} ms</span>
        </div>
      </div>

      <CollapsibleCard title="研究目标" defaultOpen>
        <p className="plan__goal text-flush">{plan.goal}</p>
      </CollapsibleCard>

      {plan.questions.length > 0 && (
        <CollapsibleCard title="关键问题" badge={<span className="hint">{plan.questions.length} 个</span>} defaultOpen>
          <ol className="data-list text-flush">
            {plan.questions.map((item, index) => (
              <li key={index} className="data-list__item">
                <span className="data-list__bullet" />
                <span className="data-list__text">{item}</span>
              </li>
            ))}
          </ol>
        </CollapsibleCard>
      )}

      <CollapsibleCard title="研究步骤" badge={<span className="hint">{plan.steps.length} 步</span>} defaultOpen>
        <div className="data-list data-list--gap text-flush">
          {plan.steps.map((step) => (
            <div key={step.index} className="step-card">
              <span className="step-card__no">{step.index}</span>
              <div>
                <div className="step-card__title">{step.title}</div>
                <div className="step-card__desc">{step.instruction}</div>
              </div>
            </div>
          ))}
        </div>
      </CollapsibleCard>

      {plan.expected_sources.length > 0 && (
        <CollapsibleCard title="预期来源" badge={<span className="hint">{plan.expected_sources.length} 个</span>}>
          <ol className="data-list text-flush">
            {plan.expected_sources.map((source, index) => (
              <li key={index} className="data-list__item">
                <span className="data-list__bullet" />
                <span className="data-list__text">{source}</span>
              </li>
            ))}
          </ol>
        </CollapsibleCard>
      )}
    </div>
  )
}
