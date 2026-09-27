# scripts_gates_test.py —— 脚本门禁类单测（pytest）。
# 覆盖审计条目（本批次新增）：
#   PY-187 verify_vectors 显式 failures 收集（含 python -O 子进程用例——
#         断言剥离后门禁仍 fail-closed）
#   PY-190 scripts/verify_vectors.py 与 scripts/verify_release_schema.py 单测
#         （tmp_path 风格）
#   PY-200 run-security-e2e 完整透传 stdout
#   PY-201 bootstrap-dev-environment 统一 sys.executable 检查
#   SP-155 tools 脚本 main() 坏 JSON → exit 2 + 文件名上下文
# SP-161：sys.path 注入统一走 conftest.py。
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import verify_vectors as vv
import verify_release_schema as vrs
from generate_sbom import generate_sbom as gen_sbom_mod

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- PY-187/190
class TestVerifyVectors:
    def test_single_step_bad_value_collected(self, tmp_path):
        # PY-187：非法 expected 值显式进 failures（不再依赖裸 assert）
        failures: list[str] = []
        vv.validate_vector({"expected": "explode"}, "x.json", failures)
        assert failures and "单步协议 expected 值非法" in failures[0]

    def test_multi_step_bad_value_collected(self, tmp_path):
        failures: list[str] = []
        vv.validate_vector({"expected_request": "maybe"}, "x.json", failures)
        assert failures and "多步流" in failures[0]

    def test_vector_without_assertion_collected(self, tmp_path):
        failures: list[str] = []
        vv.validate_vector({"url": "https://a"}, "x.json", failures)
        assert failures and "缺少断言字段" in failures[0]

    def test_valid_vectors_produce_no_failures(self):
        failures: list[str] = []
        vv.validate_vector({"expected": "deny"}, "x.json", failures)
        vv.validate_vector({"expected_approve": "allow",
                            "expected_consume_code": "E_X"}, "x.json", failures)
        assert failures == []

    def test_main_rejects_bad_vector_file(self, tmp_path, monkeypatch):
        # PY-190：tmp_path 合成 contracts 树 → main() 返回 1 并列出原因
        vectors = tmp_path / "contracts" / "vectors"
        vectors.mkdir(parents=True)
        (vectors / "bad.json").write_text(
            json.dumps({"vectors": [{"expected": "nonsense"}]}), encoding="utf-8")
        monkeypatch.setattr(vv, "ROOT", tmp_path)
        assert vv.main() == 1

    def test_main_accepts_synthetic_good_tree(self, tmp_path, monkeypatch, capsys):
        vectors = tmp_path / "contracts" / "vectors"
        vectors.mkdir(parents=True)
        (vectors / "ok.json").write_text(
            json.dumps({"vectors": [{"expected": "deny"},
                                    {"expected_evaluate": "require_confirmation"}]}),
            encoding="utf-8")
        monkeypatch.setattr(vv, "ROOT", tmp_path)
        assert vv.main() == 0

    def test_oversize_anchor_guard_still_enforced(self, tmp_path, monkeypatch):
        # 锚点守卫回归：url-origin-invalid.json 无锚点 → fail（PY-078 语义）
        vectors = tmp_path / "contracts" / "vectors"
        vectors.mkdir(parents=True)
        (vectors / "url-origin-invalid.json").write_text(
            json.dumps({"vectors": [{"url": "https://a/", "expected": "deny"}]}),
            encoding="utf-8")
        monkeypatch.setattr(vv, "ROOT", tmp_path)
        assert vv.main() == 1

    def test_python_O_still_fails_on_bad_vectors(self, tmp_path):
        # PY-187 核心：`python -O` 剥离 assert 后门禁必须仍然 fail
        #（把脚本复制进合成树——ROOT 由脚本位置推导，无需 monkeypatch）
        prog_dir = tmp_path / "prog"
        prog_dir.mkdir()
        shutil.copy2(ROOT / "scripts" / "verify_vectors.py", prog_dir / "verify_vectors.py")
        vectors = tmp_path / "contracts" / "vectors"
        vectors.mkdir(parents=True)
        (vectors / "bad.json").write_text(
            json.dumps({"vectors": [{"expected": "explode-me"}]}), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-O", str(prog_dir / "verify_vectors.py")],
            capture_output=True, text=True, timeout=60, check=False)
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "explode-me" in proc.stdout

    def test_python_O_passes_on_good_vectors(self, tmp_path):
        prog_dir = tmp_path / "prog"
        prog_dir.mkdir()
        shutil.copy2(ROOT / "scripts" / "verify_vectors.py", prog_dir / "verify_vectors.py")
        vectors = tmp_path / "contracts" / "vectors"
        vectors.mkdir(parents=True)
        (vectors / "ok.json").write_text(
            json.dumps({"vectors": [{"expected": "deny"}]}), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-O", str(prog_dir / "verify_vectors.py")],
            capture_output=True, text=True, timeout=60, check=False)
        assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------------------------------------------------------------- PY-190
