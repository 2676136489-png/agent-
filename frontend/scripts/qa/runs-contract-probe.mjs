/**
 * QA 陈旧契约验收（严过关）—— 依据 team-lead 已裁定的分工：
 *
 *   CLAIM-1  shouldListRun(run) 是「可展示性」谓词：awaiting_approval 必须出现在列表里。
 *            防的错：把 awaiting_approval 当成陈旧 run 一起过滤掉 => 那条报告从列表消失。
 *            它渲染的是常驻「待确认」角标，与陈旧信号正交；列表一旦不含它，用户
 *            没有任何办法找回该报告 —— 这是数据丢失，不是体验问题。
 *
 *   CLAIM-2  isStaleRun(run) 是「标注」谓词，不是过滤谓词：只给 running 的 run 挂
 *            「可能已中断」提示，不改变 run 是否显示。
 *            防的错：① 前端再加一遍陈旧过滤 —— 后端 SQL 与前端两套阈值互相干扰；
 *            ② 把 awaiting_approval 套进 staleness —— 它的 updated_at 在报告产出时就
 *            定格，套任何阈值等于几分钟后从列表里删掉它。
 *
 * 用法：node scripts/qa/runs-contract-probe.mjs
 * 输出：每条断言一行结论，末尾汇总；退出码 1 表示有断言失败。
 *
 * 设计原则：本文件只做「找得到就报警」的结构守卫，绝不复制一份业务谓词到 QA 脚本里
 * （那样验证的是 QA 自己）。每条断言要么能确定地失败，要么明确报「待验」。
 */
import fs from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(import.meta.dirname, '../..')

/** 会渲染 run 列表的消费者。Reports 由服务端 status=completed 取数，不参与「可展示性」判定。 */
const RUN_LIST_CONSUMERS = [
  'src/features/workflow/RunHistory.tsx',
  'src/features/evaluation/Evaluation.tsx',
]

const results = []
/** kind: 'pass' | 'fail' | 'pending'。pending = 被测能力尚未落地，不算通过。 */
const add = (claim, name, kind, why) => results.push({ claim, name, kind, why })
const srcText = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8')

/* ---------- 前置探测：契约依赖的能力到底有没有落地 ---------- */
function detectExports(rel) {
  const files = []
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name)
      if (e.isDirectory()) walk(p)
      else if (/\.tsx?$/.test(e.name)) files.push(p)
    }
  }
  walk(path.join(ROOT, rel))
  return files.map((f) => fs.readFileSync(f, 'utf8')).join('\n')
}

const allSrc = detectExports('src')
const hasShouldListRun = /shouldListRun/.test(allSrc)
const hasIsStaleRun = /isStaleRun/.test(allSrc)

/** idle_seconds 是否贯通：前端类型定义与后端 _row_to_dict 返回键，两处都得有。 */
const feIdle = /idle_seconds/.test(srcText('src/types/graph.ts'))
const bePath = path.resolve(ROOT, '../backend/app/graph/run_store.py')
const beBlock = fs.existsSync(bePath)
  ? (srcText('../backend/app/graph/run_store.py').match(/def _row_to_dict[\s\S]*?\n {4}\}/) || [''])[0]
  : ''
const beIdle = /idle_seconds/.test(beBlock)
const idleAvailable = feIdle && beIdle

/* ---------- 结构性提取：某文件里 XxxStatus 映射的键集合 ---------- */
function statusMapKeys(text, constName) {
  const m = text.match(new RegExp(`const\\s+${constName}[^=]*=\\s*\\{([^}]*)\\}`))
  if (!m) return null
  return new Set([...m[1].matchAll(/^\s*'?([A-Za-z_][A-Za-z0-9_]*)'?\s*:/gm)].map((x) => x[1]))
}

/* ================= CLAIM-1：awaiting_approval 必须可展示 ================= */
if (!hasShouldListRun) {
  add('CLAIM-1', 'shouldListRun 已落地为可展示性谓词', 'pending',
    '前端尚未出现 shouldListRun。本轮验收的是「当前行为不含数据丢失」；谓词落地后须回来补这条断言。')
}

