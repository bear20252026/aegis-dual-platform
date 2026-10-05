# verify_vectors_surface_test.py —— R7-TOOL-04 / R7-TOOL-06（第七轮 2026-10-04）。
#
# 从 scripts_gates_test.py 拆出（该文件已在行数基线内，只许减不许增——新增判定
# 用例另立文件，不挤占基线额度）。本文件测的是**门禁自身的入口完整性**：
# ① 契约目录缺失/缩减不得静默通过；② 超长 URL 锚点不得绑定文件名；
# ③ 安全 e2e 入口与红队套件在 -O 下必须响亮失败，不得给「跑过了」的假信号。
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import verify_vectors as vv

REPO = Path(__file__).resolve().parents[2]


def _load_run_script():
    """以 dash 目录里的 run.py 为模块名加载（目录名含连字符，不能直接 import）。"""
    import importlib.util

    path = REPO / "scripts" / "run-security-e2e" / "run.py"
    spec = importlib.util.spec_from_file_location("aegis_run_security_e2e", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _synthetic_tree(tmp_path, schema_n: int, vector_n: int, anchor: bool):
    vectors = tmp_path / "contracts" / "vectors"
    vectors.mkdir(parents=True)
    schemas = tmp_path / "contracts" / "schemas"
    schemas.mkdir(parents=True)
    for i in range(schema_n):
        (schemas / f"s{i}.schema.json").write_text('{"type": "object"}', encoding="utf-8")
    for i in range(vector_n):
        body = [{"expected": "deny"}]
        if anchor and i == 0:
            body.append({"url": "https://example.org/" + vv.OVERSIZE_ANCHOR,
                         "expected": "deny"})
        (vectors / f"v{i}.json").write_text(
            json.dumps({"vectors": body}), encoding="utf-8")
    return vectors, schemas


# ---------- ① 扫描面完整性 ----------


def test_missing_contract_dir_is_not_silently_green(tmp_path, monkeypatch, capsys):
    """R7-TOOL-04：contracts 目录整个消失必须红——0 文件不等于全部通过。"""
    monkeypatch.setattr(vv, "ROOT", tmp_path)
    assert vv.main() == 1
    assert "契约目录缺失" in capsys.readouterr().out


def test_reduced_vector_surface_below_floor_fails(tmp_path, monkeypatch, capsys):
    """R7-TOOL-04：删/改名向量文件即缩减契约面——必须撞下界，不能静默减面。"""
    _synthetic_tree(tmp_path, schema_n=2, vector_n=2, anchor=False)
    monkeypatch.setattr(vv, "ROOT", tmp_path)
    assert vv.main() == 1
    assert "低于下界" in capsys.readouterr().out


def test_floors_match_the_real_surface():
    """下界与真实面对齐——写小了是空转，写大了是永远红。"""
    assert len(list((REPO / "contracts" / "schemas").glob("*.json"))) >= vv.MIN_FILES["schemas"]
    assert len(list((REPO / "contracts" / "vectors").glob("*.json"))) >= vv.MIN_FILES["vectors"]


# ---------- ② 锚点去文件名化 ----------


def test_anchor_survives_rename(tmp_path, monkeypatch):
    """R7-TOOL-04：锚点判定此前按文件名早退（`path.name != OVERSIZE_VECTOR_FILE`），
    把含锚点的向量改名、内容原样移动，即静默摘掉锚点且 exit 0（实测）。
    现按内容统计、全树恰好一次——文件名不参与判定。"""
    _synthetic_tree(tmp_path, schema_n=1, vector_n=1, anchor=True)
    first = sorted((tmp_path / "contracts" / "vectors").glob("*.json"))[0]
    first.rename(tmp_path / "contracts" / "vectors" / "renamed-to-something-else.json")
    monkeypatch.setattr(vv, "ROOT", tmp_path)
    monkeypatch.setattr(vv, "MIN_FILES", {"schemas": 1, "vectors": 1})
    # R8-PY-02 的总条目下界按真实面写死，合成树（2 条）须显式核减才可比。
    monkeypatch.setattr(vv, "MIN_VECTOR_ENTRIES", 2)
    assert vv.main() == 0


def test_anchor_missing_across_tree_fails(tmp_path, monkeypatch, capsys):
    _synthetic_tree(tmp_path, schema_n=1, vector_n=1, anchor=False)
    monkeypatch.setattr(vv, "ROOT", tmp_path)
    monkeypatch.setattr(vv, "MIN_FILES", {"schemas": 1, "vectors": 1})
    assert vv.main() == 1
    assert "全树命中 0 次" in capsys.readouterr().out


# ---------- ③ -O 入口完整性 ----------


def test_optimize_environment_is_refused(capsys, monkeypatch):
    """R7-TOOL-06：PYTHONOPTIMIZE 会被 subprocess 继承，被驱动的断言全被剥离
    ——本入口必须拒绝该模式，而不是打印「✅ 安全 e2e 通过」。"""
    mod = _load_run_script()
    monkeypatch.setenv("PYTHONOPTIMIZE", "1")
    assert mod.main() == 2
    assert "不接受 -O" in capsys.readouterr().err


@pytest.mark.parametrize("rel", ["agent/tests/redteam_test.py",
                                 "agent/tests/redteam_e2e_test.py"])
def test_redteam_suites_refuse_direct_execution(rel):
    """R7-TOOL-06：手工运行器已删除。裸 `assert` 套件在 `-O` 下运行曾打印
    ALL OK、exit 0（实测），现无论是否 -O，直接执行一律 rc=2 并指向 pytest。"""
    for flag in ("-O",):
        proc = subprocess.run([sys.executable, flag, str(REPO / rel)],
                              capture_output=True, text=True, timeout=180, check=False)
        assert proc.returncode == 2, f"{flag} {rel}: rc={proc.returncode} {proc.stdout[-200:]}"
        assert "pytest" in proc.stderr, proc.stderr
    # 非 -O 直接执行同样拒绝（消除「忘了加 -O 就静默全绿」的支路）
    proc = subprocess.run([sys.executable, str(REPO / rel)],
                          capture_output=True, text=True, timeout=180, check=False)
    assert proc.returncode == 2, proc.stdout[-200:]


def test_e2e_entry_actually_passes_on_current_tree():
    """正向对照：不带 -O 时整条安全 e2e 必须真跑通（防止入口改成恒失败）。"""
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "run-security-e2e" / "run.py")],
                          capture_output=True, text=True, timeout=600, check=False,
                          cwd=str(REPO))
    assert proc.returncode == 0, proc.stdout[-800:] + proc.stderr[-800:]
    assert "安全 e2e 通过" in proc.stdout



