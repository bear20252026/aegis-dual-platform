# dotnet_test_count_gate_test.py —— R9-CI-9（第九轮 2026-10-10）：测试**发现数**下界
# 门禁脚本自身的判定面（掏空它会红 + 健康 TRX 不误红 + 控制台编码不决定判定）。
#
# 失效模式：`dotnet test` 的退出码只表达「跑到的都没失败」，零发现同样退 0。本仓 CI
# 的八处调用（compat / contracts / native-policy-artifacts / release-windows）此前只看
# 退出码，于是「绿」的含义是「没有失败的测试」，不是「782 个判定都跑过」。触发点是
# 真实的：同一批工作里 Microsoft.NET.Test.Sdk 17.14→18.10、xunit.runner.visualstudio
# 3.1.5→4.0.1 都是跨 major 的**测试宿主**升级——发现器与框架不同代时最坏结果就是
# 零发现全绿，而 PR 里没有任何人会察觉。
#
# 按本仓固定口径（R7-TOOL-04 / R8-PY-02）：不光证「现在绿」，必须证「掏空它会红」，
# 并证「不误红」（健康 TRX 必须过）。「门禁写好了但没接线」那第四种失效由
# tests/python/dotnet_suite_composite_wiring_test.py 判（项 13(a) 之后判定面在那边）。
from __future__ import annotations

import io
import sys
from pathlib import Path

import assert_test_counts as atc

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

TRX_NS = "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"

# 套件 → 登记下界（本轮实测 Core 782、Broker 189，下界取有界余量）。workflow 里的数字与本表
# 不一致即红——防「某一处被人顺手调松」。
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
# 定稿项 13(a)（R9-B16）把八条 dotnet test 的命令面抽进
# .github/actions/dotnet-test-suite，调用点只剩「测哪个工程、落在哪个目录、下界多少」。
# 「接线是否还在」这条锚因此改判 uses: 调用点与本 action 正文，见
# tests/python/dotnet_suite_composite_wiring_test.py（同批随抽取迁出，避免两个判定面
# 挤在同一份 300 行里各改一半）。
