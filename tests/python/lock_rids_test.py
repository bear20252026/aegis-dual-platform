"""`scripts/verify_lock_rids.py` 的可失败性用例（第八轮 B7 前置门禁）。

口径与本仓其它门禁一致：**先证明掏空它会红，再声称它在管**。每注入一种「锁被
restore 改坏」的真实形态，都对应项目记忆里记过的一次事故：只删不增的 RID 块、
整块空掉、原生件被 RID 图漏掉、以及扫描面莫名变空（在错误目录执行）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import verify_lock_rids as vlr

TFM = vlr.TARGET_FRAMEWORKS[0]
RID_KEY = f"{TFM}/{vlr.RUNTIME_ID}"


def base_lock() -> dict:
    """一份**合规**的最小锁：中性图含全部出货依赖，RID 图含两件按 RID 解析的原生件。"""
    def entry(name: str) -> dict:
        return {
            name: {
                "type": "Direct",
                "requested": name,
                "resolved": "1.0.0",
                "contentHash": "sha512-" + name,
            }
        }

    neutral: dict = {}
    for name in vlr.REQUIRED_PINNED:
        neutral |= entry(name)
    rid: dict = {}
    for name in vlr.REQUIRED_IN_RID:
        rid |= entry(name)
    return {"version": 1, "dependencies": {TFM: neutral, RID_KEY: rid}}


def write_lock(root: Path, payload: dict, name: str = "packages.lock.json") -> Path:
    target = root / "windows" / "src" / "App" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def problems_for(payload: dict, tmp_path: Path) -> list[str]:
    path = write_lock(tmp_path, payload)
    return vlr.check_lock(path)


def test_wellformed_lock_passes(tmp_path: Path) -> None:
    assert problems_for(base_lock(), tmp_path) == []


def test_missing_rid_block_is_a_violation(tmp_path: Path) -> None:
    # 那次「只删不增」的 restore 就是这个形态
    payload = base_lock()
    del payload["dependencies"][RID_KEY]
    problems = problems_for(payload, tmp_path)
    assert any("缺 RID 块" in line for line in problems), problems


def test_empty_rid_block_is_a_violation(tmp_path: Path) -> None:
    payload = base_lock()
    payload["dependencies"][RID_KEY] = {}
    problems = problems_for(payload, tmp_path)
    assert any("包映射为空" in line for line in problems), problems


def test_rid_block_missing_native_package_is_a_violation(tmp_path: Path) -> None:
    payload = base_lock()
    stolen = payload["dependencies"][RID_KEY].pop("SQLitePCLRaw.lib.e_sqlite3")
    payload["dependencies"][TFM] |= {
        "SQLitePCLRaw.lib.e_sqlite3": stolen,
    }
    problems = problems_for(payload, tmp_path)
    assert any("缺按 RID 解析的原生件" in line for line in problems), problems


def test_shipping_dep_absent_from_whole_lock_is_a_violation(tmp_path: Path) -> None:
    payload = base_lock()
    del payload["dependencies"][TFM]["Microsoft.Data.Sqlite"]
    problems = problems_for(payload, tmp_path)
    assert any("锁里没有这些出货依赖" in line for line in problems), problems


def test_wrong_lock_version_is_a_violation(tmp_path: Path) -> None:
    payload = base_lock()
    payload["version"] = 2
    problems = problems_for(payload, tmp_path)
    assert any("version 不是 1" in line for line in problems), problems


def test_missing_framework_block_is_a_violation(tmp_path: Path) -> None:
    payload = base_lock()
    del payload["dependencies"][TFM]
    problems = problems_for(payload, tmp_path)
    assert any("缺目标框架块" in line for line in problems), problems


def test_unparsable_lock_is_a_violation(tmp_path: Path) -> None:
    path = write_lock(tmp_path, base_lock())
    path.write_text("{not json", encoding="utf-8")
    problems = vlr.check_lock(path)
    assert any("无法解析" in line for line in problems), problems


def test_bom_prefixed_lock_still_parses(tmp_path: Path) -> None:
    # NuGet 实测可能写出 BOM；用 utf-8 读会让 json.loads 抛「无法解析」——
    # 一条假红会把人推向「那一定是我读错了」，最终演变成放宽门禁。
    path = write_lock(tmp_path, base_lock())
    raw = path.read_text(encoding="utf-8")
    path.write_bytes(b"\xef\xbb\xbf" + raw.encode("utf-8"))
    assert vlr.check_lock(path) == []


def test_real_repo_locks_pass() -> None:
    assert vlr.run(False) == 0, "实树锁必须通过——否则本门禁一到货就红"


def test_empty_scan_surface_is_environment_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vlr, "list_lock_files", lambda: [])
    assert vlr.run(False) == 2


def test_build_output_locks_are_not_scanned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # obj/bin 里的副本不是事实源（它们是上次 restore 的产物）：
    # 若被收进扫描面，删除源码树里的锁也能「通过」——判定面自己缩水
    monkeypatch.setattr(vlr, "ROOT", tmp_path)
    junk = tmp_path / "windows" / "src" / "App" / "obj"
    junk.mkdir(parents=True)
    (junk / "packages.lock.json").write_text(json.dumps(base_lock()), encoding="utf-8")
    assert vlr.list_lock_files() == []
