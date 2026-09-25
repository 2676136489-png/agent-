# AI Research Workspace — 全模块质量排查报告

**排查日期**：2026-09-24　**范围**：前端 / 后端 / Agent（LangGraph 工作流 + Phase3 手写循环）
**方式**：代码通读 + 实际运行验证（ruff / pytest / uvicorn 实跑 / curl 打真实接口 / Ollama + Tavily 真实调用 / Mock 模式状态机脚本）
**约束**：只排查现有代码，未新增业务功能；临时验证脚本已在结束后删除。

---

## 0. 验证基线

| 项 | 命令 | 结果 |
|---|---|---|
| 后端静态检查 | `ruff check app tests` | ❌ **10 errors**（README 声称 "All checks passed"，已不符） |
| 后端单元测试 | `pytest -q` | ✅ **61 passed** |
| 前端类型检查 | `tsc --noEmit` | ✅ 通过 |
| 前端生产构建 | `vite build` | ✅ 通过（310 modules，361.74 kB / gzip 115.55 kB） |
| 后端服务启动 | uvicorn :8000 | ✅ 正常，日志中 **0 条未捕获异常** |
| 完整研究链路 | 真实 LLM + 真实联网 | ✅ 跑通（见 §3） |

**端到端实测记录**（真实 qwen3:8b + Tavily）：
- `POST /api/graph/research` → `awaiting_approval`，耗时 85.9s，轨迹 `understand_task → plan → research×2 → retrieve → analyze → verify`，3 次 `search_web` 全部成功，9072 tokens
- `POST .../resume {approved:true}` → `completed`，报告含 4 个 sections + 3 条 limitations
- `POST .../resume {approved:false}` → `cancelled`
- `POST /api/agent/run` → `final_answer`，54.2s，1 次工具调用
- 知识库上传（.md）/ 类型拦截（.exe → 415）/ 语义检索 → 全部正常
- SSE：历史事件回放正常、终态关闭正常、空 thread 心跳正常（15s 间隔）

---

## 1. 后端（FastAPI / 基础设施 / 工具层）

