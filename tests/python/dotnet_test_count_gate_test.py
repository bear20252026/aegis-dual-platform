# dotnet_test_count_gate_test.py —— R9-CI-9（第九轮 2026-10-10）：测试**发现数**下界
# 门禁的自证 + 「八处 dotnet test 全部接线」的静态锚。
#
# 失效模式：`dotnet test` 的退出码只表达「跑到的都没失败」，零发现同样退 0。本仓 CI
# 的八处调用（compat / contracts / native-policy-artifacts / release-windows）此前只看
# 退出码，于是「绿」的含义是「没有失败的测试」，不是「782 个判定都跑过」。触发点是
# 真实的：同一批工作里 Microsoft.NET.Test.Sdk 17.14→18.10、xunit.runner.visualstudio
# 3.1.5→4.0.1 都是跨 major 的**测试宿主**升级——发现器与框架不同代时最坏结果就是
# 零发现全绿，而 PR 里没有任何人会察觉。
#
# 按本仓固定口径（R7-TOOL-04 / R8-PY-02）：不光证「现在绿」，必须证「掏空它会红」，
# 并证「不误红」（健康 TRX 必须过）。静态锚防的是第四种失效：门禁写好了但没接线。
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import assert_test_counts as atc
import pytest
import yaml

# _run_blocks 已在 workflow_exit_code_test 里把 job/composite 两种 steps 形态收敛好，
# 这里复用而不是再写一遍解析（两处解析漂移 = 第二个假绿源）。
from workflow_exit_code_test import _run_blocks

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

TRX_NS = "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"

# 套件 → 登记下界（本轮实测 Core 782、Broker 189，下界取有界余量）。workflow 里的数字与本表
# 不一致即红——防「某一处被人顺手调松」。
EXPECTED_FLOORS = {"core": 700, "broker": 160}

MINIMUM_RE = re.compile(r"--minimum (\d+)")
LABEL_RE = re.compile(r"--label (\S+)")
RESULTS_DIR_RE = re.compile(r"--results-dir (\S+)")


def _suite_of(token: str) -> str:
    lowered = token.lower()
    for suite in EXPECTED_FLOORS:
        if suite in lowered:
            return suite
    return "?"


def _write_trx(
    directory: Path,
    counters: dict[str, int] | None,
    *,
    name: str = "results.trx",
    raw: str | None = None,
) -> Path:
    """生成一份最小可解析 TRX；counters=None 表示「节点存在但形态不合」。"""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
        return path
    attrs = " ".join(f'{key}="{value}"' for key, value in (counters or {}).items())
    path.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<TestRun id="x" name="y" xmlns="{TRX_NS}">\n'
        f'  <ResultSummary outcome="Completed">\n'
        f"    <Counters {attrs} />\n"
        f"  </ResultSummary>\n"
        f"</TestRun>\n",
        encoding="utf-8",
    )
    return path


def _healthy(total: int) -> dict[str, int]:
    return {"total": total, "executed": total, "passed": total, "failed": 0, "error": 0, "notExecuted": 0}


# ---------------------------------------------------------------- 掏空它会红
def test_zero_discovery_is_red_not_green(tmp_path, capsys):
    """这条门禁存在的全部理由：一个测试都没发现 ⇒ 必须红，而不是「0 个失败」。"""
    _write_trx(tmp_path, {"total": 0, "executed": 0, "passed": 0, "failed": 0, "error": 0})
    assert atc.check(tmp_path, 700, "Core") == 1
    out = capsys.readouterr().out
    assert "发现测试数 0 < 下界 700" in out
    assert "测试宿主" in out, "报错必须指向真因，否则下一个排查者会当成「代码变好了」"


def test_shrunken_discovery_is_red(tmp_path, capsys):
    _write_trx(tmp_path, _healthy(403))
    assert atc.check(tmp_path, 700, "Core") == 1
    assert "403" in capsys.readouterr().out


def test_failed_counter_makes_it_red(tmp_path, capsys):
    _write_trx(tmp_path, {"total": 800, "passed": 799, "failed": 1, "error": 0})
    assert atc.check(tmp_path, 700, "Core") == 1
    assert "失败" in capsys.readouterr().out


