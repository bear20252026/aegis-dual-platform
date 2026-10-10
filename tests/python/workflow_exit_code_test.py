# workflow_exit_code_test.py —— R9-CI-2/3/4/7（第九轮 2026-10-10）：
# 「门禁不可能失败」与「dispatch 输入注进门禁自己」两类形态的常驻判据。
#
# 为什么这几条值得钉死，且为什么判据写在测试层而不是往 check_workflow_shells.py
# 里再加一条规则：`tests/python` 在 contract-source-of-truth job 里每次 PR 都跑，
# 本身就是可失败门禁；而 pwsh 那条门禁已到 357 行的零余量基线，扩面必须先做拆分。
#
# 三条实证（本轮会话内实测，不是引用）：
# • `bash -ec 'false && echo hi; echo done'` ⇒ **exit 0**：Actions 的 bash 包装是
#   `-eo pipefail`，`set -e` 对 `&&` 列表中「非最后一条」的失败豁免 ⇒
#   `zipalign -c … && echo OK` 这种「用 echo 当断言」的写法永不失败，而该步末条是
#   必过的 grep ⇒ 非对齐 APK 全绿出厂（Android 15+ 的 16KB 页设备装不上）。
# • 名为 `Fail-closed gate`、正文只有 `echo "✅ …"` 的步骤结构上不可能失败，
#   日志里的「门禁」字样会被后续人当成判定证据（SP-231 删零信息量步骤同口径）。
# • `${{ github.event.inputs.branch }}` 在 shell 解析**之前**做文本替换 ⇒
#   `branch=x"; git push origin HEAD:master; #` 能把「只许写 deps/*」那道守卫自身打断。
#   Dependency-Retlock 是全仓唯一持 `contents: write` 的手工触发面。
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
ACTIONS = ROOT / ".github" / "actions"

# bash 断言形态：某条命令作为 `&&` 列表的非末位出现，末位是 echo ⇒ 前者失败被豁免
BASH_ASSERT_ECHO = re.compile(r'^\s*(?!#)(?!"if )[^\n]*?&&\s*(?:echo|printf)\b')
# 纯 echo 的「门禁」步骤名
GATE_NAME = re.compile(r"(fail[-\s]?closed|门禁|gate)", re.IGNORECASE)


