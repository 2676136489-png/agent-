import { StatusBadge } from './StatusBadge'
import { BoltIcon } from './icons'

interface ToolCall {
  tool: string
  args: Record<string, unknown>
  ok: boolean
  error: string | null
  error_kind: string | null
  duration_ms: number
  output_preview?: string | null
}

interface ToolCallCardProps {
  call: ToolCall
}

export function ToolCallCard({ call }: ToolCallCardProps) {
  const entries = Object.entries(call.args)

  return (
    <div className="tool-call-card">
      <div className="tool-call-card__head">
        <span className="tool-call-card__tool">
          <BoltIcon size={13} />
          {call.tool}
        </span>
        <div className="tool-call-card__meta">
          <StatusBadge variant={call.ok ? 'ok' : 'error'}>
            {call.ok ? '成功' : call.error_kind ?? '失败'}
          </StatusBadge>
          <span>{call.duration_ms} ms</span>
        </div>
      </div>

      {entries.length > 0 && (
        <div className="tool-call-card__params">
          <div className="tool-call-card__params-title">调用参数</div>
          <div className="tool-call-card__params-grid">
            {entries.map(([key, value]) => (
              <div key={key} className="param-row">
                <span className="param-row__key">{key}</span>
                <span className="param-row__value">
                  {typeof value === 'string' ? value : JSON.stringify(value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {call.ok ? (
        call.output_preview && (
          <div>
            <div className="tool-call-card__output-title">返回结果</div>
            <pre className="tool-call-card__output">{call.output_preview}</pre>
          </div>
        )
      ) : (
        <div className="tool-call-card__error">{call.error}</div>
      )}
    </div>
  )
}