| # | 文件/模块 | 问题描述 | 严重度 | 复现 / 验证方式 | 修复建议 |
|---|---|---|---|---|---|
| B1 | `app/tools/calculate.py:57-62` | 幂运算指数上限只检查「右操作数为常量」这一层，**嵌套幂可绕过**：`9**9**9` 的外层右操作数是 `BinOp` 不是 `Constant`，校验直接放行。求值耗时 >25s（子进程 timeout 退出码 124）；`safe_eval` 是同步 CPU 计算，`BaseTool.execute` 的 `asyncio.wait_for(timeout=2.0)` **无法中断**它 → 整个 uvicorn 事件循环被卡死，所有请求与 SSE 心跳全部冻结 | **阻塞** | 脚本：`safe_eval("9**9**9")` 25s 未完成；`safe_eval("2**999999999")` 被正确拦截 | 在 AST 阶段递归估算幂运算结果的量级并拒绝（如估算 log10 > 1e6 直接 ValueError）；或把 `_run` 丢进 `asyncio.to_thread` / 进程池；同时对结果做位数上限校验 |
| B2 | `app/api/routes/knowledge.py:44-50` | **先 `await file.read()` 再校验大小**。`UPLOAD_MAX_BYTES=10MB` 形同虚设，2GB 文件会先被完整读进内存才返回 413 | **严重** | 代码 L44 读取、L45 才判断 | 先读 `file.size` / `Content-Length` 拦截；或分块读取并在超限时立即中断 |
| B3 | `app/graph/service.py:83-104,132-155` | ① 进程重启后（`InMemorySaver` 空）从 DB 回落时，`_to_response` 读的是 `state["status"]`（恒为 `running`），**`awaiting_approval` 被显示成 `running`**；② 此时 `resume` 会执行 `graph.ainvoke(None, config)` 抛 `EmptyInputError: Received no input for __start__`，被全局兜底 handler 吞成 **500 internal server error** | **严重** | Mock 脚本清空 checkpointer 后实测：`status=running`（应为 awaiting_approval）；再 resume → `EmptyInputError` | 落库时把派生状态一并写入 `state["status"]`；`resume_research` 开头先 `aget_state` 校验 checkpoint 存在，不存在则抛 `AppError(409, "该运行已不可恢复（进程已重启）")` |
| B4 | `app/api/routes/graph.py:48-53` | `resume_research_run` **只拦截 `completed`**，`cancelled` / `failed` 的运行可被再次批准并生成报告，人工拒绝不是终态 | **严重** | Mock 脚本：`start → resume(false) → cancelled → resume(true) → completed + 报告`；真实环境 uvicorn.log 22:50:09 取消、22:50:16 被批准成功 | 终态集合 `{completed, cancelled, failed}` 一律拒绝 resume，返回 409 |
| B5 | `app/llm/client.py:129-137` | 对**所有** OpenAI 兼容厂商无条件下发 `extra_body={"keep_alive":0,"think":False}`。① 对 OpenAI/DeepSeek/通义等非 Ollama 厂商是未知字段，有 400 风险；② 实测 Ollama qwen3:8b 带 `think:false` **仍返回 791 token 的 `reasoning`**，说明并未真正关闭思考，注释与事实不符 | **严重** | 直连 Ollama 对比三种参数，`reasoning_len` 分别 1236 / 791 / 848，从未为 0 | 按 `llm_base_url` 是否 Ollama 决定是否下发；改用 `chat_template_kwargs={"enable_thinking": False}` 或 Ollama 原生 `/api/chat` |
| B6 | `.env: LLM_MAX_TOKENS=2000` + `app/llm/client.py` | qwen3 的思考内容占用同一份 `max_tokens` 预算，长 prompt 下正文被截断成 `{\n\n}` → schema 校验失败 → **502** | **严重** | `POST /api/research/plan` 实测返回 `模型输出不符合 schema：goal: Field required...`；直连 Ollama 拿到 `content="{\n\n}"` | max_tokens 提到 ≥4096；或真正关闭 thinking（见 B5） |
| B7 | `app/services/planning_service.py:36-44` | `tenacity` 只重试传输层 LLMError，`parse_structured_payload` 抛出的 `kind="parse"` **不会重试**，一次解析失败直接 502 | **严重** | 与 B6 同一次调用 | 参照 `plan_node` 的 repair 写法，对 parse 类错误重试 1 次并把上一次原始输出回灌给模型 |
| B8 | `app/graph/schemas.py:19-35` | `_coerce_str_list` 对非字符串元素直接 `str(item)`，模型返回对象数组时被转成 **Python repr** 渲染给用户 | 一般 | 真实运行 `analysis.findings` 为 `"{'technical_requirement': '熟悉主流AI Agent框架和工具链', 'evidence': '...'}"` | dict 元素应 `json.dumps(ensure_ascii=False)` 或提取可读字段；或直接判定为 parse 错误触发重试 |
| B9 | `app/tools/fetch_webpage.py:57-78` | ① `response.text` 一次性读入全部响应体，**无大小上限**（大文件/恶意 URL → 内存打满）；② `assert_public_http_url` 先解析 DNS、再由 httpx 重新解析，存在 **DNS rebinding TOCTOU** 窗口；③ `socket.getaddrinfo` 是阻塞调用，卡在 async 事件循环里 | 一般 | 代码 L61 校验 / L64-68 请求分离 | 用 `client.stream()` 分块读取并在超限时中断；校验后绑定校验得到的 IP 发起请求；DNS 解析改 `loop.getaddrinfo` |
| B10 | `app/events/store.py:34` `app/graph/run_store.py:42` `app/rag/store.py:87` | 三处 SQLite 连接均 `check_same_thread=False` 且**无锁**、未开 WAL、未注册关闭钩子 | 一般 | 代码直读 | 加 `threading.Lock` 或改 `aiosqlite`；`PRAGMA journal_mode=WAL`；在 FastAPI shutdown 事件里 close |
| B11 | `app/api/routes/graph.py:79-83` | `list_research_runs` 未把 `limit` 暴露给调用方（写死 20），前端「效果评估」的"总运行次数"因此最多统计 20 条 | 建议 | 代码 L83 `list_runs(status=status)` | 增加 `limit: int = Query(20, ge=1, le=200)` |
| B12 | `app/core/errors.py:69-75` `app/core/security.py:104-117` | `AppError` 只 `logger.warning`；提示注入过滤命中时**无任何日志**，无法审计"是否被攻击过" | 建议 | 代码直读 | 注入过滤命中时 `logger.warning("prompt injection filtered", extra={"thread_id":...})` |
| B13 | `app/graph/nodes.py:23,140` `app/graph/schemas.py:3` `app/tools/search_provider.py:21` `app/schemas/research.py:19` 等 | **ruff 10 处**：`F841`（`last_err` 赋值未用）、`F401` ×2、6 处 `E501`、`I001`（import 未排序）。README §5 承诺 "All checks passed" 已失效 | 一般 | `ruff check app tests --output-format=concise` | `ruff check --fix` + 手动换行；把 ruff 加进 CI 门禁 |
| B14 | `app/schemas/graph.py:12` | `thread_id` 无格式校验且当前**无任何鉴权**，调用方可传入他人 thread_id 覆盖/劫持运行 | 一般 | 代码直读 | 加 `pattern=r"^thread_[a-f0-9]{12}$"` 或改为服务端生成；至少加一层 API Key |
| B15 | `app/graph/nodes.py:54-62` `app/graph/nodes.py:333-336` | ① 每个节点都重新 `build_default_registry()`（重建全部工具实例）；② `retrieve_node` 的 `ToolContext` 未传 `allowed_domains`，域名白名单在该节点失效 | 建议 | 代码直读 | registry 改为 `lru_cache` 单例；`retrieve_node` 补 `allowed_domains=settings.fetch_allowed_domains_list` |

