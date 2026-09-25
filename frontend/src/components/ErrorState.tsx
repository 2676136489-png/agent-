import type { ReactNode } from 'react'

/**
 * ErrorState —— 全站统一的「错误态」展示块（纯展示，无业务逻辑）。
 * 以 Dashboard 错误态为模板：状态徽章 + 错误码 + 说明 + 下一步建议 + 重试。
 */
interface ErrorStateProps {
  /** 错误码（如 network_error） */
  code?: string
  /** 错误说明（必填） */
  message: string
  /** 下一步建议（可传字符串或列表等任意节点） */
  tips?: ReactNode
  /** 重试回调；不传则不渲染重试按钮 */
  onRetry?: () => void
  /** 重试按钮文案；默认「重试」 */
  retryLabel?: string
}

export function ErrorState({ code, message, tips, onRetry, retryLabel = '重试' }: ErrorStateProps) {
  return (
    <div className="state state-error alert alert--error" role="alert">
      <div className="alert__row">
        <span className="badge badge--error">出错</span>
        {code && <code className="alert__code">{code}</code>}
      </div>
      <p className="alert__message">{message}</p>
      {tips && <div className="state__tips">{tips}</div>}
      {onRetry && (
        <div className="state-error__actions">
          <button type="button" className="button" onClick={onRetry}>
            {retryLabel}
          </button>
        </div>
      )}
    </div>
  )
}
