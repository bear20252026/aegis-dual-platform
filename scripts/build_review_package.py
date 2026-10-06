#!/usr/bin/env python3
"""Aegis 专家评审包生成器 —— 从规范源码（single source of truth）可复现地组装评审包。

背景：`aegis-专家评审包/` 过去是"手工维护的复制快照"，会随主仓库推进而**漂移变旧**
（曾停在 e66d36e，缺后续安全加固：bridge_guard 调用方来源模型、非码本上限 MAX_CONSUMED_NONCES 等）——典型的"重复源码 / 单点事实源被破坏"。本脚本改为
**从规范源码自动生成**：读版本/提交/时间戳，按清单复制源码（排除构建产物/缓存），
生成 README 头部戳记 + manifest.json（含每文件 SHA-256 校验）。

R8-PY-04②（第八轮审计 2026-10-06）更正旧口径「release 时用 --check 保证与当前源码
同步」：快照自 A-4 起不入库（`aegis-专家评审包` 在 `git ls-files` 命中 0），CI 里
`--build` 到临时目录再 `--check` 同一目录＝同 commit 两次生成相比 ⇒ 恒真。该步骤
**实际**证明的是生成器确定性（无时间戳/顺序抖动混入 manifest），与"同步"无关。

用法：
    python scripts/build_review_package.py --build        # 就地生成到 aegis-专家评审包/
    python scripts/build_review_package.py --check        # 重新生成并比对＝确定性自检（CI 用）
    python scripts/build_review_package.py --build --out /tmp/review-build   # 输出到指定目录

本脚本仅依赖 Python 标准库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PKG = ROOT / "aegis-专家评审包"

# 复制到评审包的规范源码目录（canonical -> package 相对路径保持一致）
TREE_COPY: list[tuple[str, str]] = [
    ("core/rust-policy-core", "core/rust-policy-core"),
    ("android", "android"),
    ("windows/src", "windows/src"),
    ("windows/tests", "windows/tests"),
    ("legacy/windows-pywebview", "legacy/windows-pywebview"),
    ("contracts", "contracts"),
    ("shared", "shared"),
    ("docs", "docs"),
    (".github/workflows", ".github/workflows"),
]

# 复制到评审包根目录的单个规范文件（全部为评审相关文档/配置）。
# PY-204（2026-09-26 审计）：原 FILE_COPY 中的 docs/DESIGN.md 与
# docs/KNOWLEDGE_BASE.md 是死条目——TREE_COPY 的 ("docs", "docs") 已整树
# 复制 docs/，两文件经树复制进入评审包；单文件条目属重复登记（同名去重
# 掩盖了冗余），删除并在此注释留痕。
FILE_COPY: list[str] = [
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CLAUDE.md",
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
# PY-277（2026-10-02 审计）：删除死条目 AegisBrowser-Setup-2.1.6.exe——
# .exe 已被 EXCLUDE_SUFFIXES 整类排除（后缀规则先命中），该文件名条目
# 永无独立生效面（同名 .exe 无论出现在哪个目录都被后缀规则拦截）。
EXCLUDE_NAMES = {
    "gradle-wrapper.jar", "fonts-bundle.zip",
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
            capture_output=True, text=True, check=True, timeout=30,  # PY-032
        ).stdout.strip()
        subject = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"], cwd=ROOT,
            capture_output=True, text=True, check=True, timeout=30,  # PY-032
        ).stdout.strip()
        return sha, subject
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return "unknown", "unknown"


def version_props() -> dict[str, str]:
    # PY-234（2026-10-01 审计）：本函数此前是仓库第三份 properties 解析
    #（宽松吞坏行——与 sync_versions.load_properties 单源语义分叉）。改为
    # 复用 scripts/sync_versions.load_properties：坏行 RuntimeError 带
    # 文件:行号（PY-026 口径，fail-fast 不再静默吞）。缺文件维持返回 {}
    #（评审包工具对未初始化工作副本保持可用——与发布链必需键语义不同）。
    from sync_versions import load_properties
    p = ROOT / "shared" / "version.properties"
    if not p.exists():
        return {}
    return load_properties(p)


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
        # R8-PY-04①：根缺席＝整棵评审面静默缺席而包看上去仍完整——硬失败。
        if not src.is_dir():
            raise SystemExit(f"INPUT-FAIL: 评审包清单根不存在: {canonical}")
        # PY-205（2026-09-26 审计）：src.rglob("*") 全遍历后再逐文件过滤——
        # android/build、target 等目录数千中间产物全走一遍 IO。改
        # os.walk(topdown=True) 在 dirs 层剪枝（EXCLUDE_DIRS / EXCLUDE_SUBTREES
        # 命中的子树根本不进入），文件级规则（名字/后缀/符号链接）仍逐文件判。
        for dirpath, dirnames, filenames in os.walk(src, topdown=True):
            rel_dir = Path(dirpath).relative_to(src)
            dirnames[:] = [
                d for d in dirnames
                if d not in EXCLUDE_DIRS
                and (canonical, (rel_dir / d).parts[0]) not in EXCLUDE_SUBTREES
            ]
            for fname in filenames:
                rel = rel_dir / fname
                # 与原 _match_excluded 全路径段判定对齐：文件名自身命中
                # EXCLUDE_DIRS（无后缀名恰与排除目录同名的极端情况）同样剔除
                if rel.name in EXCLUDE_DIRS or rel.name in EXCLUDE_NAMES or rel.suffix in EXCLUDE_SUFFIXES:
                    continue
                p = src / rel
                # 与原实现一致：跳过非普通文件（坏符号链接等）
                if not p.is_file() or p.is_symlink():
                    continue
                out.append(Path(pkg) / rel)
    for f in FILE_COPY:
        if not (ROOT / f).is_file():
            raise SystemExit(f"INPUT-FAIL: 评审包清单文件不存在: {f}")
        if not _match_excluded(Path(f)):
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


def build(out_dir: Path) -> list[dict[str, str]]:
    """组装评审包到 out_dir。返回 manifest 条目列表。

    PY-203（2026-09-26 审计）：删除死参数 apply_edit——函数体内零引用，
    --check 路径传入 False 并不改变任何行为（README 戳记始终由
    stamp_readme 按保留编辑语义处理）。调用点已同步。
    """
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
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
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
    # PY-274（2026-10-02 审计）：rmdir 的 OSError 兜底按设计静默（非空目录
    # 保留）——行级 nosec 注记替代 bandit.yaml 的 B110 全局面豁免（注记行
    # 只写 nosec 本体——bandit 会把同行后续词元当附加测试 ID 解析）
    for d in sorted(out_dir.rglob("*"), reverse=True):
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                pass  # nosec B110

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
        # PY-276（2026-10-02 审计）：正典 Windows 栈是 C#（ADR-009 单轨）——
        # 原「Windows Python + C#」并列表述失实（Python 栈是 legacy 归档基线）
        "- 源代码: Rust policy-core + Android + Windows C#（附 legacy Python 归档基线）\n"
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
        manifest = build(tmp)  # 生成到临时目录（PY-203：apply_edit 死参数已删）
        expected = {m["path"]: m["sha256"] for m in manifest}
        # 已提交的包
        actual = out_dir / "manifest.json"
        if not actual.exists():
            problems.append("评审包缺少 manifest.json（未由生成器产出）")
            return False, problems
        # PY-209（2026-09-26 审计）：json.loads 无 try——已提交 manifest 损坏
        # （半截写入/手工编辑出错）时原始栈替代干净报告。包 try/except 计入
        # problems（fail-closed——损坏即判定不同步）。
        try:
            committed = json.loads(actual.read_text(encoding="utf-8"))
            committed_files = {f["path"]: f["sha256"] for f in committed.get("files", [])}
        except (json.JSONDecodeError, OSError, AttributeError, TypeError) as exc:
            problems.append(f"已提交 manifest.json 无法解析: {exc}")
            return False, problems
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
    # PY-275（2026-10-02 审计）：互斥组 required=True——无参调用此前落到
    # print_help() 且返回 0（什么都没做却报成功，CI 误判绿灯）。现无参由
    # argparse 直接报错 exit 2（用法错误语义）
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build", action="store_true", help="Assemble the review package in place.")
    g.add_argument("--check", action="store_true", help="Rebuild and compare = determinism check (R8-PY-04②).")
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

    # required=True 保证 --build/--check 至少其一——此处必为 --build
    manifest = build(args.out)
    props = version_props()
    print(
        f"BUILT: {args.out} — {len(manifest)} 个源码文件, "
        f"版本 {props.get('VERSION_NAME', 'unknown')} 戳记已更新"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
