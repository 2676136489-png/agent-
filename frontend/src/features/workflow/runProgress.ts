/**
 * 进度百分比的唯一权威（S4 / §12.1）。
 *
 * 设计原则：**分母是推导出来的，不是写死的；100% 这一格 reserve 给终态。**
 *
 * ⚠️ 本文件的常数全部是「建模估计」，不是后端权威值。真正的保证是 0.95 钳制，不是这里的算术。
 * ⚠️ 上界是建模值，**不要拿它跟后端日志里的实际步数做断言** ——
 *    一旦写了 `expect(actualSteps).toBe(bound)` 这类断言，图结构一变就会假失败，
 *    而且失败信息会把人引向错误的方向。
 *
 * §12.2 封闭名单（唯一允许出现在进度公式里的标识符，已锁定值）：
 *   BASE_NODES           = 7   出处 app/graph/graph.py:80-86 的 7 个具名节点，不含 fail
 *   MAX_VERIFY_ATTEMPTS  = 2   出处 app/schemas/graph.py:11 / app/core/config.py:112
 *   RECOURSE_BLOCK       = 4   出处 app/graph/graph.py:95-112，一次回炉重跑 4 个节点
 *
 * ⚠️ 上述三个常量**不得带任何形式的默认值回落**（不写 `?? 4`、不写 `_FALLBACK`）。
 *    扫描失败时让扫描红着，就是「必须显式决策」这道闸门的设计意图。
 *    ⚠️ 这条规则只管常量，不要外扩到入参：`Number.isFinite(m) ? ... : 0` 与
 *       `Math.max(0, doneSteps)` 是**入参归一化 / 入参钳制**，不是常量回落。
 */

/** §12.2 封闭名单 ①：出处 `app/graph/graph.py:80-86` 的 7 个具名节点
 * （understand_task / plan / research / retrieve / analyze / verify / write），
 * **不含 `fail`**（`graph.py:87` 是显式失败终态，短路路径，不计入正常上界）。 */
export const BASE_NODES = 7

/** §12.2 封闭名单 ②：出处 `app/schemas/graph.py:11` 的
 * `max_verify_attempts: Field(default=2, ge=1, le=4)`，实际生效值来自
 * `app/core/config.py:112` 的 `graph_max_verify_attempts: int = 2`。
 * ⚠️ 镜像值：跟随后端默认值漂移，前端不拥有真相。吸收漂移的是 0.95 钳制，不是这个常量。 */
export const MAX_VERIFY_ATTEMPTS = 2

/** §12.2 封闭名单 ③（team-lead D4 批准）：出处 `app/graph/graph.py:95-112`，
 * 一次「验证回炉」会重跑 research → retrieve → analyze → verify 四个节点。
 * ⚠️ 这是回炉块的节点数，不是业务常量；图结构一变就失准（在回炉块里插一个节点，4 会静默变成错的）。 */
export const RECOURSE_BLOCK = 4

/** 运行中进度条的硬顶。终态才允许到 1。
 * ⚠️ `min(...)` 是**要求项不是保险丝**：后端默认值漂移时由它吸收，删掉它进度条就会假满格。 */
export const RUN_FILL_CEILING = 0.95

/**
 * 上界 = 7 固定节点 + (maxIterations − 1) 次 research 自环 + (MAX_VERIFY_ATTEMPTS − 1) 次回炉重跑块
 * 等价写法：maxIterations + 4 × MAX_VERIFY_ATTEMPTS + 2；默认配置 (3, 2) → 13。
 *
 * 图拓扑核对（`app/graph/graph.py:80-113`）：
 *   START → understand_task → plan → research ⇄{research 自环 | retrieve}
 *           retrieve → analyze → {verify | fail}；verify → {research 回炉 | write | fail}
 *   research 自环跑 maxIterations 次；verify 回炉跑 maxVerifyAttempts − 1 次。
 * §12.1b 已用 32 组配置（m ∈ [1,8] × v ∈ [1,4]）交叉验证。
 */
export function computeRunUpperBound(maxIterations: number): number {
  const m = Number.isFinite(maxIterations) ? Math.max(0, Math.trunc(maxIterations)) : 0
  const recourses = Math.max(0, MAX_VERIFY_ATTEMPTS - 1)
  return BASE_NODES + Math.max(0, m - 1) + recourses * RECOURSE_BLOCK
}

/**
 * fill = min( len(run.steps) / 上界, 0.95 )
 * - 第二个参数不是保险丝，是**要求项**：后端默认值漂移时由它吸收；
 * - 下界也钳到 0：负宽度在 CSS 里是非法值会被忽略，条会「停在上一帧」看起来像卡死。
 */
export function computeRunFill(doneSteps: number, maxIterations: number): number {
  const bound = computeRunUpperBound(maxIterations)
  if (bound <= 0) return RUN_FILL_CEILING
  return Math.min(Math.max(0, doneSteps) / bound, RUN_FILL_CEILING)
}

/** 终态才解锁的 100% —— 只在 run.status ∈ {completed, failed, cancelled} 时调用 */
export function computeRunFillForTerminal(): number {
  return 1
}
