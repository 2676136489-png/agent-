import { useState, type ReactNode } from 'react'

interface CollapsibleCardProps {
  title: ReactNode
  defaultOpen?: boolean
  children: ReactNode
  className?: string
  badge?: ReactNode
}

export function CollapsibleCard({
  title,
  defaultOpen = false,
  children,
  className = '',
  badge,
}: CollapsibleCardProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className={`collapsible-card ${open ? 'collapsible-card--open' : ''} ${className}`.trim()}>
      <button
        type="button"
        className="collapsible-card__header"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="collapsible-card__header-main">
          {title}
          {badge}
        </span>
        <span className="collapsible-card__chevron" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </span>
      </button>
      {open && <div className="collapsible-card__body">{children}</div>}
    </div>
  )
}