# ---------- 迁移自 scripts_gates_test.py（PY-187/PY-078 原有用例，判定不变） ----------


def test_main_accepts_synthetic_good_tree(tmp_path, monkeypatch):
    """原 TestVerifyVectors::test_main_accepts_synthetic_good_tree——判定不变，
    只因 R7-TOOL-04 的下界/锚点新增要求而移到这里（完整合成树须带锚点）。"""
    vectors = tmp_path / "contracts" / "vectors"
    schemas = tmp_path / "contracts" / "schemas"
    vectors.mkdir(parents=True)
    schemas.mkdir(parents=True)
    (schemas / "ok.schema.json").write_text('{"type": "object"}', encoding="utf-8")
    (vectors / "ok.json").write_text(
        json.dumps({"vectors": [{"expected": "deny"},
                                {"expected_evaluate": "require_confirmation"},
                                {"url": "https://example.org/" + vv.OVERSIZE_ANCHOR,
                                 "expected": "deny"}]}),
        encoding="utf-8")
    monkeypatch.setattr(vv, "ROOT", tmp_path)
    monkeypatch.setattr(vv, "MIN_FILES", {"schemas": 1, "vectors": 1})
    monkeypatch.setattr(vv, "MIN_VECTOR_ENTRIES", 3)
    assert vv.main() == 0


def test_python_O_passes_on_good_vectors():
    """PY-187 原用例改跑真实面：要证的是「-O 不摘掉判定」，与小合成树无关
    ——verify_vectors 由自身文件位置推 ROOT，故须跑仓库内副本。"""
    proc = subprocess.run(
        [sys.executable, "-O", str(REPO / "scripts" / "verify_vectors.py")],
        capture_output=True, text=True, timeout=120, check=False, cwd=str(REPO))
    assert proc.returncode == 0, proc.stdout + proc.stderr
