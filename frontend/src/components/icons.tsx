/**
 * 全局图标库（S3 / §5.1 B1）。
 *
 * 图标语言规范（AC9：同一页面 ≤2 套图标语言，本文件是唯一的线图标来源）：
 *  - 24×24 视框、1.75 描边、圆头圆角、`fill="none" + stroke="currentColor"`；
 *  - 一律 `aria-hidden="true" focusable="false"`：图标本身不带语义，
 *    承载语义的容器（按钮 / 卡片标题）用既有 `aria-label` 说明；
 *  - 尺寸由 `size` 属性给 px，不写 CSS 尺寸，避免与容器 flex 布局打架。
 *
 * 迁移范围（§5.1）：
 *  - B1：本文件接管 App.tsx 原有 4 个图标函数（Sun / Moon / Menu / Close）；
 *  - B2：字符图标 `⚡` / `✕` / `▸` / `▾` 全部改为本文件的组件；
 *  - B3：事件流 emoji 映射表（ResearchWorkflow 的 EVENT_ICON）改为组件映射；
 *  - B4：`.card__icon` / `.module__icon` 的汉字改为本文件的组件。
 *
 * 导航 9 项与分组 3 个的图标已按 B1 要求导出，但当前 DOM 未引用
 * （S1 的导航刻意是纯文字 + 推荐角标，已验收；它们在 T06 的 ⌘K 命令面板里才露面）。
 */

import type { ReactNode, SVGProps } from 'react'

/** 图标 props：透传全部 SVG 属性，仅固定视框与无障碍属性 */
export interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'viewBox' | 'xmlns'> {
  /** 渲染边长（px），默认 18 */
  size?: number
  /** 描边宽度；默认 1.75（全库统一线宽） */
  strokeWidth?: number
}

interface SvgProps extends IconProps {
  children: ReactNode
}

/** 所有图标共用的 svg 骨架；禁止在业务代码里另写 <svg> */
function Svg({ size = 18, strokeWidth = 1.75, children, ...rest }: SvgProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  )
}

/* ===================== 主题 / 导航控件（B1：由 App.tsx 搬入） ===================== */

export function SunIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2M12 19.5v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2.5 12h2M19.5 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </Svg>
  )
}

export function MoonIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </Svg>
  )
}

export function MenuIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Svg>
  )
}

export function CloseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Svg>
  )
}

/** 「更多」下拉 / 折叠面板共用 */
export function ChevronDownIcon(props: IconProps) {
  return (
    <Svg strokeWidth={2.2} {...props}>
      <path d="M5 9l7 7 7-7" />
    </Svg>
  )
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <Svg strokeWidth={2} {...props}>
      <path d="M9 6l6 6-6 6" />
    </Svg>
  )
}

/* ===================== 语义图标（B3：事件流） ===================== */

export function PlayIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 5.2 19 12 8 18.8z" />
    </Svg>
  )
}

export function PauseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9.5 5v14M14.5 5v14" />
    </Svg>
  )
}

export function BulbIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9.5 18h5M10.5 21h3" />
      <path d="M12 3a6 6 0 0 0-3.6 10.8c.5.4.8 1 .8 1.6v.6h5.6v-.6c0-.6.3-1.2.8-1.6A6 6 0 0 0 12 3z" />
    </Svg>
  )
}

export function ListIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9 6.5h11M9 12h11M9 17.5h11M4.5 6.5h.01M4.5 12h.01M4.5 17.5h.01" />
    </Svg>
  )
}

export function SearchIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M20 20l-4.3-4.3" />
    </Svg>
  )
}

export function FileIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 3h8l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
      <path d="M14 3v4h4" />
    </Svg>
  )
}

export function WrenchIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M14.7 6.3a4 4 0 0 1 5.6 5.6l-8 8a2.5 2.5 0 0 1-3.5-3.5l8-8z" />
      <path d="M11 11l2 2" />
    </Svg>
  )
}

/**
 * 分析阶段（原 emoji 🔬）。
 * ⚠️ 与 §5.1 的 PuzzleIcon 不同名：该处按 🧩 推导，但锥形瓶更能直读「取样检测」，
 * 且比拼图形状更好画、在 13px 下更可辨。如要严格对齐文档，改回 puzzle 的组件名即可。
 */
