"""启动脚本：同时适配本地开发与托管沙箱。直接 `python start.py` 即可。

为什么需要这个文件，而不是在 README 里写一条 uvicorn 命令：

1. **端口必须读 `PORT` 环境变量。** 托管沙箱把可用端口通过 `PORT` 注入，
   写死 8000 在线上会绑定失败（或绑定到一个没被反代出去的端口）。
   本地不设 `PORT` 时回落到 8000，保持开发习惯不变。

2. **必须绑定 `0.0.0.0`。** 绑 `127.0.0.1` 时进程只能被本机访问，
   反向代理从容器外部连不进来 —— 表现为「本地一切正常、线上 502」。

3. **绝不能加 `--workers`。** 配额记账依赖「单进程单连接」语义：
   Windows + WAL 下多进程并发写会让部分进程的写路径**永久退化为只读**，
   而配额 store 是 `lru_cache` 单例、没有重连路径，坏掉的 worker 会一直坏到
   进程重启（详见 app/search/quota.py 顶部 docstring）。开发模式的热重载
   （`--reload`）只重启单进程，不违反这条约束。
"""

from __future__ import annotations

import os
import sys

import uvicorn


def main() -> None:
    # 沙箱注入的 PORT 优先；本地没有就回落到 8000
    port = int(os.environ.get("PORT", "8000"))
    # 显式绑 0.0.0.0：只绑回环地址会导致反向代理连不进来（线上 502）
    host = os.environ.get("HOST", "0.0.0.0")
    # 本地开发默认开热重载；线上（有 PORT 变量）默认关掉，
    # 因为 reload 会额外起一个监视进程，在沙箱里没有必要且拖慢启动
    reload = os.environ.get("RELOAD", "").lower() in {"1", "true", "yes"}
    if "PORT" not in os.environ and not os.environ.get("RELOAD"):
        reload = True

    print(f"[start] 监听 http://{host}:{port}  (reload={reload})", file=sys.stderr)
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        # 不传 workers：必须单进程，理由见模块 docstring
    )


if __name__ == "__main__":
    main()
