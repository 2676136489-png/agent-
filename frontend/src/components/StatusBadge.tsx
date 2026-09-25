import type { ReactNode } from 'react'

type StatusVariant = 'ok' | 'error' | 'warn' | 'info' | 'running' | 'neutral'

interface StatusBadgeProps {
  variant: StatusVariant
  children: ReactNode
  className?: string
}

const VARIANT_CLASS: Record<StatusVariant, string> = {
  ok: 'badge--ok',
  error: 'badge--error',
  warn: 'badge--warn',
  info: 'badge--info',
  running: 'badge--running',
  neutral: '',
}

export function StatusBadge({ variant, children, className = '' }: StatusBadgeProps) {
  return <span className={`badge ${VARIANT_CLASS[variant]} ${className}`.trim()}>{children}</span>
}