---

## 2. Agent（LangGraph 工作流 / 提示词 / 工具调用 / 异常兜底）

| # | 文件/模块 | 问题描述 | 严重度 | 复现 / 验证方式 | 修复建议 |
|---|---|---|---|---|---|
| A1 | `app/graph/prompts.py:24-32` vs `app/schemas/research.py:14-19` | **Prompt 与 Schema 字段名不一致**：prompt 要求 steps 含 `name` / `description`，而 `PlanStep` 的字段是 `index` / `title` / `instruction`。真实模型照 prompt 输出后，`ResearchPlan._normalize_steps` 取不到字段，全部退化成占位值 | **阻塞** | 真实运行返回：`steps: [{"index":1,"title":"步骤 1","instruction":"模型未给出具体说明"}, … ×6]` —— **6 步计划 100% 是废数据** | prompt 改为 `title` / `instruction`；并像 `app/llm/prompts.py:51` 那样直接注入 `ResearchPlan.model_json_schema()`，从根上消除漂移 |
| A2 | `app/graph/prompts.py` 全部 7 个模板 | 所有节点 prompt **只有一条 `user` 消息，没有 `system` 消息**。`app/core/security.py` 文档宣称的"system prompt 声明 + schema 校验"结构性防御**并未实现**；防注入规则与用户问题挤在同一条 user 消息里，模型服从度显著更低（`app/llm/prompts.py` 用的是对的，两处不一致） | **严重** | 对比 `llm/prompts.py:43-58`（有 system）与 `graph/prompts.py:99-168`（无 system） | 把各节点的规则段拆到 `ChatMessage(role="system", ...)`，只把数据留在 user |
| A3 | `app/graph/nodes.py:163-176` | **兜底计划本身是坏的**：`_fallback_plan` 用 `PlanStep(name=..., description=...)`，字段名同样错误；且 `ResearchPlan._normalize_steps` 只接受 `dict`，`PlanStep` 对象被整批过滤 → 兜底产出 **0 步**计划，与注释"保证后续流程不中断"完全相反 | **严重** | 实测 `_fallback_plan(...)` → `steps 数量: 0` | 改用 `{"index":i,"title":...,"instruction":...}` dict 构造；补一条单测断言 `len(steps) > 0` |
| A4 | `app/graph/nodes.py:126-153` | `plan_node` 的重试循环里 `last_err` 赋值后从未使用（ruff F841），两次重试之间没有退避、也没有把上一次的错误回灌给模型，repair 提示词拿不到失败原因 | 一般 | 代码 L139-140 | 把 `last_err` 拼进 `prompts.plan_messages(..., repair_hint=last_err)`，并在两次尝试间加短暂退避 |
| A5 | `app/graph/graph.py:53-56` | `route_after_analyze` 在 `state["error"]` 时直接跳 `write`，会在 **`analysis` 为空、`evidence` 可能为空**的情况下写报告，产出空壳报告而不是 `failed` | 一般 | 代码直读 + `analyze` 失败路径推演 | 增加独立的失败终态节点；或在 write 前判断 `analysis` 为空则直接置 `status=failed` |
| A6 | `app/graph/graph.py:87-91` | `add_conditional_edges("research", …, {"research","retrieve","analyze"})` 声明了 `analyze` 分支，但 `route_after_research` **永不返回它** | 建议 | 代码直读 | 删除该死分支，避免误导后来者 |
| A7 | `app/llm/client.py:206-212,326-338` | Mock 链路脆弱：`_count_mentioned_evidence` 靠正则从 prompt 文本里抓"已经有 N 条证据"来判断循环收敛，**prompt 一改 Mock 就失效**；且 `MockLLMClient` 不支持的 purpose 直接抛错（这点是合理设计，但新增 LLM 调用点时必须同步 `_MOCK_PURPOSES`，无测试保护） | 一般 | 代码直读 | 把证据条数作为显式参数传入而不是靠正则；补一条"每个 purpose 都有 Mock fixture"的参数化测试 |
| A8 | `app/graph/nodes.py:287-290` | 只有 `search_web` / `fetch_webpage` 的结果被 `wrap_untrusted_block` 包裹；`search_knowledge_base` 返回的本地文档内容未包裹。另外 `action.args` 在校验前就被原样写进 `tool_calls` 并落库 | 建议 | 代码直读 | 本地文档同样走包裹（成本极低）；`args` 落库前做一次 schema 校验或裁剪 |

