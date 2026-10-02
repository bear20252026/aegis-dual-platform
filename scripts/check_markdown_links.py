#!/usr/bin/env python3
"""check_markdown_links.py —— SP-256（2026-10-02 审计·I-19）：Markdown 相对链接门禁。

全仓 *.md 的链接目标存在性校验（死链 fail-closed）：

- 校验行内链接/图片 ``[text](target)`` / ``![alt](target)`` 与引用式定义
  ``[text]: target``；
- 跳过：http(s)/mailto 等外部协议目标、协议相对 ``//host``、纯锚点
  （``#`` 开头）、空目标——仓库外目标无法在本地核实；
- 目标可带 ``#锚点`` / ``?查询`` 与 ``"标题"`` 后缀——仅校验路径部分
  （锚点存在性不做静态校验）；``%20`` 等 URL 转义先解码再解析；
- 围栏代码块（``` / ~~~ 开闭之间的行）不解析——文档中的示例链接不算死链；
- ``/`` 开头目标按仓库根相对解析，其余按所在 .md 文件目录相对解析。

扫描面：git ls-files 收口的受管 *.md（CLAUDE/README/docs/tests 等全量）。

用法：
    python scripts/check_markdown_links.py    # CI（contracts.yml）与本地同口径

退出码：0=全部相对链接可达 / 1=存在死链（逐条列出 文件:行号）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 行内链接 / 图片：捕获括号内原始目标（可能带 "标题" 后缀）
INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]*)\)")
# 引用式定义（行首至多 3 空格）：捕获目标（行尾最后一个空白分隔 token）。
# 首字符排除 ^——脚注定义（[^1]: 文本）不是链接定义，不入校验面
REFERENCE_LINK = re.compile(r"^\s{0,3}\[[^\]^][^\]]*\]:\s+(\S+)\s*$")
# 围栏代码块开闭行（``` 或 ~~~，允许至多 3 空格缩进）
FENCE_LINE = re.compile(r"^\s{0,3}(```|~~~)")
# 外部协议（http: / https: / mailto: 等 scheme: 形态）
EXTERNAL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def list_markdown_files() -> list[Path]:
    """git ls-files 收口扫描面——返回绝对路径（保持相对路径信息在调用侧拼接）。"""
    result = subprocess.run(
        ["git", "ls-files", "--", "*.md"],
        cwd=str(ROOT), check=False, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        print(f"❌ git ls-files 失败：{result.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2)
    return [ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()]


def extract_target(raw: str) -> str:
    """从括号内原文提取路径目标：去空白 / <> 包裹 / "标题" 后缀。"""
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    # 目标与标题以空白分隔——取首个空白前 token；纯空白目标按空处理
    return target.split()[0] if target else ""


def is_skippable(target: str) -> bool:
    """外部协议 / 协议相对 / 纯锚点 / 空目标——不在相对链接校验面。"""
    return (
        not target
        or target.startswith("#")
        or target.startswith("//")
        or bool(EXTERNAL_SCHEME.match(target))
    )


def resolve_target(md_path: Path, target: str) -> Path:
    """解析链接目标为文件系统路径：/ 开头按仓库根，其余按 md 所在目录。"""
    target = urllib.parse.unquote(target)
    target = target.split("#", 1)[0].split("?", 1)[0]
    if target.startswith("/"):
        return (ROOT / target.lstrip("/")).resolve()
    return (md_path.parent / target).resolve()


def check_file(md_path: Path) -> list[str]:
    """单文件死链检查——返回 "文件:行号" 违规描述列表。"""
    rel = md_path.relative_to(ROOT).as_posix()
    try:
        text = md_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 非 UTF-8 文档不硬性拒绝——errors=replace 后仍可解析 ASCII 形态链接
        text = md_path.read_text(encoding="utf-8", errors="replace")
    dead: list[str] = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FENCE_LINE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        raw_targets = [m.group(1) for m in INLINE_LINK.finditer(line)]
        ref = REFERENCE_LINK.match(line)
        if ref:
            raw_targets.append(ref.group(1))
        for raw in raw_targets:
            target = extract_target(raw)
            if is_skippable(target):
                continue
            resolved = resolve_target(md_path, target)
            if not resolved.exists():
                dead.append(f"{rel}:{lineno}: 死链 → ({raw.strip()})")
    return dead


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Markdown 相对链接存在性门禁（死链 fail-closed——SP-256）")
    parser.parse_args(sys.argv[1:] if argv is None else argv)
    dead: list[str] = []
    checked = 0
    for md_path in list_markdown_files():
        if not md_path.is_file():
            continue
        checked += 1
        dead.extend(check_file(md_path))
    if dead:
        print(f"❌ Markdown 链接门禁失败（{len(dead)} 处死链）：")
        for item in sorted(dead):
            print(f"  - {item}")
        return 1
    print(f"✅ Markdown 链接门禁通过（扫描 {checked} 个 .md，相对链接全部可达）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
