import { useCallback, useEffect, useState } from 'react'
import { getResearch, listRuns } from '../../api/graph'
import { ApiClientError } from '../../api/client'
import { CloseIcon } from '../../components/icons'
import { Markdown } from '../../components/Markdown'
import { StatusBadge } from '../../components/StatusBadge'
import { EmptyState } from '../../components/EmptyState'
import { LoadingState } from '../../components/LoadingState'
import { ErrorState } from '../../components/ErrorState'
import type { ResearchRun, ResearchRunSummary } from '../../types/graph'

const STATUS_LABEL: Record<string, string> = {
  completed: '已完成',
  awaiting_approval: '待确认',
  running: '运行中',
  failed: '失败',
  cancelled: '已取消',
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diff = Math.max(0, Math.floor((now.getTime() - d.getTime()) / 1000))
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`
  return d.toLocaleDateString()
}

function ReportView({ run }: { run: ResearchRun }) {
  const report = run.report
  if (!report) return <p className="hint">本次运行没有生成报告。</p>
  return (
    <article className="report-panel">
      <h3 className="report-panel__title">{report.title || run.question}</h3>
      <div className="report-panel__summary">
        <Markdown>{report.summary}</Markdown>
      </div>
      {report.sections.map((section) => (
        <section key={section.heading} className="report-panel__section">
          <h4>{section.heading}</h4>
          <Markdown>{section.content}</Markdown>
        </section>
      ))}
      {report.limitations.length > 0 && (
        <div className="report-panel__limitations">
          <strong>局限</strong>
          <Markdown>{report.limitations.map((item, i) => `${i + 1}. ${item}`).join('\n')}</Markdown>
        </div>
      )}
    </article>
  )
}

export function Reports() {
  const [runs, setRuns] = useState<ResearchRunSummary[]>([])
  // 首屏即为 loading：避免数据到达前误显示「还没有报告」的空态闪烁
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<ResearchRun | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setRuns(await listRuns('completed'))
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function openRun(threadId: string) {
    setError(null)
    try {
      const run = await getResearch(threadId)
      if (run) setSelected(run)
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : '加载详情失败')
    }
  }

  return (
    <section className="panel">
      <header className="panel__header">
        <div>
          <p className="eyebrow">研究报告</p>
          <h2 className="panel__title">已生成的研究报告</h2>
          <p className="panel__subtitle">在这里查看所有已完成的研究报告，点击条目可阅读全文。</p>
        </div>
      </header>

      {error && <ErrorState message={error} onRetry={() => void load()} />}

      {loading && runs.length === 0 && <LoadingState variant="list" rows={4} label="正在加载报告列表…" />}

      {!loading && !error && runs.length === 0 && (
        <EmptyState
          title="还没有已完成的研究报告"
          description="到「深度研究」启动一次研究并批准生成报告后，这里会自动出现。"
        />
      )}

      {!loading && runs.length > 0 && (
        <div className="report-list">
          {runs.map((run) => (
            <button
              key={run.thread_id}
              className="card card--interactive report-card"
              onClick={() => void openRun(run.thread_id)}
            >
              <div className="report-card__head">
                <StatusBadge variant="ok">{STATUS_LABEL[run.status] ?? run.status}</StatusBadge>
                <span className="hint">{formatTime(run.updated_at)}</span>
              </div>
              <p className="report-card__title">{run.question}</p>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal__head">
              <h3 className="panel__title text-flush">报告详情</h3>
              <button className="nav-icon" aria-label="关闭" onClick={() => setSelected(null)}>
                <CloseIcon size={18} />
              </button>
            </div>
            <ReportView run={selected} />
          </div>
        </div>
      )}
    </section>
  )
}
