import { useCallback, useEffect, useMemo, useState } from 'react'
import { listRuns } from '../../api/graph'
import { ApiClientError } from '../../api/client'
import { StatusBadge } from '../../components/StatusBadge'
import { EmptyState } from '../../components/EmptyState'
import { LoadingState } from '../../components/LoadingState'
import { ErrorState } from '../../components/ErrorState'
import type { ResearchRunSummary } from '../../types/graph'

const STATUS_LABEL: Record<string, string> = {
  completed: '已完成',
  awaiting_approval: '待确认',
  running: '运行中',
  failed: '失败',
  cancelled: '已取消',
}

const STATUS_VARIANT: Record<string, 'ok' | 'warn' | 'error' | 'info' | 'running'> = {
  completed: 'ok',
  awaiting_approval: 'warn',
  running: 'running',
  failed: 'error',
  cancelled: 'warn',
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString()
}

export function Evaluation() {
  const [runs, setRuns] = useState<ResearchRunSummary[]>([])
  // 首屏即为 loading：避免数据到达前误显示「暂无运行记录」的空态闪烁
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // [F6] 显式要一个足够大的 limit，否则统计只覆盖默认条数
      setRuns(await listRuns(undefined, 500))
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const stats = useMemo(() => {
    const total = runs.length
    const completed = runs.filter((r) => r.status === 'completed').length
    const failed = runs.filter((r) => r.status === 'failed').length
    const cancelled = runs.filter((r) => r.status === 'cancelled').length
    const awaiting = runs.filter((r) => r.status === 'awaiting_approval').length
    return { total, completed, failed, cancelled, awaiting }
  }, [runs])

  return (
    <section className="panel">
      <header className="panel__header">
        <div>
          <p className="eyebrow">效果评估</p>
          <h2 className="panel__title">运行效果一览</h2>
          <p className="panel__subtitle">统计深度研究的运行情况与分布，帮助判断整体可用性。</p>
        </div>
      </header>

      {error && <ErrorState message={error} onRetry={() => void load()} />}

      {loading && runs.length === 0 && <LoadingState variant="table" rows={5} />}

      {!loading && (
        <>
          <div className="stat-grid">
            <div className="card card--stat">
              <span className="stat-card__value">{stats.total}</span>
              <span className="stat-card__label">总运行次数</span>
            </div>
            <div className="card card--stat">
              <span className="stat-card__value stat-card__value--ok">{stats.completed}</span>
              <span className="stat-card__label">已完成</span>
            </div>
            <div className="card card--stat">
              <span className="stat-card__value stat-card__value--warn">{stats.awaiting}</span>
              <span className="stat-card__label">待确认</span>
            </div>
            <div className="card card--stat">
              <span className="stat-card__value stat-card__value--error">{stats.failed + stats.cancelled}</span>
              <span className="stat-card__label">失败 / 取消</span>
            </div>
          </div>

          <section className="activity">
            <div className="activity__head">
              <h3 className="plan__heading text-flush">最近运行</h3>
              <button className="link-button" onClick={() => void load()} disabled={loading}>
                {loading ? '刷新中…' : '刷新'}
              </button>
            </div>
            {runs.length === 0 ? (
              <EmptyState title="暂无运行记录" description="启动一次研究后，这里会出现统计数据与最近运行。" />
            ) : (
              <ul className="run-list">
                {runs.slice(0, 15).map((run) => (
                  <li key={run.thread_id} className="run-list__item">
                    <div className="run-list__row" title={run.question}>
                      <StatusBadge variant={STATUS_VARIANT[run.status] ?? 'info'}>
                        {STATUS_LABEL[run.status] ?? run.status}
                      </StatusBadge>
                      <span className="run-list__q">{run.question}</span>
                      <span className="hint">{formatTime(run.updated_at)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </section>
  )
}
