#!/usr/bin/env python3
"""Aegis 专家评审包生成器 —— 从规范源码（single source of truth）可复现地组装评审包。

背景 / 结构缺陷
--------------
`aegis-专家评审包/` 过去是"手工维护的复制快照"，会随主仓库推进而**漂移变旧**
（曾停在 e66d36e，未包含后续的安全加固：bridge_guard 调用方来源模型、
非码本上限 MAX_CONSUMED_NONCES 等）。这是典型的"重复源码 / 单点事实源被破坏"。

本脚本把评审包改为**从规范源码自动生成**：读入版本/提交/时间戳，按清单复制
规范目录中的源码（并排除构建产物/缓存），生成 README 头部戳记 + manifest.json
（含每文件 SHA-256 校验），并在 release 时用 `--check` 保证与当前源码同步。

用法
----
    python scripts/build_review_package.py --build        # 在 aegis-专家评审包/ 就地生成
    python scripts/build_review_package.py --check        # 校验已提交评审包是否与规范源码同步（CI 用）
    python scripts/build_review_package.py --build --out /tmp/review-build   # 输出到指定目录

本脚本仅依赖 Python 标准库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PKG = ROOT / "aegis-专家评审包"

# 复制到评审包的规范源码目录（canonical -> package 相对路径保持一致）
TREE_COPY: list[tuple[str, str]] = [
    ("core/rust-policy-core", "core/rust-policy-core"),
    ("android", "android"),
    ("windows/src", "windows/src"),
    ("windows/tests", "windows/tests"),
    ("windows/packaging", "windows/packaging"),
    ("legacy/windows-pywebview", "legacy/windows-pywebview"),
    ("contracts", "contracts"),
    ("shared", "shared"),
    ("docs", "docs"),
    (".github/workflows", ".github/workflows"),
]

# 复制到评审包根目录的单个规范文件（全部为评审相关文档/配置）
FILE_COPY: list[str] = [
    "README.md",
    "docs/DESIGN.md",       # UI 设计语言事实来源（代码/README 均有引用）
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CLAUDE.md",
    "docs/KNOWLEDGE_BASE.md",  # 架构决策与工程知识（ADR/踩坑记录）
    "LICENSE",
    "pyproject.toml",       # 根 Python（ruff）配置
    "SECURITY.md",
    "validate_release.py",
]

# 评审包中"保留的编辑性文件"：由生成器更新头部戳记、正文手工维护，不参与源码清单比对
KEEP_FILES = {"README-专家评审.txt"}

# 规范源码中明确"归档、不参与运行面"的子树（canonical 目录 -> 其下要跳过的顶层目录名）。
# 例如 legacy/windows-pywebview/ 下的 legacy/（旧 Qt 栈 61 个 Python）被 CI/README 归档。
# A-4（架构审计 2026-08-31）：geogebra 第三方应用 bundle（50MB+/数千 js/html/css）
# 是构建期注入的外部资源、非本项目源码——评审包剔除（改由 Release 资产拉取，见
# .github/actions/prepare-geogebra）。
EXCLUDE_SUBTREES: set[tuple[str, str]] = {
    ("legacy/windows-pywebview", "legacy"),
    ("legacy/windows-pywebview", "geogebra"),
}

# 目录名命中即跳过（构建产物 / 缓存 / IDE 状态）
EXCLUDE_DIRS = {
    ".git", ".gradle", ".idea", ".vs", ".vscode", ".pytest_cache", "__pycache__",
    ".ruff_cache", "target", "bin", "obj", "build", "dist", "node_modules", ".venv",
    "venv", "Debug", "Release", "x64", "arm64", "coverage", "htmlcov",
    ".importlinter_cache",
}
# 文件后缀命中即跳过（编译/二进制产物/资源体积大且非评审重点）
EXCLUDE_SUFFIXES = {
    ".pyc", ".pyo", ".pyd", ".dll", ".exe", ".pdb", ".a", ".so", ".dylib",
    ".rlib", ".deps.json", ".runtimeconfig.json", ".cache", ".class", ".jar",
    ".ttf", ".otf", ".woff", ".woff2", ".eot", ".bmp", ".png", ".jpg", ".jpeg",
    ".gif", ".webp", ".ico", ".zip", ".gz", ".tar", ".7z",
}
# 明确要去除的生成物（体积大且可复现，评审包只保留源码）
EXCLUDE_NAMES = {
    "gradle-wrapper.jar", "fonts-bundle.zip", "AegisBrowser-Setup-2.1.6.exe",
    "app-debug.apk", "app-release.aab",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit_and_head() -> tuple[str, str]:
    """返回 (short_sha, head_subject)。非 git 环境时降级为占位。"""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        subject = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return sha, subject
    except subprocess.CalledProcessError:
        return "unknown", "unknown"


def version_props() -> dict[str, str]:
    props: dict[str, str] = {}
    p = ROOT / "shared" / "version.properties"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                props[k.strip()] = v.strip()
    return props


def _match_excluded(rel: Path) -> bool:
    """排除规则：任一父目录名命中 EXCLUDE_DIRS、最后文件名命中 EXCLUDE_NAMES、
    后缀命中 EXCLUDE_SUFFIXES，或文件明确命中要剔除的源码占位。"""
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return True
    if rel.name in EXCLUDE_NAMES:
        return True
    return rel.suffix in EXCLUDE_SUFFIXES


def collect_sources() -> list[Path]:
    """返回要复制进评审包的规范源码相对路径清单（已按规则过滤）。"""
    out: list[Path] = []
    for canonical, pkg in TREE_COPY:
        src = ROOT / canonical
        if not src.exists():
            continue
        # 遍历目录，跳过 build 产物
        for p in src.rglob("*"):
            if not p.is_file() or p.is_symlink():
                continue
            rel = p.relative_to(src)
            if _match_excluded(rel):
                continue
            if (canonical, rel.parts[0]) in EXCLUDE_SUBTREES:
                continue
            # 整个包路径
            out.append(Path(pkg) / rel)
    for f in FILE_COPY:
        fp = ROOT / f
        if fp.exists() and not _match_excluded(Path(f)):
            out.append(Path(f))
    # 去重并排序，保证确定性
    seen: set[str] = set()
    unique: list[Path] = []
    for rel in out:
        key = rel.as_posix()
        if key not in seen:
            seen.add(key)
            unique.append(rel)
    return sorted(unique, key=lambda p: p.as_posix())


def build(out_dir: Path, apply_edit: bool = True) -> list[dict[str, str]]:
    """组装评审包到 out_dir。返回 manifest 条目列表。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    sources = collect_sources()

    for rel in sources:
        canonical_src = ROOT / rel
        if not canonical_src.is_file():
            continue
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(canonical_src, dest)
        manifest.append({
            "path": rel.as_posix(),
            "sha256": sha256(dest),
            "bytes": dest.stat().st_size,
        })

    # 生成 manifest.json
    props = version_props()
    version = props.get("VERSION_NAME", "unknown")
    short, subject = git_commit_and_head()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    manifest_doc = {
        "generated_at": generated_at,
        "version": version,
        "versionCode": props.get("VERSION_CODE", ""),
        "commit": short,
        "commit_subject": subject,
        "file_count": len(manifest),
        "files": manifest,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # 干净同步：删除"既不来自规范源码、也不是保留编辑文件"的陈旧条目，
    # 确保评审包 == 生成器输出 + README（单点事实源，杜绝手工残留）。
    produced = {m["path"] for m in manifest} | {"manifest.json"} | KEEP_FILES
    for p in list(out_dir.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(out_dir).as_posix()
        if rel not in produced:
            p.unlink()
    # 清空空目录
    for d in sorted(out_dir.rglob("*"), reverse=True):
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                pass

    # 更新/生成 README 头部戳记（保留正文编辑内容）
    stamp_readme(out_dir, version, short, subject, generated_at, len(manifest))
    return manifest


def stamp_readme(out_dir: Path, version: str, short: str, subject: str,
                 generated_at: str, file_count: int) -> None:
    """更新 README 头部 3 行戳记；保留既有正文编辑内容，缺失时生成模板。"""
    readme = out_dir / "README-专家评审.txt"
    header_update = {
        "# 生成时间:": f"# 生成时间: {generated_at}",
        "# 版本:": f"# 版本: {version}",
        "# 提交:": f"# 提交: {short} ({subject})",
        "# 源码文件数:": f"# 源码文件数: {file_count}",
    }
    if readme.exists():
        lines = readme.read_text(encoding="utf-8").splitlines(keepends=True)
        out: list[str] = []
        for line in lines:
            replaced = False
            for k, v in header_update.items():
                if line.startswith(k):
                    out.append(v + "\n")
                    replaced = True
                    break
            if not replaced:
                out.append(line)
        readme.write_text("".join(out), encoding="utf-8")
    else:
        template = _readme_template(version, short, subject, generated_at, file_count)
        readme.write_text(template, encoding="utf-8")


def _readme_template(version: str, short: str, subject: str,
                     generated_at: str, file_count: int) -> str:
    return (
        "# Aegis Browser 专家评审包\n"
        f"# 生成时间: {generated_at}\n"
        f"# 版本: {version}\n"
        f"# 提交: {short} ({subject})\n"
        f"# 源码文件数: {file_count}\n"
        "\n"
        "## 包含内容\n"
        "- 源代码: Rust policy-core + Android + Windows Python + C#\n"
        "- 文档: 安全审计报告 + 架构设计 + 开源浏览器调研 + 安全测试指南 + 红蓝对抗审计\n"
        "- CI/CD: GitHub Actions workflow\n"
        "\n"
        "> 本目录由 `scripts/build_review_package.py` 从规范源码自动生成，\n"
        "> 请勿手工编辑（构建产物/校验清单见 manifest.json）。\n"
        "\n"
        "## 架构概述\n"
        "- 单路径数据流: Adapter -> Broker -> Decision -> Executor -> BrowserEvent -> BrowserSessionState -> ChromeUI\n"
        "- 五项不变量: INV-01~05 全部满足\n"
        "\n"
        "## 专家评审要点\n"
        "1. 架构合理性\n2. 模块化\n3. 安全性\n4. 代码质量\n5. 与行业标准对比\n6. 代码体积\n"
    )


def check_reviewed(out_dir: Path) -> tuple[bool, list[str]]:
    """--check：比对已提交评审包与生成结果是否一致（源码与 checksum）。"""
    problems: list[str] = []
    tmp = out_dir.parent / (out_dir.name + ".check")
    try:
        manifest = build(tmp, apply_edit=False)  # 生成到临时目录
        expected = {m["path"]: m["sha256"] for m in manifest}
        # 已提交的包
        actual = out_dir / "manifest.json"
        if not actual.exists():
            problems.append("评审包缺少 manifest.json（未由生成器产出）")
            return False, problems
        committed = json.loads(actual.read_text(encoding="utf-8"))
        committed_files = {f["path"]: f["sha256"] for f in committed.get("files", [])}
        # 集合对称差 + 哈希不一致
        for path in expected:
            if path not in committed_files:
                problems.append(f"新生成未提交: {path}")
        for path, h in committed_files.items():
            if path not in expected:
                problems.append(f"已提交但源码不存在/被排除: {path}")
            elif expected[path] != h:
                problems.append(f"内容漂移: {path}")
        if len(expected) != len(committed_files):
            problems.append(
                f"文件数不一致: 生成 {len(expected)} vs 已提交 {len(committed_files)}"
            )
        return len(problems) == 0, problems
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate / verify the Aegis review package.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--build", action="store_true", help="Assemble the review package in place.")
    g.add_argument("--check", action="store_true", help="Verify the committed package is in sync.")
    ap.add_argument("--out", type=Path, default=DEFAULT_PKG, help="Output directory.")
    args = ap.parse_args()

    if args.check:
        ok, problems = check_reviewed(args.out)
        if ok:
            print(f"OK: 评审包与规范源码同步 ({args.out.name})")
            return 0
        print("SYNC-FAIL:")
        for p in problems:
            print(f"  - {p}")
        return 1

    if args.build:
        manifest = build(args.out)
        props = version_props()
        print(
            f"BUILT: {args.out} — {len(manifest)} 个源码文件, "
            f"版本 {props.get('VERSION_NAME', 'unknown')} 戳记已更新"
        )
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