def test_missing_results_directory_is_environment_error(tmp_path, capsys):
    """目录都不在 = 没有判定输入，不作通过（空扫描面同口径，exit 2）。"""
    assert atc.check(tmp_path / "nope", 700, "Core") == 2
    assert "结果目录不存在" in capsys.readouterr().err


def test_empty_results_directory_is_not_green(tmp_path, capsys):
    target = tmp_path / "empty"
    target.mkdir()
    assert atc.check(target, 700, "Core") == 2
    assert "没有任何 .trx" in capsys.readouterr().err


def test_unparsable_trx_is_environment_error(tmp_path):
    _write_trx(tmp_path, None, raw="<TestRun><broken")
    assert atc.check(tmp_path, 700, "Core") == 2


def test_trx_without_total_is_environment_error(tmp_path, capsys):
    _write_trx(tmp_path, {"passed": 5, "failed": 0})
    assert atc.check(tmp_path, 700, "Core") == 2
    assert "total" in capsys.readouterr().err


def test_trx_without_counters_node_is_environment_error(tmp_path):
    _write_trx(tmp_path, None, raw=f'<TestRun xmlns="{TRX_NS}"><ResultSummary/></TestRun>')
    assert atc.check(tmp_path, 700, "Core") == 2


def test_non_integer_counter_is_environment_error(tmp_path):
    raw = f'<TestRun xmlns="{TRX_NS}"><ResultSummary><Counters total="many" passed="0"/></ResultSummary></TestRun>'
    _write_trx(tmp_path, None, raw=raw)
    assert atc.check(tmp_path, 700, "Core") == 2


def test_partial_sum_never_becomes_a_pass(tmp_path, capsys):
    """两份 TRX 一份坏 ⇒ 判定不成立；不能「只汇总能读的那份」然后宣布达标。"""
    _write_trx(tmp_path, _healthy(900), name="good.trx")
    _write_trx(tmp_path, None, name="broken.trx", raw="<TestRun>")
    assert atc.check(tmp_path, 700, "Core") == 2


# ---------------------------------------------------------------- 不误红面
def test_healthy_trx_passes(tmp_path, capsys):
    _write_trx(tmp_path, _healthy(771))
    assert atc.check(tmp_path, 700, "Core") == 0
    assert "771" in capsys.readouterr().out


def test_attribute_casing_is_normalized(tmp_path):
    """真实 TRX 用小写属性名；归一大小写防「查不到键＝恒 0＝恒红」这种自伤形态。"""
    _write_trx(tmp_path, {"Total": 771, "Failed": 0})
    assert atc.check(tmp_path, 700, "Core") == 0


def test_counters_across_multiple_trx_are_summed(tmp_path):
    _write_trx(tmp_path, _healthy(500), name="one.trx")
    _write_trx(tmp_path, _healthy(300), name="two.trx")
    assert atc.check(tmp_path, 700, "Core") == 0