class TestVerifyReleaseSchema:
    def test_valid_release_json_passes(self, tmp_path, monkeypatch):
        # PY-190：以真实 release.json 为合法样本（tmp_path 内运行）
        real = json.loads((ROOT / "shared" / "release.json").read_text(encoding="utf-8"))
        target = tmp_path / "release.json"
        target.write_text(json.dumps(real, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(vrs, "TARGET_PATH", target)
        assert vrs.main() == 0

    def test_violation_reported_per_json_path(self, tmp_path, monkeypatch):
        real = json.loads((ROOT / "shared" / "release.json").read_text(encoding="utf-8"))
        real["product"] = "Not-Aegis"  # 枚举违约
        target = tmp_path / "release.json"
        target.write_text(json.dumps(real, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(vrs, "TARGET_PATH", target)
        assert vrs.main() == 1

    def test_bad_target_json_returns_1(self, tmp_path, monkeypatch):
        target = tmp_path / "release.json"
        target.write_text("{ broken", encoding="utf-8")
        monkeypatch.setattr(vrs, "TARGET_PATH", target)
        assert vrs.main() == 1

    def test_missing_target_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vrs, "TARGET_PATH", tmp_path / "ghost.json")
        assert vrs.main() == 1


# ---------------------------------------------------------------- PY-200
def _load_dash_script(rel: Path):
    """目录名含连字符（run-security-e2e）——importlib 按路径装载。"""
    spec = importlib.util.spec_from_file_location(rel.stem, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRunSecurityE2ePassthrough:
    def test_full_stdout_passed_through(self, capsys, monkeypatch):
        # PY-200：此前只打印 stdout 最后一行——完整输出必须透传
        #（对齐 codegen-contracts/run.py）
        mod = _load_dash_script(ROOT / "scripts" / "run-security-e2e" / "run.py")

        def fake_run(*a, **k):
            return subprocess.CompletedProcess(
                a[0], 0, stdout="line-one\nline-two\nline-three\n", stderr="")

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        assert mod.main() == 0
        out = capsys.readouterr().out
        assert "line-one" in out and "line-two" in out and "line-three" in out

    def test_failure_returns_1(self, capsys, monkeypatch):
        mod = _load_dash_script(ROOT / "scripts" / "run-security-e2e" / "run.py")

        def fake_run(*a, **k):
            return subprocess.CompletedProcess(a[0], 3, stdout="boom", stderr="err")

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        assert mod.main() == 1


# ---------------------------------------------------------------- PY-201
class TestBootstrapPythonCheck:
    def test_current_interpreter_passes(self):
        mod = _load_dash_script(ROOT / "scripts" / "bootstrap-dev-environment" / "run.py")
        ok, detail = mod._check_python()
        assert ok is True
        assert str(sys.executable) in detail

    def test_unlocatable_interpreter_fails(self, monkeypatch):
        mod = _load_dash_script(ROOT / "scripts" / "bootstrap-dev-environment" / "run.py")
        monkeypatch.setattr(mod.shutil, "which", lambda exe: None)
        ok, _detail = mod._check_python()
        assert ok is False

    def test_version_below_minimum_fails(self, monkeypatch):
        # PY-201：版本断言——< 3.12 必须失败（此前注释声称 3.12 实际不校验）
        mod = _load_dash_script(ROOT / "scripts" / "bootstrap-dev-environment" / "run.py")
        monkeypatch.setattr(sys, "version_info", (3, 11, 9))
        ok, detail = mod._check_python()
        assert ok is False and "3.11" in detail

    def test_main_uses_unified_python_check(self, capsys, monkeypatch):
        mod = _load_dash_script(ROOT / "scripts" / "bootstrap-dev-environment" / "run.py")
        monkeypatch.setattr(mod.shutil, "which", lambda exe: None)  # dotnet/cargo 缺失
        rc = mod.main()
        assert rc == 1
        out = capsys.readouterr().out
        assert "python" in out


# ---------------------------------------------------------------- SP-155
class TestToolsBadJsonGuard:
    def test_artifact_set_main_bad_json_exit_2(self, tmp_path, capsys, monkeypatch):
        from verify_artifact_set import main as vasm
        bad = tmp_path / "manifest-bad.json"
        bad.write_text("{ nope", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["verify_artifact_set.py", str(tmp_path), str(bad)])
        assert vasm() == 2
        # SP-155：报告含文件名上下文（不再是原始 traceback）
        assert "manifest-bad.json" in capsys.readouterr().out

    def test_generate_sbom_main_bad_json_exit_2(self, tmp_path, capsys, monkeypatch):
        import generate_sbom as gs
        bad = tmp_path / "manifest-bad.json"
        bad.write_text("{ nope", encoding="utf-8")
        out = tmp_path / "out.cdx.json"
        monkeypatch.setattr(sys, "argv", ["generate_sbom.py", str(bad), str(out)])
        assert gs.main() == 2
        assert "manifest-bad.json" in capsys.readouterr().out

    def test_generate_sbom_roundtrip(self, tmp_path, monkeypatch):
        # SBOM 生成正常路径回归（SP-155 守卫不得误伤）
        import generate_sbom as gs
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({"artifacts": [
            {"platform": "windows-x64", "url": "https://c/a.zip", "sha256": "a" * 64}]}),
            encoding="utf-8")
        out = tmp_path / "sbom.cdx.json"
        monkeypatch.setattr(sys, "argv", ["generate_sbom.py", str(manifest), str(out)])
        assert gs.main() == 0
        doc = json.loads(out.read_text(encoding="utf-8"))
        assert doc["bomFormat"] == "CycloneDX"
        assert gen_sbom_mod({"artifacts": []})["components"] == []


# 脚本可独立运行（无 pytest 环境时的最低验证）
if __name__ == "__main__":
    rc = subprocess.run([sys.executable, "-m", "pytest", __file__, "-q"],
                        check=False).returncode
    sys.exit(rc)