def _run_blocks(doc: dict) -> list[tuple[str, str, str]]:
    """展开成 (文件内标识, 步骤名, run 文本)——含 job 级 steps 与 composite action。"""
    out: list[tuple[str, str, str]] = []
    for job_name, job in ((doc or {}).get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for idx, step in enumerate(job.get("steps") or [], start=1):
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                out.append((f"{job_name}#{idx}", str(step.get("name") or "?"), step["run"]))
    runs = (doc or {}).get("runs") or {}
    for idx, step in enumerate(runs.get("steps") or [], start=1):
        if isinstance(step, dict) and isinstance(step.get("run"), str):
            out.append((f"composite#{idx}", str(step.get("name") or "?"), step["run"]))
    return out


def _scan_workflows(workflow_dir: Path = WORKFLOWS, actions_dir: Path = ACTIONS) -> list[str]:
    """返回违规描述列表（空 = 通过）。两条判据都在 `run:` 正文层，与 shell 声明无关：
    bash 侧 `X && echo` 与「门禁名 + 只有 echo」——后者对 pwsh 同样成立。"""
    problems: list[str] = []
    files = sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml"))
    if actions_dir.is_dir():
        files += sorted(actions_dir.glob("*/action.yml"))
    for path in files:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for where, name, run in _run_blocks(doc or {}):
            code = [ln for ln in run.splitlines() if ln.strip() and not ln.strip().startswith("#")]
            if GATE_NAME.search(name) and code and all(
                re.match(r"^\s*(echo|printf)\b", ln) for ln in code
            ):
                problems.append(
                    f"{path.name} {where}「{name}」：名为门禁却只有 echo——结构上不可能失败")
            if "pwsh" in str((doc or {}).get("defaults") or ""):
                pass  # pwsh 侧由 check_workflow_shells.py 管，这里不重复判定
            for line in run.splitlines():
                if BASH_ASSERT_ECHO.match(line) and not re.match(r"^\s*(if|elif|while)\b", line):
                    problems.append(
                        f"{path.name} {where}「{name}」：`X && echo` 形态的断言在 set -e 下"
                        f"永不失败（行：{line.strip()[:60]}）")
    return problems


def test_real_tree_has_no_echo_only_gate_or_bash_assert_echo():
    assert _scan_workflows() == [], _scan_workflows()


def test_bash_assert_echo_shape_is_caught(tmp_path):
    wf = tmp_path / "workflows"
    wf.mkdir(parents=True)
    (wf / "a.yml").write_text(
        "jobs:\n"
        "  b:\n"
        "    steps:\n"
        "      - name: align\n"
        "        shell: bash\n"
        "        run: |\n"
        "          set -euo pipefail\n"
        '          "$BT/zipalign" -c -P 16 4 "$APK" && echo "对齐 OK"\n'
        '          grep -Fx "lib/arm64-v8a/x.so" <<< "$entries"\n',
        encoding="utf-8",
    )
    problems = _scan_workflows(wf, tmp_path / "actions")
    assert any("&& echo" in p for p in problems), problems


def test_echo_only_named_gate_is_caught(tmp_path):
    wf = tmp_path / "workflows"
    wf.mkdir(parents=True)
    (wf / "a.yml").write_text(
        "jobs:\n"
        "  b:\n"
        "    steps:\n"
        "      - name: Fail-closed gate\n"
        '        run: echo "✅ 验证通过"\n',
        encoding="utf-8",
    )
    problems = _scan_workflows(wf, tmp_path / "actions")
    assert any("不可能失败" in p for p in problems), problems


def test_if_condition_line_is_not_a_violation(tmp_path):
    # 不误红：`if ! zipalign …; then … exit 1; fi` 与 `if X && Y; then` 都不算断言形态
    wf = tmp_path / "workflows"
    wf.mkdir(parents=True)
    (wf / "a.yml").write_text(
        "jobs:\n"
        "  b:\n"
        "    steps:\n"
        "      - name: align\n"
        "        shell: bash\n"
        "        run: |\n"
        "          if ! zipalign -c a.apk; then\n"
        '            echo "::error::对齐失败"\n'
        "            exit 1\n"
        "          fi\n",
        encoding="utf-8",
    )
    assert _scan_workflows(wf, tmp_path / "actions") == []


def test_dependency_relock_has_no_in_run_expressions():
    """R9-CI-2：dispatch 输入必须经 env 中转——`${{ }}` 在 shell 解析前做文本替换，
    本 job 是全仓唯一持 contents: write 的手工触发面。"""
    doc = yaml.safe_load(
        (WORKFLOWS / "dependency-relock.yml").read_text(encoding="utf-8"))
    offenders = [
        (where, name, ln.strip())
        for where, name, run in _run_blocks(doc)
        for ln in run.splitlines()
        if "${{" in ln
    ]
    assert offenders == [], offenders
    # 写回步骤必须自带二次守卫（不依赖第一步存在）
    text = (WORKFLOWS / "dependency-relock.yml").read_text(encoding="utf-8")
    assert text.count("deps/*)") >= 2, "写回步骤缺少二次守卫——deps/* 边界只剩一处约定"


def test_xaml_resource_gate_runs_on_pr_surface():
    """R9-CI-4：verify_xaml_resources.py 此前唯一调用点在 release-windows.yml（tag 才跑）
    ⇒ PR 面对 XAML `FindResource`↔`x:Key` 对账零执行。现必须挂在常跑 job 上。"""
    doc = yaml.safe_load((WORKFLOWS / "contracts.yml").read_text(encoding="utf-8"))
    steps = doc["jobs"]["contract-source-of-truth"]["steps"]
    runs = [str(s.get("run") or "") for s in steps]
    assert any("verify_xaml_resources.py" in r for r in runs), "XAML 资源门禁未接入 PR 常跑面"


def test_zipalign_is_a_real_assertion():
    """R9-CI-3 的正面锚：出货 APK 的 16K 对齐校验必须能在失败时让步骤变红。"""
    text = (WORKFLOWS / "release-android.yml").read_text(encoding="utf-8")
    assert 'if ! "$BT/zipalign"' in text, "zipalign 校验退回 && echo 形态"
    assert '&& echo "[zipalign]' not in text