export function BeakerIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9.5 3h5M10.5 3v5.2L6.2 17.4A2 2 0 0 0 7.9 20.5h8.2a2 2 0 0 0 1.7-3.1L13.5 8.2V3" />
      <path d="M8 14h8" />
    </Svg>
  )
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4.5 12.5l5 5L19.5 7" />
    </Svg>
  )
}

export function PencilIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12.5 20H21" />
      <path d="M16.4 3.6a2 2 0 0 1 2.8 0l1.2 1.2a2 2 0 0 1 0 2.8L7.5 19.4 3 21l1.6-4.5z" />
    </Svg>
  )
}

export function AlertIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 3.5 21.5 20H2.5z" />
      <path d="M12 10v4.5M12 17.2h.01" />
    </Svg>
  )
}

export function XIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Svg>
  )
}

/** 工具调用（原 `.tool-call-card__tool::before` 的 ⚡ 字符） */
export function BoltIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M13.5 2.5 5.4 13.6h5.2L9.4 21.5l9.2-11.3h-5.3z" />
    </Svg>
  )
}

/** 事件流的兜底标记（替代原先的 `•` 字符） */
export function DotIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 12h.01" strokeWidth={2.6} />
    </Svg>
  )
}

/* ===================== 模块图标（B4：替代汉字） ===================== */

/** 概览 */
export function HomeIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3.5 10.5 12 3.8l8.5 6.7V20a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1z" />
      <path d="M9.5 21v-6.5h5V21" />
    </Svg>
  )
}

/** 深度研究（该卡的 icon 语义是「做一次实验」） */
export function FlaskIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9.5 3h5M10.5 3v5.2L6.2 17.4A2 2 0 0 0 7.9 20.5h8.2a2 2 0 0 0 1.7-3.1L13.5 8.2V3" />
      <path d="M8 14h8" />
    </Svg>
  )
}

/** 研究规划 */
export function ClipboardIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9.5 4.5h5a1 1 0 0 1 1 1V6h2.5a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h2.5v-.5a1 1 0 0 1 1-1z" />
      <path d="M8 12h8M8 16h5" />
    </Svg>
  )
}

/** 智能体 */
export function BotIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="4" y="7" width="16" height="12" rx="3" />
      <path d="M12 3v4" />
      <path d="M2.5 11v2M21.5 11v2" />
      <path d="M9 13h.01M15 13h.01" strokeWidth={2.4} />
    </Svg>
  )
}

/** 知识库 */
export function BookIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 6.5A3.5 3.5 0 0 0 8.5 5H4.5v14h4A3.5 3.5 0 0 0 12 20.5z" />
      <path d="M12 6.5A3.5 3.5 0 0 1 15.5 5H19.5v14H15a3.5 3.5 0 0 1-3-3.5z" />
    </Svg>
  )
}

/** 研究报告 */
export function DocIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 3h8l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
      <path d="M14 3v4h4" />
      <path d="M9 12.5h6M9 16.5h6" />
    </Svg>
  )
}

/** 使用教程 */
export function GraduationIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M2.5 8.5 12 4.5l9.5 4-9.5 4z" />
      <path d="M6.5 10.6v4.7c0 1.7 2.5 3 5.5 3s5.5-1.3 5.5-3v-4.7" />
      <path d="M21 9.5v5" />
    </Svg>
  )
}

/** 效果评估 */
export function BarChartIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 20v-5M12 20V8M18 20v-9" />
    </Svg>
  )
}

/** 系统设置 */
export function SlidersIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 7.5h8M17 7.5h3M4 16.5h3M12 16.5h8" />
      <circle cx="14.5" cy="7.5" r="2.2" />
      <circle cx="9.5" cy="16.5" r="2.2" />
    </Svg>
  )
}

/* ===================== 其它通用图标 ===================== */

/** 撤销 / 回退（复用于「同参数重试」） */
export function UndoIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3.5 8.5h10.5a5 5 0 0 1 0 10H8" />
      <path d="M7 4.5 3 8.5l4 4" />
    </Svg>
  )
}
