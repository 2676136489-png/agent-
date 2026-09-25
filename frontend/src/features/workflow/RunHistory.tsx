import { useCallback, useEffect, useState } from 'react'
import { listRuns } from '../../api/graph'
import { ApiClientError } from '../../api/client'
import { StatusBadge } from '../../components/StatusBadge'
import { EmptyState } from '../../components/EmptyState'
import { LoadingState } from '../../components/LoadingState'
import { ErrorState } from '../../components/ErrorState'
import type { ResearchRunSummary } from '../../types/graph'

export interface RunHistoryProps {
  onSelect?: (threadId: string) => void
  limit?: number
  status?: ResearchRunSummary['status']
}

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
  const now = new Date()
  const diff = Math.max(0, Math.floor((now.getTime() - d.getTime()) / 1000))
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`
  return d.toLocaleDateString()
}

function truncate(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max)}…` : text
}

export function RunHistory({ onSelect, limit = 10, status }: RunHistoryProps) {
  const [runs, setRuns] = useState<ResearchRunSummary[]>([])
  // 首屏即为 loading：避免数据到达前误显示「还没有运行记录」的空态闪烁
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    // [F3] 之前只有 try/finally 没有 catch：请求失败被静默吞掉，
    // 界面显示"还没有运行记录"，用户会以为真的没有数据。
    try {
      setRuns(await listRuns(status))
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : '加载历史运行失败')
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <section className="activity">
      <div className="activity__head">
        <h3 className="plan__heading text-flush">历史运行</h3>
        <button className="link-button" onClick={() => void refresh()} disabled={loading}>
          {loading ? '刷新中…' : '刷新'}
        </button>
      </div>

      {loading && runs.length === 0 && <LoadingState variant="list" rows={3} />}

      {error && <ErrorState message={error} onRetry={() => void refresh()} />}

      {!loading && !error && runs.length === 0 && (
        <EmptyState title="还没有运行记录" description="启动一次研究后，这里会列出历史运行，可点击加载。" />
      )}

      {runs.length > 0 && (
        <ul className="run-list">
          {runs.slice(0, limit).map((run) => (
            <li key={run.thread_id} className="run-list__item">
              <button
                className="run-list__btn"
                onClick={() => onSelect?.(run.thread_id)}
                disabled={!onSelect}
                title={onSelect ? '点击加载这次运行' : run.question}
              >
                <StatusBadge variant={STATUS_VARIANT[run.status] ?? 'info'}>{STATUS_LABEL[run.status] ?? run.status}</StatusBadge>
                <span className="run-list__q">{truncate(run.question)}</span>
                <span className="hint">{formatTime(run.updated_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