---

## 3. 前端（React + Vite）

| # | 文件/模块 | 问题描述 | 严重度 | 复现 / 验证方式 | 修复建议 |
|---|---|---|---|---|---|
| F1 | `src/api/client.ts:37-45` | 注释声称"AbortController 让请求可以被取消（组件卸载时）"，**实际代码中没有任何 AbortController**；`apiGet/apiPost` 的 `signal` 参数全项目无人传入。启动工作流是一次 1~2 分钟的长请求，切页后仍会 setState 且无法取消 | **严重** | 注释与代码不符；全项目 grep 无 `AbortController` | 在 `request()` 内部合并 `AbortSignal.timeout(ms)`；组件内用 `useRef` 持有 controller 并在 `useEffect` cleanup 中 abort |
| F2 | `src/features/workflow/ResearchWorkflow.tsx:290-293` | `handleRefresh` **完全没有 try/catch**，后端 500 或网络断开时产生未捕获的 Promise rejection，UI 零反馈（用户点了"刷新状态"什么都不发生） | **严重** | 代码直读（无 try/catch，未 setError） | 包 try/catch 并 `setError`，与 `handleStart` 保持一致 |
| F3 | `src/features/workflow/RunHistory.tsx:47-54` `src/features/knowledge/KnowledgeBase.tsx:19-21,122-129` | `refresh()` / `handleSearch()` 只有 `try/finally` **没有 catch**，请求失败被静默吞掉，界面显示"还没有运行记录"/"检索中…结束但无结果"，用户以为真的没数据 | 一般 | 代码直读 | 补 catch + error state；至少 `console.error` 之外给用户可见提示 |
| F4 | `src/features/agent/AgentRunner.tsx:13-25` | `FINISH_REASON_LABEL` / `FINISH_VARIANT` 的键是 `completed / max_steps / tool_error / cancelled`，而后端 `AgentRunResult.finished_reason` 实际值是 **`final_answer / max_steps_reached / timeout / llm_error`** —— 键名 100% 不匹配，界面永远显示英文原始值 + 中性样式 | 一般 | 实测 `/api/agent/run` 返回 `finished_reason: "final_answer"`；前端字典无此键 | 按后端 `app/agent/schemas.py:75` 注释的实际枚举重写字典，并加兜底显示 |
| F5 | `src/features/workflow/useRunEvents.ts:46` + `ResearchWorkflow.tsx:353` | `useEffect(() => close, [close])` 在**组件卸载时关闭 SSE**，而 `ResearchWorkflow.tsx` 的文案明确写着"工作流在后台持续运行并实时推送事件，**你可切到其他模块同步查看，进度不会中断**" —— 一切换导航就断流，回来后只剩手动刷新，与产品承诺直接矛盾 | **严重** | 代码直读 + 文案对照 | 把 EventSource 提升到 App 级/全局 store（或模块级单例），组件卸载不关闭；或修正文案 |
| F6 | `src/features/evaluation/Evaluation.tsx:49-56` | 统计基于 `listRuns()`，而后端硬编码 `limit=20`（见 B11），"总运行次数 / 已完成 / 失败"等指标**最多覆盖 20 条**，指标失真 | 建议 | 后端 `list_runs(limit=20)` | 配合 B11 暴露 limit，或后端单独提供聚合接口 |
| F7 | `src/api/graph.ts:35-38` `src/api/client.ts:95-110` | ① `?status=${status}` 未 `encodeURIComponent`；② `apiUpload` 无 signal、且非 JSON 响应会抛原始 `SyntaxError`（不是 `ApiClientError`），调用方 catch 到的是未知类型 | 建议 | 代码直读 | 用 `encodeURIComponent`；`apiUpload` 复用统一的 `request()` 错误分支 |
| F8 | `src/features/reports/Reports.tsx:8-14` `RunHistory.tsx:12-18` | `STATUS_LABEL[run.status]` 用 `Record<RunStatus, string>` 索引，后端将来新增状态时会渲染 `undefined` | 建议 | 类型直读 | 加 `?? run.status` 兜底 |
| F9 | `src/components/Markdown.tsx` | **已验证安全**：`react-markdown` 未启用 `rehype-raw`，默认 `urlTransform` 会过滤 `javascript:` 等危险协议，报告内容（模型可产出任意文本）不会造成 XSS | 通过 | 组件仅挂载 `remark-gfm` | 保持现状；若将来加 `rehype-raw` 必须同步引入 `rehype-sanitize` |

