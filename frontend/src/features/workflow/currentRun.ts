/**
 * 「当前这一次运行」的启动期快照（B3 / P1 根治）。
 *
 * 为什么需要它：进度条的分母依赖 `maxIterations`。而 `maxIterations` 是**滑杆 state**——
 * 用户随时能改。若进度条在渲染时直接读滑杆 state，就会出现：
 *
 *   1. 用户设 3 轮启动 → 跑到一半，把滑杆拖到 8 → **进度条瞬间倒退**（分母 13 变 18）；
 *   2. 用户设 8 轮启动 → 跑到一半，把滑杆拖回 1 → **进度条瞬间假满格**（分母 18 变 6）。
 *
 * 两者都是「拿当前的输入去解释过去的运行」，属于 [IC-1] 同族的单位混用。
 *
 * 根治办法：**启动那一刻把 `maxIterations` 快照下来，此后不再随滑杆变化。**
 * 进度条只读快照，滑杆只写 state，两者从此不相干。
 *
 * ⚠️ 三个不变量，改这个文件前先读：
 *   A. `maxIterations` 是**启动时的值**，写入后**不可变**（不是「跟随滑杆」，也不是「取最新值」）。
 *   B. 快照**只服务于进度条的分母**。它**不是**「这次运行的真实参数」的权威——
 *      真权威在后端（`run.max_iterations`）。这里存的是「我们发出去时用的那个值」，
 *      用途单一：让进度条在本次运行期间保持一把不变的尺子。
 *   C. 恢复历史运行时（从 RunHistory 点进来）**没有本地快照**（那时是别的会话、别的页面实例）。
 *      → 必须允许 `null`，并由消费方回落到一个**与后端一致的**保守值，而不是回落到滑杆 state。
 */

/** 一次运行的启动期快照。`maxIterations` 是不可变值（见不变量 A）。 */
export interface CurrentRun {
  threadId: string
  question: string
  startedAt: number
  phaseLabel: string
  /**
   * 启动时发出的 `max_iterations`。**此后不变**（不变量 A）。
   * ⚠️ 不要把它与「当前滑杆值」混用——那正是本文件要根治的缺陷。
   */
  maxIterations: number
}

/**
 * 后端默认 `max_iterations`（出处 `app/schemas/graph.py:10` 的
 * `max_iterations: int = Field(default=3, ge=1, le=8)`）。
 * ⚠️ 与前端滑杆 `<input type="range" min={1} max={8}>` 的上下界同源（ge=1 / le=8）。
 *
 * ⚠️ 这是**恢复历史运行时的回落值**，不是「常量回落」——`runProgress.ts` 里那条
 *    「不得带默认值回落」的规则管的是 §12.2 封闭名单三个常量，不是本文件。
 *    本文件是**数据缺失时的兜底**，性质是入参归一化。
 */
export const DEFAULT_MAX_ITERATIONS = 3

/**
 * 从后端返回的 `max_iterations` 归一出一个可用的分母入参。
 *
 * 为什么需要：`ResearchRun` 的 `max_iterations` 目前**不在类型里**
 * （`types/graph.ts` 的 `ResearchRun` 没有该字段），历史运行也拿不到本地快照。
 * 此时**绝不能回落到滑杆 state**（不变量 C）——那会让「看历史」和「改滑杆」意外耦合。
 *
 * @param value 后端可能返回的值；缺失/非法时回落 `DEFAULT_MAX_ITERATIONS`
 */
export function normalizeMaxIterations(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return DEFAULT_MAX_ITERATIONS
  const n = Math.trunc(value)
  // 后端契约是 ge=1；小于 1 说明数据坏了，回落到默认而不是钳成 1（钳成 1 会伪装成合法值）
  return n >= 1 ? n : DEFAULT_MAX_ITERATIONS
}
