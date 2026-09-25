"""把 API Key 写进 backend/.env.production 的小工具（只改指定那几行，不碰其他内容）。

为什么要这个脚本，而不是让你手动改文件：

  1. 手动改容易把 key 粘到 .env 或 .env.example 里，前者会污染本地开发环境、
     后者会被提交到 GitHub。这个脚本只认 .env.production 一个目标。
  2. 写之前会**断言该文件处于 git 忽略状态**，万一哪天 .gitignore 被改坏了，
     脚本会直接拒绝执行，而不是默默把 key 写进一个可提交的文件。
  3. 写完之后做一次回读校验，并打印脱敏预览，确认改对了。

用法（在项目根目录执行）：

    python backend/scripts/set_api_key.py --llm sk-xxxxxxxx
    python backend/scripts/set_api_key.py --tavily tvly-dev-xxxxxxxx
    python backend/scripts/set_api_key.py --llm sk-x --tavily tvly-y --embedding sk-z

    # 只看当前状态，不写任何东西：
    python backend/scripts/set_api_key.py --check

安全约定：
  - 脚本不会把 key 打印到终端（只打印前 4 位 + 长度）
  - 脚本不会把 key 写进日志、不会 commit、不会 push
  - 目标文件必须是 git 忽略的，否则拒绝写入
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "backend" / ".env.production"

# 参数名 -> .env.production 里的配置项名
KEY_FIELDS = {
    "llm": "LLM_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "embedding": "EMBEDDING_API_KEY",
}


def _mask(value: str) -> str:
    """脱敏预览：只显示前 4 位和后 2 位，其余用 * 代替。"""
    if not value:
        return "(空)"
    if len(value) <= 8:
        return f"{value[:2]}{'*' * (len(value) - 2)}（长度 {len(value)}）"
    return f"{value[:4]}...{value[-2:]}（长度 {len(value)}）"


def _is_git_ignored(path: Path) -> tuple[bool, str]:
    """确认 path 被 git 忽略。返回 (是否忽略, 说明)。

    用 `git check-ignore` 而不是自己解析 .gitignore —— 后者要考虑
    取反规则、目录继承、全局 gitignore，自己写一定会有漏。
    """
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-v", str(path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False, "找不到 git 命令，无法校验忽略状态"

    # exit 0 = 被忽略；1 = 未被忽略；128 = 出错（如不在 git 仓库里）
    if result.returncode == 0:
        return True, result.stdout.strip()
    if result.returncode == 1:
        return False, "该文件**未被** git 忽略"
    return False, f"git check-ignore 出错：{result.stderr.strip()}"


def _read_current(path: Path) -> dict[str, str]:
    """读出目标文件里现有的 Key 值，用于 --check 和写入前的备份提示。"""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Z_]+)=(.*)$", line)
        if match and match.group(1) in KEY_FIELDS.values():
            values[match.group(1)] = match.group(2)
    return values


def _set_field(path: Path, field: str, value: str) -> bool:
    """只替换 `FIELD=...` 那一行，其他内容原样保留。返回是否真的改动了。"""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(field)}=.*$", re.MULTILINE)

    if not pattern.search(text):
        print(f"  ✗ 目标文件里找不到 `{field}=` 这一行，未做修改")
        return False

    new_text, count = pattern.subn(f"{field}={value}", text, count=1)
    if count == 0:
        return False

    path.write_text(new_text, encoding="utf-8")
    return True


def _print_status(path: Path) -> None:
    current = _read_current(path)
    print(f"\n当前 {path.relative_to(REPO_ROOT)} 中的 Key 状态：")
    for name, field in KEY_FIELDS.items():
        value = current.get(field, "")
        flag = "已配置" if value else "未配置（留空）"
        print(f"  {field:<22} {flag:<16} {_mask(value)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把 API Key 写入 backend/.env.production（该文件不进 Git）",
    )
    parser.add_argument("--llm", metavar="KEY", help="DeepSeek / OpenAI 兼容 API Key")
    parser.add_argument("--tavily", metavar="KEY", help="Tavily 搜索 API Key")
    parser.add_argument("--embedding", metavar="KEY", help="Embedding API Key")
    parser.add_argument(
        "--check", action="store_true", help="只查看当前状态，不写入任何内容"
    )
    args = parser.parse_args()

    if not TARGET.is_file():
        print(f"✗ 目标文件不存在：{TARGET}", file=sys.stderr)
        return 1

    # ---- 第一道闸：目标文件必须是 git 忽略的 ----
    ignored, reason = _is_git_ignored(TARGET)
    if not ignored:
        print(
            "✗ 拒绝写入：目标文件不处于 git 忽略状态。\n"
            f"  {reason}\n"
            "  这意味着写入后它可能被提交到 GitHub。\n"
            "  请先修复 .gitignore（Environment 段应有 `.env.production`），再重试。",
            file=sys.stderr,
        )
        return 1
    print(f"✓ 安全检查通过：{TARGET.name} 已被 git 忽略（{reason}）")

    _print_status(TARGET)

    if args.check:
        print("\n（--check 模式，未做任何修改）")
        return 0

    updates = {
        KEY_FIELDS["llm"]: args.llm,
        KEY_FIELDS["tavily"]: args.tavily,
        KEY_FIELDS["embedding"]: args.embedding,
    }
    pending = {field: value for field, value in updates.items() if value}
    if not pending:
        print("\n没有提供任何 Key（--llm / --tavily / --embedding），未做修改。")
        return 0

    print()
    changed = False
    for field, value in pending.items():
        if _set_field(TARGET, field, value):
            print(f"  ✓ 已写入 {field} = {_mask(value)}")
            changed = True

    if not changed:
        print("  没有任何改动。")
        return 0

    # ---- 第二道闸：写完回读，确认落盘正确 ----
    print("\n回读校验：")
    verify = _read_current(TARGET)
    ok = True
    for field, value in pending.items():
        actual = verify.get(field, "")
        if actual == value:
            print(f"  ✓ {field} 校验通过")
        else:
            print(f"  ✗ {field} 校验失败！（文件里是 {_mask(actual)}）")
            ok = False

    if ok:
        print(
            "\n下一步：重新部署，让服务器读到新的 .env.production。\n"
            "提示：`git status` 里不应看到 .env.production —— 若看到了，"
            "说明 .gitignore 有问题，立刻停下来检查。"
        )
        return 0

    print("\n✗ 有字段校验未通过，请检查文件。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
