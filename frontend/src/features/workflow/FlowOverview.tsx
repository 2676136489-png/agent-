/** 研究工作流的流程说明：用卡片逐段解释每个阶段在做什么。
 *  抽成独立组件，避免把所有展示逻辑堆在 ResearchWorkflow 里。 */
interface FlowStep {
  no: number
  name: string
  desc: string
  detail: string
  tag?: string
}

const STEPS: FlowStep[] = [
  {
    no: 1,
    name: '理解任务',
    desc: '解析你提出的问题，明确研究目标、需要回答的关键子问题，以及研究的边界范围。',
    detail: '模型会输出结构化的「任务理解」：研究目标、关键子问题、研究范围与排除项。这一步保证后续检索不会跑题。',
  },
  {
    no: 2,
    name: '制定计划',
    desc: '把目标拆成若干可执行的研究步骤，形成一份可逐步追踪的研究计划。',
    detail: '将复杂问题拆成多步可执行计划，每步都有明确要检索的问题和预期证据类型，方便后续按图索骥。',
  },
  {
    no: 3,
    name: '研究决策',
    desc: '由模型判断下一步该调用哪个工具，并决定证据是否已经足够、是否还需要继续检索。',
    detail: '智能体在每次循环中评估证据充分度：足够则进入分析，不足则继续检索；避免无效搜索，也防止遗漏关键信息。',
    tag: '可循环',
  },
  {
    no: 4,
    name: '资料获取',
    desc: '调用检索、网页抓取等工具获取证据，并去重后累加到任务的上下文里。',
    detail: '通过 Tavily 联网搜索 + 网页抓取获取原始资料，对结果去重、摘要，并写入上下文供后续节点使用。',
    tag: '与研究决策循环',
  },
  {
    no: 5,
    name: '分析',
    desc: '对收集到的证据做归纳，提炼出核心结论，并标记仍然存在的证据缺口。',
    detail: '基于已有证据进行归纳、对比和推理，输出核心发现，同时诚实地标注还有哪些问题尚未被证据充分支撑。',
  },
  {
    no: 6,
    name: '验证',
    desc: '核对现有证据是否足以支撑结论，给出「通过 / 需要补充」的判定。',
    detail: '在生成最终报告前做一轮事实校验：确认每个关键结论都有对应证据；不充分的结论会打回补充检索。',
  },
  {
    no: 7,
    name: '撰写报告',
    desc: '把研究结果汇总成结构化的研究报告——但在落笔之前会先暂停，等待你确认。',
    detail: '最终输出包含标题、摘要、分节正文和局限说明。报告生成前会主动中断，等待你确认或补充要求。',
    tag: '人工确认闸门',
  },
]

export function FlowOverview() {
  return (
    <section className="flow-wrap">
      <h3 className="plan__heading">工作流程</h3>
      <p className="lead">
        整条研究链路由 LangGraph 驱动：先「理解」，再「计划」，随后在「研究决策 ⇄ 资料获取」之间反复循环以补充证据，
        经过「分析」与「验证」后，在生成最终报告之前会主动中断，等待你的人工确认（human-in-the-loop）。
      </p>
      <div className="flow">
        {STEPS.map((s) => (
          <div key={s.no} className="flow__step">
            <div className="flow__head">
              <span className="flow__no">{s.no}</span>
              <span className="flow__name">{s.name}</span>
            </div>
            <p className="flow__desc">{s.desc}</p>
            <p className="flow__detail">{s.detail}</p>
            {s.tag && <span className="flow__tag">{s.tag}</span>}
          </div>
        ))}
      </div>
    </section>
  )
}