---

## 4. 配置与依赖

| # | 项 | 结论 |
|---|---|---|
| C1 | `.env` 是否入库 | ✅ **安全**：`.gitignore:20` 已忽略 `.env`，`git ls-files` 确认未跟踪，Tavily / LLM Key 无泄露风险 |
| C2 | `httpx2` 依赖 | ✅ **安全**：`httpx2 2.13.1` 来自 pydantic/Tom Christie，是 `openai 3.19.0` 与 `langsmith` 的合法依赖，非投毒包 |
| C3 | `EMBEDDING_DIMENSION=256` vs nomic-embed-text 实际 768 | 建议：该值仅在 hash 兜底模式生效，真实 embedding 以模型返回为准，无实际影响，但注释容易误导，建议在 `.env` 注明 |
| C4 | `langchain-core` 未声明 | 一般：`app/graph/nodes.py:18` 直接 `from langchain_core.runnables import RunnableConfig`，但 `pyproject.toml` 只声明了 `langgraph`，属于**未声明的传递依赖**，langgraph 升级可能打破导入 → 显式加入 dependencies |
| C5 | `pyproject.toml` uv 源 | 建议：硬编码清华 PyPI 镜像，团队/跨区协作时需注明 |

---

## 5. 按优先级排序的问题汇总

