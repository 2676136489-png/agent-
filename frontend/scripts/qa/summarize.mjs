/**
 * QA 汇总：读取四档探针 JSON，输出溢出/导航/首屏主操作结论表格。
 *
 * 陈旧数据保护：产物早于「改名落地时点」时判为 STALE-DATA，并【拒绝输出任何
 * 通过/失败结论】。理由见 rename-marker.mjs —— 拿改名前抓帧报出的「失败计数」
 * 会被误读成改名引入的缺陷，导向一次错误修复。
 */
import fs from 'node:fs'
import { RENAME_LANDED_AT, PRE_RENAME_LABEL } from './rename-marker.mjs'

const widths = [1440, 1024, 768, 375]
let fail = 0
const staleArtifacts = []

for (const w of widths) {
  const path = `scripts/qa/out/probe-${w}.json`
  if (!fs.existsSync(path)) {
    console.log(`[${w}] 缺少 ${path}`)
    continue
  }
  const raw = fs.readFileSync(path, 'utf8')

  /* ---- 陈旧数据闸门：早于改名落地的产物一律拒绝出结论 ---- */
  const mtimeMs = fs.statSync(path).mtimeMs
  const byTime = mtimeMs < RENAME_LANDED_AT
  // 第二重判据：产物内容里出现只有改名前才有的旧文案，是更硬的证据
  const byContent = raw.includes(PRE_RENAME_LABEL)
  if (byTime || byContent) {
    staleArtifacts.push({ w, path, mtimeMs, byTime, byContent })
    console.log(`[${w}] STALE-DATA —— 拒绝出结论`)
    console.log(
      `      时间：抓帧 ${new Date(mtimeMs).toISOString()} < 改名落地 ${new Date(RENAME_LANDED_AT).toISOString()}${byTime ? '（早于改名）' : ''}`,
    )
    if (byContent) console.log(`      内容：含改名前旧文案「${PRE_RENAME_LABEL}」，可确定为历史快照`)
    continue
  }

  let data
  try {
    data = JSON.parse(raw)
  } catch (e) {
    console.log(`[${w}] JSON 解析失败: ${e.message}\n${raw.slice(0, 300)}`)
    continue
  }
  console.log(`\n========== viewport ${w} (innerW=${data.viewport.w}) ==========`)
  console.log(
    `导航: menuVisible=${data.navInit.menuVisible}/${data.navInit.menuTotal} core=${data.navInit.coreVisible} nonCore=${data.navInit.nonCoreVisible} 更多按钮=${data.navInit.moreBtnVisible} 汉堡=${data.navInit.toggleVisible} 抽屉在DOM=${data.navInit.drawerInDom}`,
  )
  console.log(`       nav-inner scrollW=${data.navInit.navInnerScrollW} / w=${data.navInit.navInnerW}`)
  for (const p of data.pages) {
    const overflow = p.overflowPx > 0 ? `❌溢出+${p.overflowPx}px` : 'ok'
    if (p.overflowPx > 0) fail++
    let prim = '—'
    if (p.primary && p.primary.primaryButton) {
      const pb = p.primary.primaryButton
      prim = `主按钮"${pb.text}" top=${pb.top} 首屏=${pb.firstScreen ? '✓' : '✗'} | 入口卡首屏 ${p.primary.entryCardsFirstScreen}/${p.primary.entryCardCount} | 角标=${p.primary.primaryCardBadge}`
      if (!pb.firstScreen) fail++
    } else if (p.primary) {
      prim = `"${p.primary.text}" top=${p.primary.top} 首屏=${p.primary.firstScreen ? '✓' : '✗'}`
      if (!p.primary.firstScreen) fail++
    }
    console.log(`  ${p.page.padEnd(6)} scrollW=${String(p.scrollW).padStart(4)} innerW=${p.innerW} ${overflow.padEnd(10)} | ${prim}`)
  }
}
if (staleArtifacts.length > 0) {
  console.log('\n' + '='.repeat(72))
  console.log('拒绝给出结论：存在早于改名落地的陈旧产物。')
  for (const s of staleArtifacts) console.log(`  - ${s.path}`)
  console.log('')
  console.log('上面任何逐页数字（含「溢出+NNNpx」）描述的都是【改名前】的布局，')
  console.log('不能读作改名引入的缺陷，也不能用作本轮验收依据。')
  console.log('要得到当前结论，请重跑 scripts/qa/viewport-probe.js 并重新落盘为 out/probe-<w>.json。')
  console.log('='.repeat(72))
  process.exitCode = 2
} else {
  console.log(`\n===== 溢出/首屏失败计数: ${fail} =====`)
}
