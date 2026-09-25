import type { ReactNode } from 'react'

export interface ProcessTimelineItem {
  id: string | number
  title: string
  body?: ReactNode
  detail?: ReactNode
  status: 'done' | 'active' | 'error' | 'pending'
  time?: string
}

interface ProcessTimelineProps {
  items: ProcessTimelineItem[]
}

export function ProcessTimeline({ items }: ProcessTimelineProps) {
  return (
    <ul className="process-timeline">
      {items.map((item) => (
        <li
          key={item.id}
          className={`process-timeline__item process-timeline__item--${item.status}`}
        >
          <span className="process-timeline__dot" aria-hidden="true" />
          <div>
            <div className="process-timeline__head">
              <span className="process-timeline__title">{item.title}</span>
              {item.time && <span className="process-timeline__time">{item.time}</span>}
            </div>
            {item.body && <div className="process-timeline__body">{item.body}</div>}
            {item.detail && <div className="process-timeline__detail">{item.detail}</div>}
          </div>
        </li>
      ))}
    </ul>
  )
}
