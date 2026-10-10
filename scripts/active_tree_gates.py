#!/usr/bin/env python3
"""active_tree_gates.py —— PY-263（2026-10-02 审计）：活跃树质量门禁单源。

背景：legacy-python-guard.yml 中「ruff 检查（根仓库脚本……）」与「bandit
安全扫描（活跃树 scripts/release/contracts/agent——PY-245 接线）」两个步骤
的命令行此前各自内联在 workflow 里（.github 与本地手工复跑双源漂移面），
且只有周六 cron 触发。本脚本把两步的命令参数收拢为可复用单源：

- ruff 门禁：ruff check scripts release contracts agent validate_release.py
  tests core/rust-policy-core/bindings（口径与 workflow 步骤逐字一致）
- bandit 门禁：bandit -c bandit.yaml -r scripts release contracts agent
  validate_release.py tests core/rust-policy-core/bindings -ll -q
  （配置单源根级 bandit.yaml——仅 Medium/High 触发失败；SP-227 面对齐 ruff）

.workflow 后续接线（SP 批承接 .github 变更）直接以
``python scripts/active_tree_gates.py ruff`` / ``... bandit`` 替代内联命令行，
本地亦可随时复跑同一口径。统一经 ``sys.executable -m`` 调用——不依赖
ruff/bandit 在 PATH 中的安装形态（与 pytest 调用口径一致）。

用法：
    python scripts/active_tree_gates.py            # 全部门禁（ruff + bandit）
    python scripts/active_tree_gates.py ruff       # 仅 ruff
    python scripts/active_tree_gates.py bandit     # 仅 bandit

退出码：0=全部通过 / 1=任一门禁失败（子工具退出码透传汇总）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ruff 门禁目标面——与 legacy-python-guard.yml 现行步骤逐字一致
#（SP-208 门禁面：validate_release.py、tests/python、core/rust-policy-core/
#  bindings 均在 lint 范围内；pyproject.toml 的 [tool.ruff] 是规则单源）
RUFF_TARGETS = [
    "scripts", "release", "contracts", "agent",
    "validate_release.py", "tests", "core/rust-policy-core/bindings",
]

# bandit 门禁目标面 + 阈值口径（-ll 仅 Medium/High 失败；豁免单源 bandit.yaml）
# SP-227（2026-10-02 审计）：对齐 SP-208 ruff 面——validate_release.py、tests、
# core/rust-policy-core/bindings 此前不在 SAST 范围（subprocess/哈希操作漏扫）
BANDIT_TARGETS = [
    "scripts", "release", "contracts", "agent",
    "validate_release.py", "tests", "core/rust-policy-core/bindings",
]
BANDIT_EXTRA_ARGS = ["-ll", "-q"]

# CI 解释器钉在 3.12（各 workflow 的 python-version），本地常跑 3.13+。
# 只在 3.13+ 才存在的 API 写进活跃树时，本地全绿、CI 直接 TypeError——
# PR #82 实测：`Path.read_text(newline="")` 的 newline 关键字是 3.13 新增，
# 整套 tests/python 在 CI 上报 "got an unexpected keyword argument 'newline'"。
# 本门禁把这类"只在更高版本成立"的写法扫出来，不让它再靠一次红 CI 才被发现。
HIGH_VERSION_APIS = [
    # 模式与提示串都拆成相邻字面量书写——否则本表会扫到自己（自指假阳性）。
    # 用 [^)]* 界定参数列，不再写单词边界转义（转义在部分工具链里会被吞掉）。
    ("read_text_newline",
     r"\.read_" r"text\([^)]*newline\s*=",
     "Path.read_" r"text(newline=) 需 3.13+——改用 open(path, newline=...)"),
    ("walk_recurse_on_error",
     r"\.w" r"alk\([^)]*recurse_on_error\s*=",
     "Path.w" r"alk(recurse_on_error=) 需 3.13+"),
    ("path_fromuri",
     r"Path\.from" r"uri\(",
     "Path.from" r"uri() 需 3.13+——CI 钉 3.12"),
]


def _python_files(targets: list[str]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        base = ROOT / target
        if base.is_file() and base.suffix == ".py":
            files.append(base)
        elif base.is_dir():
            files.extend(sorted(base.rglob("*.py")))
    return files


def compat_violations(files: list[Path]) -> list[str]:
    """扫描给定 py 文件里"仅高版本 Python 才成立"的写法。

    限制（如实声明）：按行匹配并跳过 `#` 之后的内容——串里含 `#` 时可能漏判；
    本门禁的目标是窄集合（钉版差异），不是通用 AST lint。"""
    problems: list[str] = []
    for path in files:
        if "__pycache__" in path.parts:
            continue
        for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            code = line.split("#", 1)[0]
            for _rule_id, pattern, message in HIGH_VERSION_APIS:
                if re.search(pattern, code):
                    # 相对根目录显示；扫描面在根之外（单测用 tmp_path）时退回原路径
                    try:
                        label = str(path.relative_to(ROOT))
                    except ValueError:
                        label = str(path)
                    problems.append(f"{label}:{number}: {message}")
    return problems


def run_compat() -> int:
    """3.12 兼容门禁（口径与 ruff/bandit 同面——同一 TARGETS，不另立范围）。

    额外把 `.github/workflows/*.yml` 一起扫：workflow 里内嵌的 python（heredoc）是同一条
    判据的第二处落点，而它天然不在 `*.py` 扫描面里。这不是假设——PR #82 与
    run 37800016632 是**同一个缺陷的两次发生**：第一次在 tests/python，第二次就藏在
    Dependency-Retlock 的 heredoc 里，本地 3.14 全绿、CI 3.12 直接 TypeError。"""
    files = _python_files(RUFF_TARGETS)
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    # R9-CI-5（第九轮 2026-10-10）：`.github/actions/*/action.yml` 里同样有内嵌 python
    # heredoc（prepare-geogebra 的 zip-slip 断言与入口存在性检查），而
    # check_workflow_shells.py 早已把 actions 目录纳入 pwsh 面——两个「workflow 结构类」
    # 门禁覆盖面不一致，R8-CI-21 那个「同一缺陷第二次发生」的第三次落点就在这里。
    actions = sorted((ROOT / ".github" / "actions").glob("*/action.yml"))
    problems = compat_violations(files) + compat_violations(workflows) + compat_violations(actions)
    print(f"[gate] py312-compat: 扫描 {len(files)} 个 py 文件 + {len(workflows)} 个 workflow"
          f" + {len(actions)} 个 composite action")
    if not files or not workflows or (ROOT / ".github" / "actions").is_dir() and not actions:
        print("[gate] py312-compat: FAILED（扫描面为空——空面即恒绿）")
        return 2
    if problems:
        for problem in problems:
            print(f"  ❌ {problem}")
        print("[gate] py312-compat: FAILED")
        return 1
    print("[gate] py312-compat: OK")
    return 0


def _run_gate(name: str, cmd: list[str]) -> int:
    """执行单个门禁子命令——cwd 锚定仓库根，退出码透传。"""
    print(f"[gate] {name}: {' '.join(cmd)}")
    # PLW1510：门禁以子工具退出码为断言对象——显式 check=False 手动判定
    result = subprocess.run(cmd, cwd=str(ROOT), check=False)
    status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
    print(f"[gate] {name}: {status}")
    return result.returncode


def run_ruff() -> int:
    """ruff 门禁（规则面单源 pyproject.toml——本脚本只固定目标清单）。"""
    return _run_gate("ruff", [sys.executable, "-m", "ruff", "check", *RUFF_TARGETS])


def run_bandit() -> int:
    """bandit 门禁（豁免面单源 bandit.yaml——本脚本只固定目标与阈值）。"""
    return _run_gate(
        "bandit",
        [sys.executable, "-m", "bandit", "-c", "bandit.yaml",
         "-r", *BANDIT_TARGETS, *BANDIT_EXTRA_ARGS],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="活跃树（scripts/release/contracts/agent）质量门禁单源"
                    "（ruff + bandit——与 legacy-python-guard 步骤同口径）")
    parser.add_argument(
        "gate", nargs="?", choices=("ruff", "bandit", "compat", "all"), default="all",
        help="执行哪个门禁（默认 all=ruff+bandit+compat）")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.gate == "ruff":
        return run_ruff()
    if args.gate == "bandit":
        return run_bandit()
    if args.gate == "compat":
        return run_compat()
    # all：任一失败即失败（ruff 先行——静态违规通常比 SAST 发现更快定位）
    codes = [run_ruff(), run_bandit(), run_compat()]
    return 0 if all(code == 0 for code in codes) else 1


if __name__ == "__main__":
    sys.exit(main())
