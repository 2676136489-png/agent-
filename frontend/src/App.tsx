import { useEffect, useState } from 'react'
import { ChevronDownIcon, CloseIcon, MenuIcon, MoonIcon, SunIcon } from './components/icons'
import { Dashboard } from './features/dashboard/Dashboard'
import { ResearchPlanner } from './features/research/ResearchPlanner'
import { AgentRunner } from './features/agent/AgentRunner'
import { KnowledgeBase } from './features/knowledge/KnowledgeBase'
import { ResearchWorkflow } from './features/workflow/ResearchWorkflow'
import { Tutorial } from './features/tutorial/Tutorial'
import { Reports } from './features/reports/Reports'
import { Evaluation } from './features/evaluation/Evaluation'
import { Settings } from './features/settings/Settings'

/**
 * 顶栏导航 + 内容区。
 *
 * 响应式（纯 CSS 断点，除抽屉开合外无额外状态）：
 *  - ≥1200px：组标签可见，9 项平铺在 3 组内；
 *  - 1024–1199px：隐藏组标签，只留组间竖线；
 *  - 768–1023px：顶栏只留 NAV_CORE_KEYS 三项 +「更多」下拉（3 组标题 + 全部 9 项）；
 *  - <768px：汉堡按钮 + 移动抽屉（唯一的 navOpen state，9 项 + 3 组标题）。
 */

/* ===================== 导航数据结构（S1 / §2.1） ===================== */

export type PageKey =
  | 'dashboard' | 'workflow' | 'research' | 'agent' | 'knowledge'
  | 'reports' | 'evaluation' | 'settings' | 'tutorial'

/** 视觉层级：家 / 主推 / 次（开发者向也用次） */
export type NavTier = 'home' | 'primary' | 'secondary'

export interface NavItem {
  key: PageKey
  /** 导航显示文案（唯一可改名的地方） */
  label: string
  /** 视觉层级 */
  tier: NavTier
  /** 推荐角标（只有 workflow 为 true） */
  recommend?: boolean
  /** 命令面板 / 抽屉的补充说明（可选） */
  hint?: string
}

export interface NavGroup {
  id: 'home' | 'research' | 'results' | 'system'
  /** 组标签文案；'home' 为空字符串（顶栏不渲染标签，见 Q2） */
  label: string
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  { id: 'home', label: '', items: [
    { key: 'dashboard', label: '概览', tier: 'home' },
  ]},
  { id: 'research', label: '研究', items: [
    { key: 'workflow', label: '深度研究', tier: 'primary', recommend: true, hint: '推荐入口' },
    { key: 'research', label: '研究规划', tier: 'secondary' },
    { key: 'agent', label: '智能体', tier: 'secondary' },
    { key: 'knowledge', label: '知识库', tier: 'secondary' },
  ]},
  { id: 'results', label: '结果', items: [
    { key: 'reports', label: '研究报告', tier: 'secondary' },
    { key: 'evaluation', label: '效果评估', tier: 'secondary', hint: '开发者向' },
  ]},
  { id: 'system', label: '系统', items: [
    { key: 'settings', label: '系统设置', tier: 'secondary', hint: '开发者向' },
    { key: 'tutorial', label: '使用教程', tier: 'secondary' },
  ]},
]

/** 扁平索引：保持 NAV_ITEMS 的既有用法（navigate() 查找等）不变 */
export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items)

/**
 * 768–1023px 顶栏保留项。不在本列表中的组，在该档位整组不渲染。
 * ⚠️ M7：严格等于 ['dashboard','workflow','reports']，不要增删。
 */
const NAV_CORE_KEYS: PageKey[] = ['dashboard', 'workflow', 'reports']

/**
 * 抽屉是「全量说明」场景，家的组标签也要出（NAV_GROUPS 里 home.label 为空字符串）。
 * 见 §2.1 Q2 与 §2.5。
 */
const DRAWER_GROUP_LABEL: Partial<Record<NavGroup['id'], string>> = { home: '概览' }

/* 图标统一见 src/components/icons.tsx（§5.1 B1）：本文件不再自行声明 svg 图标 */

/* ===================== 会话内页面记忆（§2.6） ===================== */

