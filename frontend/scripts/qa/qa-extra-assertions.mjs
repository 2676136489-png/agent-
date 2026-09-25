/**
 * QA 独立补充断言（严过关）。不改动工程师的 smoke-render.mjs。
 * 侧重点：工程师可能遗漏的「移动端溢出防护 / 死类双向核查 / 标题令牌 / 无障碍契约 / 硬编码残留」。
 * 运行：node scripts/qa/qa-extra-assertions.mjs
 */
import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const stylesDir = path.join(root, 'src', 'styles')
const cssFiles = fs.readdirSync(stylesDir).filter((f) => f.endsWith('.css'))
const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '')
const cssOf = Object.fromEntries(cssFiles.map((f) => [f, fs.readFileSync(path.join(stylesDir, f), 'utf8')]))
const cssNoComments = Object.fromEntries(Object.entries(cssOf).map(([f, s]) => [f, stripComments(s)]))
const allCss = Object.values(cssNoComments).join('\n')

// 收集所有 tsx
const tsxFiles = []
;(function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) walk(p)
    else if (e.name.endsWith('.tsx')) tsxFiles.push(p)
  }
})(path.join(root, 'src'))
const allTsx = tsxFiles.map((f) => fs.readFileSync(f, 'utf8')).join('\n')

const checks = []
const expect = (name, cond, detail = '') => checks.push([name, !!cond, detail])

/* ---------- 1) 移动端溢出防护：run-list 网格列必须被夹紧 ---------- */
const gridClamped = /\.run-list\s*\{[^}]*grid-template-columns\s*:\s*minmax\(\s*0\s*,/.test(allCss)
const itemMinW0 = /\.run-list__item\s*\{[^}]*min-width\s*:\s*0/.test(allCss)
expect('防溢出：.run-list 使用 minmax(0, 1fr) 或 .run-list__item{min-width:0}', gridClamped || itemMinW0, `minmax=${gridClamped} itemMinW0=${itemMinW0}`)

/* ---------- 2) run-list 行盒 min-width 链路 ---------- */
expect('run-list 行盒（.run-list__btn/.run-list__row）显式 min-width:0', /\.run-list__btn[\s\S]{0,200}min-width\s*:\s*0/.test(allCss))

/* ---------- 3) 标题字号令牌化 ---------- */
const tokenCss = cssOf['tokens.css'] || ''
const textTokens = [...tokenCss.matchAll(/--text-[a-z0-9-]+\s*:/g)].map((m) => m[0].replace(/\s*:$/, ''))
expect('tokens.css 定义 ≥8 个 --text-* 字号令牌', textTokens.length >= 8, `count=${textTokens.length}`)

const titleRule = allCss.match(/\.panel__title\s*\{[^}]*\}/)
expect('.panel__title 字号引用 var(--text-*)', !!titleRule && /font-size\s*:\s*var\(--text-/.test(titleRule[0]))
const heroRule = allCss.match(/\.hero h1\s*\{[^}]*\}/)
expect('.hero h1 字号引用 var(--text-hero)', !!heroRule && /font-size\s*:\s*var\(--text-hero\)/.test(heroRule[0]))

/* ---------- 4) 硬编码残留：颜色 / 字号 ---------- */
const hexInBusiness = cssFiles
  .filter((f) => f !== 'tokens.css')
  .flatMap((f) => [...cssNoComments[f].matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map((m) => `${f}:${m[0]}`))
const hexNonWhite = hexInBusiness.filter((x) => !/#(fff|ffffff)$/i.test(x))
expect('业务 CSS 无 #hex 颜色残留（白色文本/圆点除外）', hexNonWhite.length === 0, `残留=${JSON.stringify(hexNonWhite)}`)

const pxFont = cssFiles
  .filter((f) => f !== 'tokens.css')
  .flatMap((f) => [...cssNoComments[f].matchAll(/font-size\s*:\s*[^;]*?(\d+)px/g)].map((m) => `${f}:${m[0]}`))
expect('业务 CSS 无 font-size:Npx 硬编码（≤1 处已知例外）', pxFont.length <= 1, `命中=${JSON.stringify(pxFont)}`)

/* ---------- 5) 死类双向检查 ---------- */
// 反向：CSS 定义但 tsx 0 引用（排除由模板字面量 `${}` 动态拼出的后缀类）
const dynamicPrefixes = [...allTsx.matchAll(/([a-zA-Z][a-zA-Z0-9_-]*--)\$\{/g)].map((m) => m[1])
const cssClasses = [...new Set([...allCss.matchAll(/\.([a-zA-Z][a-zA-Z0-9_-]*)/g)].map((m) => m[1]))]
const referenced = (c) => {
  if (new RegExp(`(^|[^a-zA-Z0-9_-])${c.replace(/[-]/g, '\\-')}([^a-zA-Z0-9_-]|$)`, 'm').test(allTsx)) return true
  return dynamicPrefixes.some((p) => c.startsWith(p))
}
const deadInCss = cssClasses.filter((c) => !referenced(c))
expect('CSS 无 0 引用死类（定义但 tsx 未使用）', deadInCss.length === 0, `死类=${JSON.stringify(deadInCss.slice(0, 40))}`)

// 正向：tsx 使用但 CSS 未定义（仅取字面量 className；剔除 `foo--${}` 动态前缀残留）
const jsxTokens = new Set()
for (const m of allTsx.matchAll(/className="([^"]+)"/g)) m[1].split(/\s+/).forEach((t) => t && jsxTokens.add(t))
for (const m of allTsx.matchAll(/className=\{`([^`]+)`\}/g)) {
  m[1].replace(/\$\{[^}]*\}/g, ' ').split(/\s+/).forEach((t) => t && jsxTokens.add(t))
}
const undefinedClasses = [...jsxTokens].filter((t) => !t.endsWith('--') && !cssClasses.includes(t))
expect('JSX 字面量 className 均在 CSS 中有定义', undefinedClasses.length === 0, `未定义=${JSON.stringify(undefinedClasses)}`)

/* ---------- 6) 无障碍契约 ---------- */
const compDir = path.join(root, 'src', 'components')
const loading = fs.readFileSync(path.join(compDir, 'LoadingState.tsx'), 'utf8')
const error = fs.readFileSync(path.join(compDir, 'ErrorState.tsx'), 'utf8')
const empty = fs.readFileSync(path.join(compDir, 'EmptyState.tsx'), 'utf8')
expect('LoadingState 含 role="status" + aria-busy', /role="status"/.test(loading) && /aria-busy="true"/.test(loading))
expect('ErrorState 含 role="alert" + badge--error', /role="alert"/.test(error) && /badge--error/.test(error))
expect('EmptyState 仅在有 actionLabel+onAction 时渲染按钮', /Boolean\(actionLabel && onAction\)/.test(empty))

/* ---------- 7) 断点收敛（两档语义）---------- */
const responsive = cssOf['responsive.css'] || ''
const medias = [...responsive.matchAll(/@media\s*\(max-width:\s*(\d+)px\)/g)].map((m) => m[1])
const nonPreference = medias.filter((n) => !['1023', '767'].includes(n))
expect('responsive.css 仅 1023/767 两个宽度断点', nonPreference.length === 0, `其他断点=${JSON.stringify(nonPreference)}`)

/* ---------- 输出 ---------- */
let failed = 0
for (const [n, ok, detail] of checks) {
  if (!ok) failed++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${!ok && detail ? `  → ${detail}` : ''}`)
}
console.log(`\n结果: ${checks.length - failed}/${checks.length} 通过`)
process.exit(failed ? 1 : 0)
