"""测试环境统一配置。

[P0] 这里在「导入任何 app 模块之前」改写进程环境变量，
让整个测试会话都走「离线 Mock」：

- LLM_PROVIDER=mock：所有 LLM 调用走 MockLLMClient，不产生真实模型调用，
  也不依赖外部付费服务（TestClient 下真实 AsyncOpenAI 还会触发 event-loop 问题）。
- 清空 TAVILY_API_KEY：联网搜索回退到内置离线语料（含 example.com 等示例），
  既免费又稳定，且能命中 test_tools 的离线断言。

这样跑 `uv run pytest` 完全离线、可重复，不会因为缺 Key / 限流 / 计费而红。

注意：必须在 import app 之前设置，因为 get_settings() 是用 lru_cache 缓存的。
"""
from __future__ import annotations

import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ.pop("LLM_API_KEY", None)
os.environ["LLM_API_KEY"] = ""
os.environ.pop("TAVILY_API_KEY", None)
os.environ["TAVILY_API_KEY"] = ""
os.environ["EMBEDDING_PROVIDER"] = "hash"
