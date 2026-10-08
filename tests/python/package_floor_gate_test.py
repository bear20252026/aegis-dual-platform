"""check_package_floors.py 的可失败性用例（第八轮 B7 同批门禁）。

口径与本仓其它门禁一致：先证明「注入它会红」，再声称它在管。
现树证据（写本门禁时实测）：重锁前 `python scripts/check_package_floors.py` 在
三把锁上都报 `SQLitePCLRaw.bundle_e_sqlite3 resolved=2.1.11 低于下界 2.1.12`
——这就是 R8-DEPS-3 那条「NU1903 修复只做了 3/4」的机器形态；重锁补齐后转绿。
"""

from __future__ import annotations

import json

import check_package_floors as cpf


def make_lock(tmp_path, name: str, packages: dict[str, str]) -> None:
    """写一份最小可用锁：NuGet lock v1 的图值直接是包映射（无 packages 包装层）。"""
    graph = {
        package: {"type": "Direct", "requested": f"[{version}, )", "resolved": version}
        for package, version in packages.items()
    }
    payload = {"version": 1, "dependencies": {"net10.0-windows7.0": graph}}
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_version_comparison_is_numeric_and_pads_missing_segments():
    assert cpf.at_least("2.1.12", "2.1.12")
    assert cpf.at_least("2.1.13", "2.1.12")
    assert cpf.at_least("3.0.0", "2.1.12")
    assert cpf.at_least("2.1", "2.1.0")  # 缺段补 0，不按字符串比
    assert not cpf.at_least("2.1.11", "2.1.12")
    assert not cpf.at_least("2.1", "2.1.1")
    # 预发布/元数据尾段截断后按数值段判（"2.1.12-beta" 的下界判据是 2.1.12）
    assert cpf.parse_version("2.1.12-beta.3") == (2, 1, 12)


def test_below_floor_is_reported(tmp_path):
    make_lock(tmp_path, "a-lock.json", {
        "SQLitePCLRaw.bundle_e_sqlite3": "2.1.11",
        "SQLitePCLRaw.core": "2.1.12",
        "Microsoft.Web.WebView2": "1.0.2903.40",
    })
    problems = cpf.violations([tmp_path / "a-lock.json"], cpf.FLOORS)
    assert any("bundle_e_sqlite3" in p and "2.1.11" in p for p in problems), problems
    assert not any("Microsoft.Web.WebView2" in p for p in problems)


def test_exact_floor_and_newer_are_clean(tmp_path):
    make_lock(tmp_path, "ok-lock.json", {
        "SQLitePCLRaw.bundle_e_sqlite3": "2.1.12",
        "SQLitePCLRaw.core": "2.1.13",
        "SQLitePCLRaw.provider.e_sqlite3": "2.1.12",
        "SQLitePCLRaw.lib.e_sqlite3": "2.1.12",
        "Microsoft.Web.WebView2": "1.0.4258.31",
    })
    assert cpf.violations([tmp_path / "ok-lock.json"], cpf.FLOORS) == []


def test_floor_entry_that_appears_in_no_lock_is_a_failure(tmp_path):
    """下界表里写了、任何锁里都没命中 ⇒ 门禁在查不存在的对象（恒绿的另一种形态）。"""
    make_lock(tmp_path, "one-lock.json", {"Microsoft.Web.WebView2": "1.0.2903.40"})
    problems = cpf.violations([tmp_path / "one-lock.json"], cpf.FLOORS)
    silent = [p for p in problems if "没出现" in p]
    assert len(silent) == 4, silent  # SQLitePCLRaw 四件全缺席
    assert all("任何一把锁" in p or "都没出现" in p for p in silent)


def test_empty_lock_surface_is_environment_error(tmp_path, capsys):
    assert cpf.run(locks=[], floors=cpf.FLOORS) == 2
    assert "环境错误" in capsys.readouterr().out


def test_empty_floor_table_is_not_a_pass(tmp_path, capsys):
    make_lock(tmp_path, "any-lock.json", {"Microsoft.Web.WebView2": "1.0.2903.40"})
    assert cpf.run(locks=[tmp_path / "any-lock.json"], floors={}) == 2
    assert "空心化" in capsys.readouterr().out


def test_the_real_tree_meets_the_floors():
    """实树判据：重锁落地后这条必须绿；它红着就说明「补钉 4/4」没真到货。

    与本文件其它用例不同，这条不喂 tmp_path——它判的是仓库里那三把锁本身。"""
    locks = cpf.vlr.list_lock_files()
    assert len(locks) == 3, f"锁文件面应为三把，实得 {[str(p) for p in locks]}"
    assert cpf.violations(locks, cpf.FLOORS) == []
