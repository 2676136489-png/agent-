"""Application configuration.

[P0] 这是全后端唯一的「配置来源」。
为什么需要它：把「会随环境变化的值」（端口、密钥、CORS 白名单、日志级别）
从代码里抽出来，放到环境变量 / .env 文件里。
好处：同一份代码可以在开发、测试、生产里跑，且密钥不会进 Git。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """运行时配置。

    字段的取值优先级（高 → 低）：
    1. 进程真实环境变量（例如 export LOG_LEVEL=DEBUG）
    2. backend/.env 文件
    3. 这里写的默认值
    """

    # model_config 是 pydantic-settings 的约定写法，不是普通 pydantic 字段。
    model_config = SettingsConfigDict(
        # 多个 env 文件按**从后往前**的优先级合并：列表里越靠后的文件优先级越高
        # （pydantic-settings 的约定：后加载的覆盖先加载的）。
        # 顺序说明：
        #   ".env"            本地开发配置（含真实 Key，不入库）
        #   ".env.production" 线上部署配置（无 Key，Mock 模式，入库）
        # 让本地 .env 优先级更高，是为了「线上模板入库、本地私密配置覆盖它」——
        # 开发时若误留 .env.production，也不会把本地 Key 冲掉。
        # 真实环境变量（沙箱注入的）优先级永远高于这两者，这是 pydantic-settings
        # 的固定行为，适合放「部署时才知道的敏感值」。
        env_file=(".env.production", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",  # .env 里多写了未定义的变量时不要报错
    )

    app_name: str = "AI Research Workspace"
    environment: str = "development"  # development | staging | production
    version: str = "0.1.0"
    log_level: str = "INFO"

    # 所有接口的统一前缀，前端只需要知道这一个值
    api_prefix: str = "/api"

    # ----- LLM -----
    # auto = 有 Key 走真实 API，没 Key 自动退化成离线 Mock（保证本地/CI 可跑）
    llm_provider: str = "auto"
    # 留空则用 SDK 默认（OpenAI）；换厂商只改这两个值：
    #   DeepSeek:  https://api.deepseek.com        + deepseek-flash
    #   通义千问:  https://dashscope.aliyuncs.com/compatible-mode/v1 + qwen-plus
    llm_base_url: str = ""
    # SecretStr：打印 Settings 时会显示 '**********'，避免 Key 被日志泄露
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0
    llm_max_attempts: int = 3
    llm_temperature: float = 0.2
    llm_max_tokens: int = 2000

    # ----- Agent / Tools -----
    # 离线/真实搜索的选择：auto = 有 Tavily Key 走真实联网，没 Key 回退离线语料
    search_provider: str = "auto"
    # 联网搜索服务的 Key（当前接入 Tavily）。留空则用离线示例语料。
    tavily_api_key: SecretStr = SecretStr("")
    # 一个 Agent run 最多走几步（含工具调用与最终回答）
    agent_max_steps: int = 6
    # 整个 run 的墙钟时间上限（秒）。这是防失控的最后一道闸。
    agent_total_timeout_seconds: float = 120.0
    # 工具输出进入上下文前的最大字符数（防止把上下文撑爆）
    tool_output_max_chars: int = 3000
    # 抓取网页时的域名白名单，留空 = 不限制（仍禁止内网地址）
    fetch_allowed_domains: str = ""

    # ----- Search quota -----
    #
    # ⚠️ 单 worker 语义。判据已实测修正，别再写成「多 worker 会各记各账/超支」：
    # 防超支由 quota.py reserve() 那条 UPSERT 的 WHERE 子句保证，SQLite 写事务
    # 跨进程天然串行，实测无超支。真实理由是 WAL + 长连接在多进程写入下会
    # 永久退化为只读，而 get_search_quota() 的 lru_cache 单例没有重连路径。
    # 请勿用 --workers>1 启动；/api/health 会暴露 quota_mode: single-worker。
    # 详见 app/search/quota.py 顶部 docstring 与架构文档 §2.3.2。
    #
    # 计费口径（Tavily）：basic = 1 credit/次，advanced = 2 credits/次。
    search_quota_enabled: bool = True
    search_quota_db_path: str = "storage/search_quota.db"
    # Tavily free tier = 1000 credits/月
    search_quota_monthly_credits: int = 1000
    search_quota_warn_ratios: str = "0.5,0.75,0.9"
    # degrade_annotate = 额度耗尽仍出报告但明说（默认）；hard_stop = 拒绝新建 run
    search_quota_policy: str = "degrade_annotate"
    search_quota_soft_cap_ratio: float = 0.9
    # 单次 run 的搜索次数硬顶，防止一条 run 疯狂烧积分
    search_quota_per_run_cap: int = 12
    # 默认 basic（1 credit/次）：1000 credits 的免费额度因此可以撑满 1000 次搜索
    # （advanced 只够约 500 次）。检索质量让位于「额度够用」——改成 advanced
    # 只需把这里（或 .env 的 SEARCH_DEPTH）换成 "advanced"，单价表两种档位都在。
    # 设置页需明示「advanced = 2 credits / basic = 1 credits」。
    #
    # 用 Literal 而不是裸 str：非法值（如拼错的 "advaned"）必须**启动即报错**。
    # 否则用户以为在用 advanced（2 credits/次），实际被静默回落到 basic，
    # 或反之——两种方向都是「看不见的钱包问题」，fail-fast 才是对的。
    search_depth: Literal["basic", "advanced"] = "basic"

    # ----- Tool retry -----
    tool_max_attempts: int = 2
    tool_retry_backoff_min: float = 0.5
    tool_retry_backoff_max: float = 4.0
    retryable_tool_kinds: str = "timeout,network,upstream_5xx,rate_limit"

    # ----- Observability -----
    log_format: str = "json"  # json | plain

    # ----- Knowledge base (RAG) -----
    # SQLite 数据库文件与上传文件的存放位置（相对 backend/ 目录）
    knowledge_db_path: str = "storage/knowledge.db"
    storage_dir: str = "storage/documents"
    # Agent 运行记录（LangGraph 之外的产品视角记录）
    agent_runs_db_path: str = "storage/agent_runs.db"
    # Agent 事件流（SSE 回放 + 前端刷新恢复）
    events_db_path: str = "storage/events.db"
    # SSE 心跳间隔（秒）。必须小于常见代理的空闲超时（通常 60s）。
    sse_heartbeat_seconds: float = 15.0
    # Research Graph 的默认循环上限
    graph_max_iterations: int = 3
    graph_max_verify_attempts: int = 2
    # 切块参数：size 太小会丢上下文，太大则检索不精准；overlap 用于避免句子被切断
    chunk_size: int = 800
    chunk_overlap: int = 120
    # 一次检索返回几条
    retrieval_top_k: int = 5
    # 上传文件大小上限（字节）。必须限制，否则一个 2GB 文件就能打满内存。
    upload_max_bytes: int = 10 * 1024 * 1024

    # ----- Embedding -----
    # auto = 有 Key 用真实 embedding API，没有则用本地哈希向量（仅保证链路可跑）
    embedding_provider: str = "auto"
    embedding_base_url: str = ""
    embedding_api_key: SecretStr = SecretStr("")
    embedding_model: str = "text-embedding-3-small"
    # 本地哈希向量的维度（真实模型时不生效，以模型返回为准）
    embedding_dimension: int = 256
    embedding_timeout_seconds: float = 30.0

    # CORS 白名单：允许哪些「浏览器来源」访问后端。用逗号分隔的字符串而不是 list，
    # 因为环境变量天然是字符串，直接解析 list 容易踩坑（需要写 JSON 数组）。
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ----- 前端静态产物（单端口部署用）-----
    # 由后端托管前端构建产物时，指定 dist 目录。空 = 走默认查找顺序
    # （`backend/frontend_dist` → `backend/../frontend/dist`）。
    #
    # 为什么必须在这里声明成 Settings 字段，而不是在代码里直接读 os.environ：
    # pydantic-settings 读取 .env 文件后**不会**把未知的键注入 os.environ，
    # 所以「写进 .env 但没在 Settings 里声明」的配置项会被静默忽略 ——
    # 表现为「明明配了却不生效」。声明成字段后，它才能被 .env 文件真正驱动。
    frontend_dist: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        """把 "a,b,c" 解析成 ["a", "b", "c"]，并容忍多余的空格与空值。"""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def fetch_allowed_domains_list(self) -> list[str]:
        return [
            domain.strip() for domain in self.fetch_allowed_domains.split(",") if domain.strip()
        ]

    @property
    def search_quota_warn_ratios_list(self) -> list[float]:
        """把 "0.5,0.75,0.9" 解析成 [0.5, 0.75, 0.9]（排序由 store 负责）。"""
        return [float(ratio) for ratio in self.search_quota_warn_ratios.split(",") if ratio.strip()]

    @property
    def retryable_tool_kinds_set(self) -> frozenset[str]:
        return frozenset(
            kind.strip() for kind in self.retryable_tool_kinds.split(",") if kind.strip()
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全局唯一的 Settings 实例。

    为什么用 lru_cache：Settings() 每次都会读一遍 .env 并做校验。
    配置在一个进程内不会变，缓存一次即可（这是「单例 + 依赖注入」的轻量写法）。
    """
    return Settings()
