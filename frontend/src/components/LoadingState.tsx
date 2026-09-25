/**
 * LoadingState —— 全站统一的「加载态」骨架屏（纯展示，无业务逻辑）。
 * 使用固定高度占位块 + 纯 CSS shimmer，消除内容到达时的页面跳动（CLS）。
 */
type LoadingVariant = 'card' | 'list' | 'table' | 'inline'

/** 各变体的默认占位行数 */
const DEFAULT_ROWS: Record<LoadingVariant, number> = {
  card: 3,
  list: 4,
  table: 5,
  inline: 1,
}

interface LoadingStateProps {
  /** 骨架形态，决定占位块高度；默认 card */
  variant?: LoadingVariant
  /** 覆盖占位行数；默认由 variant 决定 */
  rows?: number
  /** 可选加载文案（屏幕阅读器与视觉同时可见） */
  label?: string
}

export function LoadingState({ variant = 'card', rows, label }: LoadingStateProps) {
  const requestedRows = rows ?? DEFAULT_ROWS[variant]
  const count = Math.max(1, Math.floor(requestedRows))
  const placeholders = Array.from({ length: count }, (_, index) => index)

  return (
    <div
      className={`state state-loading state-loading--${variant}`}
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={label ?? '加载中'}
    >
      {label && <p className="state-loading__label">{label}</p>}
      <div className="state-loading__body">
        {placeholders.map((index) => (
          <div key={index} className="skeleton" />
        ))}
      </div>
    </div>
  )
}