const PAGE_KEY = 'arw-page'
/** 白名单：只有 NAV_ITEMS 里出现过的 key 才可被恢复，避免存储被篡改后落到陌生页 */
const PAGE_KEYS: PageKey[] = NAV_ITEMS.map((i) => i.key)

/** 读取：非法值一律回落 'dashboard'，绝不信任存储内容 */
function readStoredPage(): PageKey {
  try {
    const v = sessionStorage.getItem(PAGE_KEY)
    return v && (PAGE_KEYS as string[]).includes(v) ? (v as PageKey) : 'dashboard'
  } catch {
    // 隐私模式 / 禁用存储
    return 'dashboard'
  }
}

/* ===================== 共用的导航项渲染（§2.5） ===================== */

interface NavLinkButtonProps {
  item: NavItem
  page: PageKey
  /** 是否标记 data-core="true"（决定 768–1023 档位顶栏是否保留） */
  core: boolean
  onNavigate: (key: string) => void
}

/** 三个容器（顶栏 / 更多下拉 / 抽屉）共用同一份渲染，零分支 */
function NavLinkButton({ item, page, core, onNavigate }: NavLinkButtonProps) {
  const active = item.key === page
  const cls = [
    'nav-link',
    item.tier === 'primary' ? 'nav-link--primary' : '',
    item.key === 'evaluation' || item.key === 'settings' ? 'nav-link--dev' : '',
    active ? 'nav-link--active' : '',
  ].filter(Boolean).join(' ')

  return (
    <button
      type="button"
      className={cls}
      data-core={core ? 'true' : 'false'}
      aria-current={active ? 'page' : undefined}
      onClick={() => onNavigate(item.key)}
    >
      {item.label}
      {item.recommend && <span className="nav-link__badge">推荐</span>}
      {item.hint && <span className="nav-link__hint">{item.hint}</span>}
    </button>
  )
}

/* ===================== App ===================== */