### P0 — 阻塞（必须立刻修，否则核心产出不可用）
1. **A1** 计划节点 Prompt 与 `PlanStep` 字段不一致 → 研究计划 100% 退化为占位文案（`app/graph/prompts.py`）

### P1 — 严重（会造成服务不可用、状态错乱或安全/资金风险）
2. **B1** 嵌套幂绕过指数上限 → CPU DoS 冻结整个服务（`app/tools/calculate.py`）
3. **B3** 重启后状态失真 + `resume` 抛 `EmptyInputError` → 500（`app/graph/service.py`）
4. **B4** 已取消的运行可被重新批准并出报告（`app/api/routes/graph.py`）
5. **A3** `_fallback_plan` 产出 0 步，兜底机制自身失效（`app/graph/nodes.py`）
6. **B6 + B7** `max_tokens` 撞上思考模式 → 空 JSON → 502，且解析失败无重试（`.env` + `app/services/planning_service.py`）
7. **B2** 上传先读全文再校验大小，10MB 上限形同虚设（`app/api/routes/knowledge.py`）
8. **A2** 7 个图节点 prompt 全部缺少 system 消息，防注入结构性防御未落地（`app/graph/prompts.py`）
9. **B5** 无条件下发 `extra_body`，`think:false` 实测无效且对非 Ollama 厂商有 400 风险（`app/llm/client.py`）
10. **F2** `handleRefresh` 无 try/catch，错误零反馈（`ResearchWorkflow.tsx`）
11. **F1** 长请求不可取消，注释与实现不符（`src/api/client.ts`）
12. **F5** 切页即断 SSE，与页面"进度不会中断"承诺矛盾（`useRunEvents.ts`）

### P2 — 一般（影响数据质量、可维护性与健壮性）
13. **B8** `_coerce_str_list` 把对象转成 Python repr 渲染给用户
14. **B9** 网页抓取无响应体上限 + SSRF 的 DNS rebinding 窗口 + 阻塞式 DNS
15. **B10** 三处 SQLite 无锁、无 WAL、无关闭
16. **B13** ruff 10 处未修（README 承诺已失效）
17. **B14** `thread_id` 无校验、全站无鉴权
18. **A4** plan 重试未带回错误原因
19. **A5** 分析失败仍会写空壳报告
20. **A7** Mock 依赖正则抓 prompt 文本，脆弱
21. **F3** 三处请求无 catch，错误静默吞掉
22. **F4** Agent 完成原因字典键名与后端完全不匹配
23. **C4** `langchain-core` 属未声明的传递依赖

### P3 — 建议（体验与工程整洁度）
24. **B11** / **F6** `/api/graph/runs` 未暴露 limit → 评估页统计失真
25. **B12** 提示注入过滤无日志，无法审计
26. **B15** 每节点重建工具注册表；`retrieve_node` 未传域名白名单
27. **A6** `route_after_research` 存在永不命中的死分支
28. **A8** 知识库内容未做不可信包裹；`args` 未校验即落库
29. **F7** 查询串未编码；`apiUpload` 错误类型不统一
30. **F8** 状态字典缺兜底
31. **C3** / **C5** 配置注释与镜像源的说明

---

## 6. 结论：当前项目能否正常运行？

**能正常运行**，但存在一个阻塞级的质量缺陷和若干严重级隐患。

- ✅ **能跑通**：后端启动无异常，`pytest` 61 项全绿，前端类型检查与生产构建均通过；完整研究链路（理解 → 计划 → 研究循环 → 检索 → 分析 → 验证 → 人工中断 → 批准 → 报告）在**真实 Ollama + 真实 Tavily 联网**下实测跑通并产出结构化报告；拒绝路径、SSE 回放与心跳、知识库上传/检索、Phase3 手写 Agent 循环均实测可用。
- ⚠️ **但产出质量不达标**：P0 的 A1 让"研究计划"这一核心产物 100% 是占位文案；`_fallback_plan`（A3）兜底同样失效。也就是说——**流程是通的，计划是废的**。
- ⚠️ **有可致服务不可用的风险点**：B1（一次恶意/异常表达式即可冻结整个服务）、B3（进程重启后恢复必 500）、B6/B7（本地模型下 `/api/research/plan` 有概率直接 502）。
- ⚠️ **状态机存在漏洞**：B4 让"人工拒绝"不是终态，可被二次批准复活。
- ✅ **未发现密钥泄露**（`.env` 已正确忽略），未发现 XSS（react-markdown 默认安全），未发现 SQL 注入（全部参数绑定）。