for (const rel of RUN_LIST_CONSUMERS) {
  const text = srcText(rel)

  // 守卫：态色映射里必须有 awaiting_approval 这个键，且不得指向陈旧文案。
  // 防的错：该状态被并进陈旧分支 => 列表里的「待确认」角标消失 => 用户失去找回入口。
  const keys = statusMapKeys(text, 'STATUS_VARIANT') || statusMapKeys(text, 'STATUS_LABEL')
  const hasKey = !!keys && keys.has('awaiting_approval')
  add('CLAIM-1', `${rel}：状态映射含 awaiting_approval 键`,
    hasKey ? 'pass' : 'fail',
    '若键不存在，说明该状态已被并进陈旧/隐藏分支，待确认报告将失去唯一的找回入口（数据丢失）。')

  // 守卫：展示型列表不得引用 idle_seconds。
  // 防的错：前端按空闲时长丢弃 run —— 可展示性只应由 status 决定。
  // 用「符号是否存在」这一确定性判断，而不是去猜调用长什么样（猜不出可靠形态的正则只会造出假绿）。
  const usesIdle = /idle_seconds/.test(text)
  add('CLAIM-1', `${rel}：展示型列表不引用 idle_seconds`,
    usesIdle ? 'fail' : 'pass',
    '一旦出现按 idle_seconds 的丢弃，待确认报告会随陈旧阈值静默消失，且前端阈值与后端 SQL 两套判定互相干扰。')
}

/* ================= CLAIM-2：陈旧只标注、不过滤 ================= */
if (!hasIsStaleRun) {
  add('CLAIM-2', 'isStaleRun 已落地为标注谓词（仅 running 命中）', 'pending',
    '前端尚未出现 isStaleRun。标注语义须在实现时锁定 status==="running" 单一极性（与后端同极性）。')
}

for (const rel of RUN_LIST_CONSUMERS) {
  const text = srcText(rel)
  // 守卫：本文件不得出现任何陈旧标记的定义/引用。
  // 防的错：前端自造阈值过滤，与后端 SQL 双阈值判同一条 run。
  const staleRef = /\b(isStaleRun|STALE_RUN|staleAfter|stale_after|runStale)\b/.test(text)
  add('CLAIM-2', `${rel}：无陈旧判定引入`,
    staleRef ? 'fail' : 'pass',
    '后端 list_runs 的 SQL 是陈旧过滤的唯一出处；前端再加一遍会出现两套阈值对同一条 run 给出不同结论。')

  // 守卫：staleness 不得覆盖 awaiting_approval。
  // 防的错：awaiting_approval 的 updated_at 在报告产出时定格，套陈旧阈值等于定时删除该报告。
  const coversAwaiting = /isStaleRun[^\n]*awaiting_approval|awaiting_approval[^\n]*isStaleRun/i.test(text)
  add('CLAIM-2', `${rel}：staleness 不覆盖 awaiting_approval`,
    coversAwaiting ? 'fail' : 'pass',
    '两类事件成因不同（run 可能已死 vs 用户在思考），混写会诱导出一堆豁免分支。')
}

/* ---------- idle_seconds 阈值：未落地则「待验」，不记失败 ---------- */
add('CLAIM-2', 'idle_seconds 已贯通（前端类型 + 后端 _row_to_dict）',
  idleAvailable ? 'pass' : 'pending',
  idleAvailable
    ? '字段已贯通，陈旧阈值用例可实跑。'
    : `前端类型定义含该字段=${feIdle}；后端 _row_to_dict 返回含该字段=${beIdle}。`
      + '字段未落地 => 陈旧阈值用例当前无法实跑，报「待验」而非「不通过」。')

/* ---------- 输出 ---------- */
let last = ''
for (const r of results) {
  if (r.claim !== last) {
    console.log(`\n===== ${r.claim} =====`)
    last = r.claim
  }
  const mark = { pass: 'PASS   ', fail: 'FAIL   ', pending: 'PENDING' }[r.kind]
  console.log(`[${mark}] ${r.name}\n          防的错：${r.why}`)
}
const nFail = results.filter((r) => r.kind === 'fail').length
const nPending = results.filter((r) => r.kind === 'pending').length
console.log(`\n===== 汇总：共 ${results.length} 条｜通过 ${results.length - nFail - nPending}｜待验 ${nPending}｜失败 ${nFail} =====`)
process.exit(nFail > 0 ? 1 : 0)
