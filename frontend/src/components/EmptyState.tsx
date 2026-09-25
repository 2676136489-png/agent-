/**
 * EmptyState —— 全站统一的「空状态」展示块（纯展示，无业务逻辑）。
 * 用于：未开始 / 无数据 / 检索无结果 等场景。
 */
interface EmptyStateProps {
  /** 图标字（单个字符或 emoji）；不传则不渲染图标 */
  icon?: string
  /** 主标题（必填） */
  title: string
  /** 一句说明 */
  description?: string
  /** 主操作按钮文案 */
  actionLabel?: string
  /** 主操作回调；与 actionLabel 同时存在时才渲染按钮 */
  onAction?: () => void
}

export function EmptyState({ icon, title, description, actionLabel, onAction }: EmptyStateProps) {
  const hasAction = Boolean(actionLabel && onAction)

  return (
    <div className="state state-empty">
      {icon && (
        <span className="state__icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <p className="state__title">{title}</p>
      {description && <p className="state__desc">{description}</p>}
      {hasAction && (
        <button type="button" className="button button--primary state__action" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  )
}