**建议修复顺序**：A1 → B1 → B3/B4 → A3 → B6/B7 → B2 → F1/F2/F5 → 其余 P2/P3。修完 A1 与 B1 后，项目即达到"可演示、可交付"水平。

---

## 7. 修复记录（同日晚，全部已修复并验证）

修复原则：**只修现有代码，不新增业务功能**。以下每条都跑了对应验证。

### 已修复并验证通过

| # | 修复内容 | 验证结果 |
|---|---|---|
| **A1** | `app/graph/prompts.py` 全部重写：7 个节点改为 system(规则+JSON Schema) / user(数据) 两段式；plan 的 steps 字段名改为 `title`/`instruction`；schema 通过 `schema_for_prompt()` 注入（剥掉顶层 title/description 元数据） | ✅ 真实运行：4 步计划全部是真实标题+说明（修复前是「步骤 N / 模型未给出具体说明」） |
| **A2** | 同上，system 消息承载安全规则与输出契约 | ✅ 消息角色实测为 `['system','user']` |
| **A3** | `_fallback_plan` 改用 dict 构造 steps | ✅ 从「0 步」变为「3 步」，每步有 title/instruction |
| **A4** | `plan_node` 把 `last_err` 回灌进 repair 提示词，并加 WARNING 日志 | ✅ 代码路径验证 |
| **A5** | 新增 `fail_node` 显式失败终态，`route_after_analyze/verify` 在 error 时走它 | ✅ 图编译通过，61 测试全绿 |
| **A6** | 删除 `route_after_research` 永不命中的 `analyze` 分支 | ✅ |
| **A7** | `_count_mentioned_evidence` 优先读 `metadata["evidence_count"]`，正则仅作兜底；`_ask()` 支持传 metadata | ✅ Mock 全链路仍跑通 |
| **A8** | 改为「只信任 calculate」白名单，其余工具输出一律 `wrap_untrusted_block`；新增 `_safe_args()` 规范化落库参数 | ✅ |
| **B1** | `safe_eval` 新增 `_const_eval()` 递归估算幂指数 + 结果位数上限 | ✅ `9**9**9` / `9**9**9**9` / `2**999999999` 全部 0.000s 拦截；`(1200+380)*0.15`、`2**10`、`9**100` 正常 |
| **B2** | 上传先按声明大小拦截，再分块 `_read_limited()` 边读边校验 | ✅ 上传/检索正常 |
| **B3** | `_snapshot` 落库时写入派生 `status`；`_to_response` 优先信任已落库状态；`resume_research` 先校验 checkpoint | ✅ 重启模拟：`status=awaiting_approval`（修复前 running）；resume 返回明确 409（修复前 500 EmptyInputError） |
| **B4** | service 层 + 路由层双重拦截 `TERMINAL_STATUSES` | ✅ 取消后再批准 → 409「这次运行已结束（cancelled）」；完成后再 resume → 409 |
| **B5** | 新增 `_is_ollama()`，`keep_alive`/`think` 只对 Ollama 下发（LLM 与 embedding 两处） | ✅ 直连验证 Ollama 仍走扩展字段 |
| **B6** | `.env` 的 `LLM_MAX_TOKENS` 2000 → 4096；`complete_structured` 在 `finish_reason=="length"` 时抛出可操作的 `truncated` 错误 | ✅ `/api/research/plan` 连续返回 200 |
| **B7** | `create_research_plan` 对 `kind=="parse"` 重试一次并回灌失败原因；`llm/prompts.py` 支持 `repair_hint` | ✅ |
| **B8** | `_coerce_str_list` 新增 `_stringify()`：dict → "键: 值" 可读形式，不再产出 Python repr | ✅ 实测 findings 为 6 条干净字符串 |
| **B9** | `fetch_webpage` 改为 `client.stream()` + `_read_limited()`（2MB 上限） | ✅ |
| **B10** | 三个 SQLite store 加 `threading.Lock` + WAL + `close()`；`main.py` 用 lifespan 在关闭时释放 | ✅ 无 DeprecationWarning |
| **B11** | `/api/graph/runs` 暴露 `limit`（默认 50，上限 500） | ✅ `?limit=3` 返回 3 条 |
| **B12** | 提示注入过滤命中时 `logger.warning` 记录 | ✅ |
| **B13** | ruff 10 处全部修复 | ✅ **All checks passed!** |
| **B14** | `thread_id` 加 `pattern=^thread_[0-9a-f]{12}$`；前端 `newThreadId()` 降级路径改为生成十六进制 | ✅ 非法 id → 422 |
| **B15** | `build_default_registry` 改 `lru_cache` 单例；`retrieve_node` 补 `allowed_domains` | ✅ |
| **F1** | `client.ts` 新增 `withTimeout()`：合并外部 signal + 300s 超时；网络错误/非 JSON 统一包成 `ApiClientError` | ✅ |
| **F2** | `handleRefresh` 补 try/catch + setError | ✅ |
| **F3** | `RunHistory.refresh`、`KnowledgeBase.refresh`、`SearchBox.handleSearch` 全部补 catch + 可见错误提示 | ✅ |
| **F4** | `FINISH_REASON_LABEL/FINISH_VARIANT` 改为后端真实值 `final_answer/max_steps_reached/timeout/llm_error` | ✅ 实测 `finished_reason=final_answer` 现可正确映射 |
| **F5** | `useRunEvents` 重构为模块级连接管理器：组件只注册监听器，卸载不关连接，切页回来进度连续 | ✅ |
| **F6** | `listRuns` 支持 limit；`Evaluation` 显式请求 500 条 | ✅ |
| **F7** | 用 `URLSearchParams` 编码查询串；`apiUpload` 复用统一错误分支 + 超时 | ✅ |
| **F8** | 状态字典类型放宽为 `Record<string, …>` 并加 `?? run.status` 兜底 | ✅ |
| **新增（修复过程中发现）** | 模型会把输出包成 `{"description": {...}}`（JSON Schema 的顶层 description 被误当字段）→ `schema_for_prompt()` 剥离元数据 + `parse_structured_payload` 增加单层解包兜底 | ✅ 修复前 findings 为空数组，修复后为 6 条真实结论 |

