# windows_python_encoding_test.py —— R9-CI-10（第九轮 2026-10-10）：Windows runner 上
# 的 python 调用必须显式声明 UTF-8 输出，否则**门禁的判定结果由控制台编码决定**。
#
# 触发事实（不是推测）：PR #137 的 `windows-contract-build` 里 `dotnet test` 782/782
# 全绿、发现数下界也达成，`scripts/assert_test_counts.py` 却在打印 `✅` 那一行抛
# `UnicodeEncodeError: 'charmap' codec can't encode character '\u2705'` ⇒ 脚本退出 1
# ⇒ 门禁在**通过路径**上把 job 打红。同一形态本仓已付过两次账：2026-10-08 的
# Dependency-Retlock 首跑（死在 heredoc 的中文 print，run 37793334416）与
# compat.yml/legacy-python-guard.yml 里既有的 `PYTHONUTF8: "1"` 注记。
#
# 判据为什么做成「job 声明 env」而不是「每个脚本自己 reconfigure」：本仓 windows job
# 里有大量 `python - <<'PY'` 形态的内嵌脚本，脚本级修复覆盖不到它们；而脚本自己
# reconfigure 仍然值得保留（本地 Windows 控制台同样不是 UTF-8，见
# tests/python/dotnet_test_count_gate_test.py 的 cp1252 用例）。两层并存，缺任一层
# 各由对应测试判红。
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
ACTIONS_ROOT = ROOT / ".github" / "actions"

# 至少这些 job 是「windows + 跑 python」的（实测 7 个：compat×2、contracts、
# dependency-relock、legacy-python-guard、native-policy、release-windows）。
# 掉到 0 说明解析面失灵，而不是"变安全了"。
MIN_SCANNED_JOBS = 7
UTF8_KEYS = ("PYTHONUTF8", "PYTHONIOENCODING")
PYTHON_CALL = re.compile(r"(?<![\w.-])python(?:\.exe)?\s")


def _local_action_runs(uses: str) -> list[str]:
    """`uses: ./.github/actions/<name>` → 该 composite 正文里的 run 文本。

    定稿项 13(a)（R9-B16）把 `python scripts/assert_test_counts.py` 搬进了
    dotnet-test-suite——不跟着把判定面扩到 composite，「windows + python」的 job 数
    就从 7 塌到 5（实测）。扫描面自己变小时宣布"没问题"，正是本锚要防的那一类。
    """
    if not uses.startswith("./.github/actions/"):
        return []
    # removeprefix 而不是 lstrip("./")：后者按字符集剥前导，会把 `.github` 的点也剥掉
    path = ROOT / uses.removeprefix("./") / "action.yml"
    if not path.is_file():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [str(step.get("run")) for step in ((doc.get("runs") or {}).get("steps") or [])
            if isinstance(step, dict) and step.get("run")]


def python_calls_on_windows(spec: dict) -> int:
    """该 job 在 windows runner 上的 python 调用次数（0 = 不在判定面）。
    含经本地 composite 转发的调用。"""
    if "windows" not in str(spec.get("runs-on") or "").lower():
        return 0
    blob = "\n".join(
        str(s.get("run")) for s in (spec.get("steps") or []) if isinstance(s, dict) and s.get("run")
    )
    calls = len(PYTHON_CALL.findall(blob))
    for step in spec.get("steps") or []:
        if isinstance(step, dict):
            for run in _local_action_runs(str(step.get("uses") or "")):
                calls += len(PYTHON_CALL.findall(run))
    return calls


def declares_utf8(spec: dict) -> bool:
    """job 级或任一步骤级声明了 PYTHONUTF8 / PYTHONIOENCODING。"""
    holders = [set((spec.get("env") or {}))]
    holders += [set(s.get("env") or {}) for s in (spec.get("steps") or []) if isinstance(s, dict)]
    return any(any(key in env for key in UTF8_KEYS) for env in holders)


def scan() -> tuple[int, list[str]]:
    """返回 (判定的 job 数, 违规列表)。"""
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    scanned, offenders = 0, []
    for path in files:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, spec in ((doc or {}).get("jobs") or {}).items():
            if not isinstance(spec, dict):
                continue
            calls = python_calls_on_windows(spec)
            if not calls:
                continue
            scanned += 1
            if not declares_utf8(spec):
                offenders.append(f"{path.name}:{job_name}（{calls} 处 python 调用）")
    return scanned, offenders


def test_real_tree_has_no_undeclared_utf8_on_windows_python_jobs():
    scanned, offenders = scan()
    assert scanned >= MIN_SCANNED_JOBS, f"扫描面塌缩：只判了 {scanned} 个 windows+python job（基线 ≥{MIN_SCANNED_JOBS}）"
    assert not offenders, "Windows runner 上的 python 调用会把成功判成失败：" + "；".join(offenders)


def test_python_only_via_local_composite_is_still_in_the_surface():
    """R9-B16 的反向锚：python 调用搬进 composite 后，判定面不能跟着缩水。

    构造一个「windows runner + 只经本地 action 调 python + 没声明 UTF-8」的 job：
    必须被数到并判违规。旧解析面会返回 0 ⇒ 这类 job 从锚里消失。
    """
    spec = {"runs-on": "windows-2025",
            "steps": [{"uses": "./.github/actions/dotnet-test-suite"}]}
    assert python_calls_on_windows(spec) >= 1, "经 composite 的 python 调用必须计入"
    assert not declares_utf8(spec)
    found = _local_action_runs("./.github/actions/dotnet-test-suite")
    assert any("assert_test_counts.py" in run for run in found), "action 正文解析不到 = 锚是摆设"
    # 不存在的 action 不能凭空造出调用面（路径写错时安静返回空，不误判也不虚增）
    assert _local_action_runs("./.github/actions/no-such-action") == []


def test_gate_flags_the_missing_declaration_and_does_not_misfire():
    py_steps = [{"run": "python scripts/whatever.py\n"}]
    windows = {"runs-on": "windows-2025", "steps": py_steps}
    assert python_calls_on_windows(windows) == 1, "在判定面却没被数到 = 锚是摆设"
    assert not declares_utf8(windows), "未声明时必须判违规"
    for env in ({"PYTHONUTF8": "1"}, {"PYTHONIOENCODING": "utf-8"}):
        assert declares_utf8({**windows, "env": env}), f"已声明 {env} 仍被误判"
    step_level = {"runs-on": "windows-2025", "steps": [{"env": {"PYTHONUTF8": "1"}, "run": "python x.py\n"}]}
    assert declares_utf8(step_level), "step 级声明同样算合规（relock 用过这种写法）"
    assert python_calls_on_windows({"runs-on": "ubuntu-latest", "steps": py_steps}) == 0, "非 windows runner 不在判定面"
    assert python_calls_on_windows({"runs-on": "windows-2025", "steps": [{"run": "dotnet test a.csproj\n"}]}) == 0, "不跑 python 的 job 不在判定面"
