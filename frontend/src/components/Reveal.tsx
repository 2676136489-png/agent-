import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'

/**
 * 滚动揭示：进入视口时淡入上移，只触发一次。
 * 用独立 IntersectionObserver，动态插入的内容（如 SSE 事件）也能正常揭示。
 */
export function Reveal({
  children,
  className,
  delay = 0,
  as = 'div',
  style,
}: {
  children: ReactNode
  className?: string
  delay?: number
  as?: 'div' | 'section' | 'li' | 'article'
  style?: CSSProperties
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          io.disconnect()
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  const Tag = as as 'div'
  return (
    <Tag
      ref={ref as never}
      className={className}
      data-reveal=""
      data-visible={visible}
      style={{ ...(delay ? { transitionDelay: `${delay}ms` } : {}), ...style }}
    >
      {children}
    </Tag>
  )
}
