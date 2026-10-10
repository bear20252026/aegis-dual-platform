#!/usr/bin/env python3
"""check_file_sizes.py —— SP-255（2026-10-02 审计·I-03）：行数红线门禁。

红线口径（CLAUDE.md「单文件单职责」/ PR 模板同源）：新文件 ≤300 行、
改造后 ≤500 行。静态检查无法回答「哪些存量文件本就超限」——引入基线
ratchet（scripts/file_size_baseline.json）：

- 基线登记现存超 300 行源文件及其行数快照；基线内文件「只许减不许增」
  （超基线即 exit 1——防「顺手再加几十行」）；
- 基线外文件一律按 ≤300 行红线（新文件无 500 行豁免）——存量 301..500
  行文件已登记在基线内，其增长同样被 ratchet 拦截。

扫描面：git ls-files 收口受管源文件（*.py *.cs *.kt *.kts *.rs *.js
*.mjs），排除生成物目录（契约生成代码随生成器产出、行数不受人控——契约镜像由
contracts.yml 的「Regenerate + git diff --exit-code」兜，UniFFI 绑定由
scripts/verify_uniffi_binding_surface.py 兜，都不入本红线面）。
行数口径与 wc -l 一致（按换行符计数，CRLF/LF 均可），与基线快照同口径。

用法：
    python scripts/check_file_sizes.py                  # 门禁检查（CI/本地同口径）
    python scripts/check_file_sizes.py --write-baseline # 重建基线快照（人工 diff
                                                        # 核对后再入库，不静默自动更新）

退出码：0=通过 / 1=任一文件越线 / 2=环境错误（git 不可用、基线缺失或损坏）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = Path(__file__).resolve().parent / "file_size_baseline.json"

# 扫描的源码扩展名（与基线生成口径一致）
SOURCE_EXTENSIONS = ("*.py", "*.cs", "*.kt", "*.kts", "*.rs", "*.js", "*.mjs")

# 生成物目录前缀（不入红线面）
GENERATED_PREFIXES = (
    "windows/src/Aegis.Windows.App/Contracts/Generated/",
    "android/contracts/src/main/kotlin/com/aegis/contracts/generated/",
    # R9-RS-2：UniFFI 绑定的行数由 uniffi 版本 + 导出面决定，不受人控——把
    # `#[uniffi::export]` 加一个方法就涨 95 行，按 ratchet 反而会拦住「把入库件
    # 重 derive 成当前真相」这个正确动作。它不在红线面不等于无人看管：
    # 漂移由 scripts/verify_uniffi_binding_surface.py 判红（名字集合双向对账）。
    "core/rust-policy-core/bindings/",
)

# 基线外文件红线（新文件同口径）
LINE_LIMIT = 300


def list_managed_sources() -> list[str]:
    """git ls-files 收口扫描面——返回相对仓库根的 posix 路径。"""
    result = subprocess.run(
        ["git", "ls-files", "--", *SOURCE_EXTENSIONS],
        cwd=str(ROOT), check=False, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        print(f"❌ git ls-files 失败：{result.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2)
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    # startswith 接受元组——逐路径排除生成物前缀
    return [p for p in paths if not p.startswith(GENERATED_PREFIXES)]


def count_lines(path: Path) -> int:
    """行数按换行符计数（wc -l 同口径——与基线快照生成口径一致）。"""
    return path.read_bytes().count(b"\n")


def load_baseline() -> dict[str, int]:
    """读取基线快照；缺失/损坏属环境错误（exit 2，不静默放行）。"""
    if not BASELINE_PATH.exists():
        print(f"❌ 基线文件缺失：{BASELINE_PATH}", file=sys.stderr)
        raise SystemExit(2)
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in data["files"].items()}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"❌ 基线文件损坏（{BASELINE_PATH}）：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def write_baseline() -> int:
    """重建基线快照——只写文件、不代替人工审查（增长须在 PR 说明拆分计划）。"""
    snapshot: dict[str, int] = {}
    for rel in list_managed_sources():
        path = ROOT / rel
        if not path.is_file():
            # 索引在、工作树已删（待提交的删除）——不入快照
            continue
        snapshot[rel] = count_lines(path)
    over = {p: n for p, n in snapshot.items() if n > LINE_LIMIT}
    payload = {
        "_comment": [
            "SP-255（2026-10-02 审计·I-03）行数红线基线（ratchet）。",
            f"登记现存超 {LINE_LIMIT} 行的受管源文件快照；基线内文件只许减不许增，"
            "基线外文件一律 ≤300 行。",
            "重建规程：python scripts/check_file_sizes.py --write-baseline，"
            "人工 diff 核对后入库。",
        ],
        "files": dict(sorted(over.items())),
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✅ 基线已重建：{len(over)} 个超 {LINE_LIMIT} 行文件 → {BASELINE_PATH}")
    print("⚠️ 请人工 diff 核对后入库——基线增长须在 PR 说明中给出拆分计划")
    return 0


def run_check() -> int:
    """门禁检查：基线内不许增长、基线外不许超 300 行。"""
    baseline = load_baseline()
    violations: list[str] = []
    checked = 0
    for rel in list_managed_sources():
        path = ROOT / rel
        if not path.is_file():
            continue
        checked += 1
        lines = count_lines(path)
        if rel in baseline:
            limit = baseline[rel]
            if lines > limit:
                violations.append(
                    f"{rel}: {lines} 行 > 基线 {limit} 行"
                    "（ratchet：基线文件只许减不许增）")
            elif lines < limit:
                # R7-TOOL-05（第七轮 2026-10-04）：基线记的是**最后一次人工快照**而非
                # 历史最小值——文件缩到红线以下却不收窄基线，其后涨回原额度仍然绿，
                # 等于每次重构都给后续 PR 留下越线额度。收窄必须是同 PR 的动作。
                violations.append(
                    f"{rel}: {lines} 行 < 基线 {limit} 行——基线未同步收窄"
                    "（运行 python scripts/check_file_sizes.py --write-baseline "
                    "并把收窄结果一并提交；否则该文件可在额度内自由回涨）")
        elif lines > LINE_LIMIT:
            violations.append(
                f"{rel}: {lines} 行 > {LINE_LIMIT} 行红线（基线外文件——新文件"
                "按红线拆分；确属存量超限走 --write-baseline 重建并说明）")
    if checked == 0:
        # R7-TOOL-04（第七轮）：扫描面为空 = 没有任何文件被判定，此前恒绿——
        # git 索引异常、在错误目录执行、或受管源被整体移出面都会静默通过。
        # 与 check_workflow_shells/verify_vectors 同口径：空面属环境错误（2）。
        print("❌ 扫描面为空（0 个受管源文件）——git ls-files 或执行目录异常，"
              "不作通过判定", file=sys.stderr)
        return 2
    if violations:
        print(f"❌ 行数红线门禁失败（{len(violations)} 处）：")
        for item in sorted(violations):
            print(f"  - {item}")
        return 1
    print(f"✅ 行数红线门禁通过（扫描 {checked} 个源文件；基线 {len(baseline)} 项）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="行数红线门禁（新文件 ≤300 行 + 基线 ratchet——SP-255）")
    parser.add_argument(
        "--write-baseline", action="store_true",
        help="重建基线快照（scripts/file_size_baseline.json）而非检查")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.write_baseline:
        return write_baseline()
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
