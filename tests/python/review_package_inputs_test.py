"""R8-PY-04（第八轮审计 2026-10-06）常驻门禁：评审包的**输入面**不得静默缩水。

`scripts/build_review_package.py` 的 `TREE_COPY`/`FILE_COPY` 是"交付给外部评审的
源码面"的唯一清单。修复前两处 `if not …exists(): continue` 把缺席条目静默跳过：

- 登记在册的 `windows/packaging` 本就不存在（`windows/README.md:30` 早已记载，
  安装包定义在 `docs/release/AegisSetup-CSharp.iss`）——死条目挂了多轮无人知；
- 真正的危害是它的同型：`contracts`/`docs`/`.github/workflows` 任一根改名或移动，
  评审包就少一整棵树，而包看上去仍是完整交付物、`--check` 照样绿（它比的是
  同 commit 的两次生成，见模块 docstring 的 R8-PY-04② 更正）。

因此本文件的判定面有两层：①**现树对账**——清单里每个条目必须真实存在（改名即红）；
②**可失败面**——注入一个不存在的条目必须硬失败（否则①只是在断言"脚本会跳过"）。
"""

from __future__ import annotations

import build_review_package as brp
import pytest


def test_registered_trees_exist_in_the_real_repo():
    missing = [canonical for canonical, _ in brp.TREE_COPY if not (brp.ROOT / canonical).is_dir()]
    assert not missing, f"TREE_COPY 指向不存在的根：{missing}"


def test_registered_single_files_exist_in_the_real_repo():
    missing = [name for name in brp.FILE_COPY if not (brp.ROOT / name).is_file()]
    assert not missing, f"FILE_COPY 指向不存在的文件：{missing}"


def test_dead_packaging_entry_is_not_resurrected():
    # 反向锚：windows/packaging 从未存在过，登记它等于给"静默跳过"留一条活路
    assert "windows/packaging" not in {canonical for canonical, _ in brp.TREE_COPY}


def test_missing_tree_root_fails_closed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "core").mkdir()
    monkeypatch.setattr(brp, "ROOT", tmp_path)
    monkeypatch.setattr(brp, "TREE_COPY", [("core", "core"), ("contracts", "contracts")])
    monkeypatch.setattr(brp, "FILE_COPY", [])
    with pytest.raises(SystemExit) as raised:
        brp.collect_sources()
    assert "INPUT-FAIL" in str(raised.value)
    assert "contracts" in str(raised.value)


def test_missing_single_file_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(brp, "ROOT", tmp_path)
    monkeypatch.setattr(brp, "TREE_COPY", [])
    monkeypatch.setattr(brp, "FILE_COPY", ["SECURITY.md"])
    with pytest.raises(SystemExit) as raised:
        brp.collect_sources()
    assert "SECURITY.md" in str(raised.value)


def test_present_inputs_are_collected_not_skipped(tmp_path, monkeypatch):
    # 与上两条配对：只有"存在即收集"成立时，fail-closed 才不是把判定换成恒空
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "lib.rs").write_text("fn main() {}\n", encoding="utf-8")
    (tmp_path / "SECURITY.md").write_text("# policy\n", encoding="utf-8")
    monkeypatch.setattr(brp, "ROOT", tmp_path)
    monkeypatch.setattr(brp, "TREE_COPY", [("core", "core")])
    monkeypatch.setattr(brp, "FILE_COPY", ["SECURITY.md"])
    collected = {p.as_posix() for p in brp.collect_sources()}
    assert collected == {"core/lib.rs", "SECURITY.md"}


def test_check_no_longer_claims_source_sync():
    # R8-PY-04②：--check 比的是同 commit 两次生成（评审包快照不入库），旧 docstring
    # 却把它写成"保证与当前源码同步"。声明真相化后不得再出现该表述。
    assert "保证与当前源码同步" not in brp.__doc__