### 回归结果

| 项 | 修复前 | 修复后 |
|---|---|---|
| `ruff check app tests` | ❌ 10 errors | ✅ **All checks passed!** |
| `pytest -q` | 61 passed | ✅ **61 passed**（未破坏任何既有测试） |
| `tsc --noEmit` | ✅ | ✅ 通过 |
| `vite build` | ✅ | ✅ 通过（364.31 kB / gzip 116.30 kB） |
| 完整研究链路（真实 Ollama + Tavily） | 跑通但计划全废 | ✅ **跑通且产出可用**：4 步真实计划 + 6 条 findings + 报告 6 sections / 2 limitations |
| `/api/research/plan` | 间歇 502 | ✅ 连续 200 |
| 取消后复活 | 可复活并出报告 | ✅ 409 |
| 重启后恢复 | 500 | ✅ 409 明确提示 |

### 未处理（有意保留）

- **C4 `langchain-core` 未显式声明**：`app/graph/nodes.py` 直接 import 了它，但它只作为 `langgraph` 的传递依赖存在。补声明需要同步更新 `uv.lock`（要联网重新解析），本次未做，建议在下一次 `uv add langchain-core` 时一并处理。
- **C3 / C5 配置注释**：`EMBEDDING_DIMENSION=256` 与 nomic-embed-text 实际 768 维不一致（仅在 hash 兜底模式生效，无实际影响）；`pyproject.toml` 硬编码清华镜像源。均为说明性问题，已记录。