def test_main_resolves_relative_results_dir_against_repo_root(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(atc, "ROOT", tmp_path)
    _write_trx(tmp_path / "TestResults" / "core", _healthy(771))
    rc = atc.main(["--results-dir", "TestResults/core", "--minimum", "700", "--label", "Core"])
    assert rc == 0
    assert "[Core]" in capsys.readouterr().out


# ---------------------------------------------------------------- 控制台编码不得决定判定
# 第九轮 PR #137 的 CI 实证：`dotnet test` 782/782 全绿、下界达成，但 Actions 的
# Windows 控制台代码页不是 UTF-8 ⇒ print("✅ …") 抛 UnicodeEncodeError ⇒ 脚本退出 1 ⇒
# **通过路径**把 job 打红。门禁的输出编码必须是实现的一部分，否则它永远只会在
# 「测试其实通过了」那一条分支上失败。
def _cp1252_streams(monkeypatch):
    out, err = io.TextIOWrapper(io.BytesIO(), encoding="cp1252"), io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    return out, err


def test_success_message_survives_a_cp1252_console(tmp_path, monkeypatch):
    out, _err = _cp1252_streams(monkeypatch)
    _write_trx(tmp_path, _healthy(782))
    rc = atc.main(["--results-dir", str(tmp_path), "--minimum", "700", "--label", "Core"])
    out.flush()
    assert rc == 0, "非 ASCII 输出在 cp1252 控制台上抛异常 ⇒ 门禁在通过路径判红"
    assert b"782" in out.buffer.getvalue()


def test_environment_error_message_survives_a_cp1252_console(tmp_path, monkeypatch):
    _out, err = _cp1252_streams(monkeypatch)
    rc = atc.main(["--results-dir", str(tmp_path / "absent"), "--minimum", "700", "--label", "Core"])
    err.flush()
    assert rc == 2
    assert b"Core" in err.buffer.getvalue(), "exit 2 的说明必须打得出来，否则排查者只看到 traceback"


# ---------------------------------------------------------------- 接线锚
def _dotnet_test_blocks() -> list[tuple[str, str]]:
    """(位置标识, run 文本)——只收含 `dotnet test` 的步骤，含复合 action。"""
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    actions = ROOT / ".github" / "actions"
    if actions.is_dir():
        files += sorted(actions.glob("*/action.yml"))
    found: list[tuple[str, str]] = []
    for path in files:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for where, _name, run in _run_blocks(doc or {}):
            if "dotnet test" in run:
                found.append((path.name, run))
    return found


def test_scan_surface_is_not_empty():
    """扫描面为空＝锚自身失灵（R7-TOOL-04 同口径）。台账实测：4 个 workflow / 6 个步骤
    / 8 条 dotnet test（compat 与 contracts 各两步，native-policy 与 release 各一步两步）。
    数量对不上说明解析面漏了形态（复合 action、matrix、job 级 defaults）。"""
    blocks = _dotnet_test_blocks()
    assert len({name for name, _ in blocks}) == 4, "dotnet test 应分布在 compat/contracts/native-policy/release 四个 workflow"
    calls = sum(1 for _name, run in blocks for line in run.splitlines() if line.strip().startswith("dotnet test"))
    assert calls == 8, f"实见 {calls} 条 dotnet test 调用，与台账 8 条不符"


BLOCKS = _dotnet_test_blocks()
BLOCK_IDS = [f"{index}-{name.replace('.yml', '')}" for index, (name, _run) in enumerate(BLOCKS)]


@pytest.mark.parametrize("where,run", BLOCKS, ids=BLOCK_IDS)
def test_every_dotnet_test_is_followed_by_a_discovery_floor(where: str, run: str):
    problems: list[str] = []
    test_lines = [line.strip() for line in run.splitlines() if line.strip().startswith("dotnet test")]
    gate_lines = [
        line.strip()
        for line in run.splitlines()
        if "assert_test_counts.py" in line and not line.strip().startswith("#")
    ]
    if len(gate_lines) != len(test_lines):
        problems.append(f"{len(test_lines)} 条 dotnet test 只配到 {len(gate_lines)} 条发现数断言")

    for line in test_lines:
        if "--results-directory" not in line:
            problems.append("缺 --results-directory：TRX 落点随 SDK 版本漂，门禁无从定位")
        if "trx;" not in line:
            problems.append("缺 trx logger：没有结果文件就只看退出码＝原缺陷未闭合")

    seen_dirs: list[str] = []
    for line in gate_lines:
        minimum, label, results_dir = MINIMUM_RE.search(line), LABEL_RE.search(line), RESULTS_DIR_RE.search(line)
        if minimum is None or label is None:
            problems.append("断言行缺 --minimum 或 --label")
            continue
        suite = _suite_of(label.group(1))
        if suite == "?":
            problems.append(f"--label {label.group(1)} 认不出套件")
        elif int(minimum.group(1)) != EXPECTED_FLOORS[suite]:
            problems.append(f"{suite} 下界 {minimum.group(1)} 与登记值 {EXPECTED_FLOORS[suite]} 漂移")
        if results_dir is None:
            problems.append("断言行缺 --results-dir")
        else:
            seen_dirs.append(results_dir.group(1))
    if len(set(seen_dirs)) != len(seen_dirs):
        problems.append("同一步骤内两个套件共用 results 目录 ⇒ 计数互相污染")

    assert not problems, f"{where}: " + "；".join(problems)