export default function App() {
  // 初始值读 sessionStorage；写入放在 effect 里，避免首帧把 'dashboard' 写回去
  const [page, setPage] = useState<PageKey>(() => readStoredPage())
  const [theme, setTheme] = useState<'light' | 'dark'>(
    () => (localStorage.getItem('arw-theme') as 'light' | 'dark') || 'light',
  )
  const [scrolled, setScrolled] = useState(false)
  // 唯一的 UI 状态：移动端抽屉开合
  const [navOpen, setNavOpen] = useState(false)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('arw-theme', theme)
  }, [theme])

  // 会话内页面记忆：切页 → 写入（§2.6）
  useEffect(() => {
    try {
      sessionStorage.setItem(PAGE_KEY, page)
    } catch {
      // 存储被禁用时静默降级
    }
  }, [page])

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // 抽屉开启时：锁定 body 滚动 + Esc 关闭；视口放大回桌面档时自动收起（避免滚动锁残留）
  useEffect(() => {
    if (!navOpen) return
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setNavOpen(false)
    }
    const mq = window.matchMedia('(min-width: 768px)')
    const onViewportChange = () => {
      if (mq.matches) setNavOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    mq.addEventListener('change', onViewportChange)

    return () => {
      document.body.style.overflow = prevOverflow
      window.removeEventListener('keydown', onKeyDown)
      mq.removeEventListener('change', onViewportChange)
    }
  }, [navOpen])

  const navigate = (key: string) => {
    const item = NAV_ITEMS.find((i) => i.key === key)
    if (item) {
      setPage(item.key)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  /** 抽屉内点击后：导航并收起抽屉 */
  const navigateAndClose = (key: string) => {
    navigate(key)
    setNavOpen(false)
  }

  /** 该组是否含 core 项（顶栏整组跳过，避免出现「空组 + 空竖线」） */
  const hasCore = (group: NavGroup) => group.items.some((item) => NAV_CORE_KEYS.includes(item.key))

  return (
    <div className="site-shell">
      <header className="global-nav" data-scrolled={scrolled}>
        <div className="nav-inner">
          <a
            className="nav-brand"
            href="#"
            onClick={(e) => {
              e.preventDefault()
              navigate('dashboard')
            }}
          >
            <span className="nav-logo">ARW</span>
            AI 研究工作台
            <small>研究智能体</small>
          </a>

          {/* ≥768px 顶栏：按分组渲染；NAV_CORE_KEYS 之外的项打 data-core="false"，由 responsive.css 隐藏 */}
          <nav className="nav-menu" aria-label="主导航">
            {NAV_GROUPS.map((group) =>
              hasCore(group) ? (
                <div className="nav-group" data-group={group.id} key={group.id}>
                  {group.label && (
                    <span className="nav-group__label" aria-hidden="true">{group.label}</span>
                  )}
                  {group.items.map((item) => (
                    <NavLinkButton
                      key={item.key}
                      item={item}
                      page={page}
                      core={NAV_CORE_KEYS.includes(item.key)}
                      onNavigate={navigate}
                    />
                  ))}
                </div>
              ) : null,
            )}
          </nav>

          {/* 平板档（768–1023px）「更多」下拉：纯 CSS 展开，无 state。
              内部按组展示全部 9 项（含组标题），是用户第一次学到分组心智的地方。 */}
          <div className="nav-more">
            <button className="nav-link nav-more__btn" type="button" aria-haspopup="true">
              更多
              <span className="nav-more__caret" aria-hidden="true"><ChevronDownIcon /></span>
            </button>
            <div className="nav-more__menu">
              <nav className="nav-more__groups" aria-label="更多导航">
                {NAV_GROUPS.map((group) => (
                  <div className="nav-more__group" key={group.id}>
                    <div className="nav-more__label" aria-hidden="true">{group.label || DRAWER_GROUP_LABEL[group.id] || ''}</div>
                    {group.items.map((item) => (
                      <NavLinkButton
                        key={item.key}
                        item={item}
                        page={page}
                        core={false}
                        onNavigate={navigate}
                      />
                    ))}
                  </div>
                ))}
              </nav>
            </div>
          </div>

          <div className="nav-actions">
            <button
              className="nav-icon"
              type="button"
              aria-label={theme === 'light' ? '切换到深色外观' : '切换到浅色外观'}
              onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
            >
              {theme === 'light' ? <MoonIcon size={17} /> : <SunIcon size={17} />}
            </button>

            <button
              className="nav-toggle"
              type="button"
              aria-label="打开导航菜单"
              aria-expanded={navOpen}
              aria-controls="nav-drawer"
              onClick={() => setNavOpen(true)}
            >
              <MenuIcon size={18} />
            </button>
          </div>
        </div>
      </header>

      {/* 移动抽屉（<768px 才会被打开；纯 CSS 断点控制显隐，无额外状态） */}
      {navOpen && (
        <div className="nav-drawer-layer">
          <button className="nav-scrim" type="button" aria-label="关闭导航菜单" onClick={() => setNavOpen(false)} />
          <aside id="nav-drawer" className="nav-drawer" role="dialog" aria-modal="true" aria-label="主导航">
            <div className="nav-drawer__head">
              <span className="nav-drawer__title">导航</span>
              <button className="nav-icon" type="button" aria-label="关闭" onClick={() => setNavOpen(false)}>
                <CloseIcon size={18} />
              </button>
            </div>
            {NAV_GROUPS.map((group) => (
              <div className="nav-drawer__group" key={group.id}>
                <div className="nav-drawer__label">
                  {group.label || DRAWER_GROUP_LABEL[group.id] || ''}
                </div>
                {group.items.map((item) => (
                  <NavLinkButton
                    key={item.key}
                    item={item}
                    page={page}
                    core={false}
                    onNavigate={navigateAndClose}
                  />
                ))}
              </div>
            ))}
          </aside>
        </div>
      )}

      <main className="main">
        <div className="shell shell--tight">
          {page === 'dashboard' && <Dashboard onNavigate={navigate} />}
          {page === 'workflow' && <ResearchWorkflow />}
          {page === 'research' && <ResearchPlanner />}
          {page === 'agent' && <AgentRunner />}
          {page === 'knowledge' && <KnowledgeBase />}
          {page === 'tutorial' && <Tutorial onNavigate={navigate} />}
          {page === 'reports' && <Reports />}
          {page === 'evaluation' && <Evaluation />}
          {page === 'settings' && <Settings />}
        </div>
      </main>

      {/* T05 在此挂载 <ToastHost />（模块级单例，零 prop drilling，不改动既有元素结构） */}
    </div>
  )
}
