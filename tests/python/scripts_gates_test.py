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

import pytest
import verify_release_schema as vrs
import verify_vectors as vv
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


# ---------------------------------------------------------------- PY-233/246
class TestBootstrapVersionFloors:
    """PY-233（2026-10-01 审计）：dotnet/node 版本下限断言（此前只验存在）。"""

    def test_version_floor_parsing(self):
        mod = _load_dash_script(ROOT / "scripts" / "bootstrap-dev-environment" / "run.py")
        f = mod._version_floor_ok
        # dotnet 口径："10.0.100" >= (10,)
        assert f("10.0.100", (10,)) is True
        assert f("9.0.204", (10,)) is False
        assert f("11.0.100", (10,)) is True
        # node 口径："v21.7.0" >= (21,)
        assert f("v21.7.0", (21,)) is True
        assert f("v20.11.0", (21,)) is False
        assert f("v22.0.0", (21,)) is True
        # fail-closed：解析不出任何数字段 → 不达标
        assert f("unknown", (10,)) is False
        assert f("", (10,)) is False

    def test_check_enforces_floor(self, monkeypatch):
        # _check 对版本不足的工具必须报失败（不只是展示版本号）
        mod = _load_dash_script(ROOT / "scripts" / "bootstrap-dev-environment" / "run.py")
        monkeypatch.setattr(mod.shutil, "which", lambda exe: r"C:\fake\dotnet.exe")

        def fake_run(cmd, **k):
            return subprocess.CompletedProcess(cmd, 0, stdout="8.0.412\n", stderr="")

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        ok, detail = mod._check("dotnet", ["dotnet", "--version"], (10,))
        assert ok is False and "8.0.412" in detail and "10" in detail

    def test_check_accepts_floor_met(self, monkeypatch):
        mod = _load_dash_script(ROOT / "scripts" / "bootstrap-dev-environment" / "run.py")
        monkeypatch.setattr(mod.shutil, "which", lambda exe: r"C:\fake\node.exe")

        def fake_run(cmd, **k):
            return subprocess.CompletedProcess(cmd, 0, stdout="v21.7.0\n", stderr="")

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        ok, detail = mod._check("node", ["node", "--version"], (21,))
        assert ok is True and "v21.7.0" in detail


class TestMigrateProfileDataSkeleton:
    """PY-246（2026-10-01 审计）：migrate-profile-data 骨架零单测补齐
    （含 python -O 下断言剥离仍稳定——SP-038/085 语义由退出码承载）。"""

    @staticmethod
    def _load():
        return _load_dash_script(ROOT / "scripts" / "migrate-profile-data" / "run.py")

    def test_skeleton_returns_not_implemented(self, capsys):
        mod = self._load()
        assert mod.main([]) == mod.EXIT_NOT_IMPLEMENTED == 3
        out = capsys.readouterr().out
        assert "四步骤" not in out  # 只是措辞锚——真实锚在下方
        assert out.count("1. ") == 1 and "4. " in out  # 四步骤逐项打印

    def test_cli_args_accepted(self, capsys):
        mod = self._load()
        assert mod.main(["--source", "old", "--target", "new", "--dry-run"]) == 3
        out = capsys.readouterr().out
        assert "old" in out and "new" in out and "dry_run=True" in out

    def test_python_O_still_returns_not_implemented(self):
        # PY-246：`python -O` 剥离 assert 后骨架语义不变（退出码 3 不依赖断言）
        import subprocess as sp
        prog = ROOT / "scripts" / "migrate-profile-data" / "run.py"
        proc = sp.run([sys.executable, "-O", str(prog)],
                      capture_output=True, text=True, timeout=60, check=False)
        assert proc.returncode == 3

    def test_migration_steps_declared(self):
        mod = self._load()
        assert len(mod.MIGRATION_STEPS) == 4
        assert all(mod.MIGRATION_STEPS)


class TestVerifyAgentCatalogGate:
    """PY-246/254（2026-10-01 审计）：verify_agent_catalog.check() 四项断言单测
    （此前 CI 脚本零单测且只断言两项——门禁弱于 pytest 侧）。"""

    @staticmethod
    def _load():
        import verify_agent_catalog as vac
        return vac

    def test_real_catalog_passes(self):
        vac = self._load()
        doc = __import__("yaml").safe_load(
            vac.CATALOG.read_text(encoding="utf-8"))
        assert vac.check(doc) == []

    def test_missing_policy_version_reported(self):
        vac = self._load()
        doc = {"default_deny": True, "policy_version": "",
               "actions": [{"name": "a", "read_only": True,
                            "budget": {"max_actions": 5, "max_bytes": 64}}]}
        errors = vac.check(doc)
        assert any("policy_version" in e for e in errors)

    def test_bool_budget_rejected(self):
        # PY-251 口径：bool 是 int 子类——max_actions: true 不得过 CI 门禁
        vac = self._load()
        doc = {"default_deny": True, "policy_version": "1.0",
               "actions": [{"name": "a", "read_only": True,
                            "budget": {"max_actions": True, "max_bytes": 64}}]}
        errors = vac.check(doc)
        assert any("max_actions" in e and "正整数" in e for e in errors)

    def test_read_only_and_default_deny_enforced(self):
        vac = self._load()
        doc = {"default_deny": False, "policy_version": "1.0",
               "actions": [{"name": "a", "read_only": False,
                            "budget": {"max_actions": 5, "max_bytes": 64}}]}
        errors = vac.check(doc)
        assert any("default_deny" in e for e in errors)
        assert any("read_only" in e for e in errors)

    def test_main_exit_codes(self, monkeypatch, capsys):
        vac = self._load()
        import pathlib
        bad = pathlib.Path("bad-catalog-does-not-exist.yaml")
        monkeypatch.setattr(vac, "CATALOG", bad)
        assert vac.main() == 2


# ---------------------------------------------------------------- SP-155
class TestToolsBadJsonGuard:
    def test_artifact_set_missing_args_exit_2(self, monkeypatch):
        # PY-286（2026-10-02 审计）：手工 argv 改 argparse——必填 positional
        # 缺参自动 SystemExit(2)（0/1/2 退出码语义保持）
        from verify_artifact_set import main as vasm
        monkeypatch.setattr(sys, "argv", ["verify_artifact_set.py", "dist-only"])
        with pytest.raises(SystemExit) as excinfo:
            vasm()
        assert excinfo.value.code == 2

    def test_generate_sbom_missing_args_exit_2(self, monkeypatch):
        # PY-286：同上——generate_sbom 缺 output positional
        import generate_sbom as gs
        monkeypatch.setattr(sys, "argv", ["generate_sbom.py", "manifest-only"])
        with pytest.raises(SystemExit) as excinfo:
            gs.main()
        assert excinfo.value.code == 2

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

    def test_generate_sbom_percent_encoded_url_unquoted(self):
        # PY-226（2026-10-01 审计）：Release browser_url 对含空格资产名是
        # percent-encoded——SBOM 组件名须 unquote（与 verify_artifact_set 的
        # PY-210 口径一致），否则 SBOM 对账必失败
        sbom = gen_sbom_mod({"artifacts": [
            {"platform": "windows-x64",
             "url": "https://github.com/o/r/releases/download/v1/a%20b%20v2.zip",
             "sha256": "a" * 64}]})
        assert sbom["components"][0]["name"] == "a b v2.zip"


# ---------------------------------------------------------------- PY-220
class TestToolchainLocksAligned:
    def test_legacy_dev_lock_matches_ci_lock_versions(self):
        # PY-220（2026-10-01 审计）：legacy-python-guard 用 legacy dev 锁装
        # 工具却跑活跃树门禁——两把锁版本漂移即两套规则口径。共同工具的
        # pin 必须与根 requirements-ci.in 一致（锁定对齐，防再漂移）。
        import re as _re
        ci = (ROOT / "requirements-ci.in").read_text(encoding="utf-8")
        dev = (ROOT / "legacy" / "windows-pywebview" / "requirements-dev.txt").read_text(encoding="utf-8")

        def pins(text):
            return dict(_re.findall(r"^(ruff|mypy|bandit|pytest)==([\w.]+)$",
                                    text, _re.MULTILINE))

        ci_pins, dev_pins = pins(ci), pins(dev)
        assert ci_pins and dev_pins
        drift = {k: (dev_pins.get(k), ci_pins[k]) for k in ci_pins
                 if dev_pins.get(k) != ci_pins[k]}
        assert not drift, f"双锁版本漂移（dev vs ci.in）: {drift}"


# ---------------------------------------------------------------- PY-263
class TestActiveTreeGates:
    """PY-263（2026-10-02 审计）：活跃树 ruff/bandit 门禁命令单源封装
    （scripts/active_tree_gates.py——legacy-python-guard 两步骤的命令参数
    收拢点，workflow 后续直接调用；本地可随时复跑同一口径）。"""

    def test_gate_targets_match_workflow_face(self):
        # 目标面与 legacy-python-guard.yml 两步骤逐字一致（防封装漂移）
        import active_tree_gates as atg
        assert atg.RUFF_TARGETS == [
            "scripts", "release", "contracts", "agent",
            "validate_release.py", "tests", "core/rust-policy-core/bindings"]
        # SP-227（2026-10-02 审计）：bandit 面对齐 ruff 面（validate_release.py/
        # tests/bindings 此前不在 SAST 范围）
        assert atg.BANDIT_TARGETS == [
            "scripts", "release", "contracts", "agent",
            "validate_release.py", "tests", "core/rust-policy-core/bindings"]
        assert atg.BANDIT_EXTRA_ARGS == ["-ll", "-q"]

    def test_subcommand_dispatch_and_exit_codes(self, monkeypatch, capsys):
        import active_tree_gates as atg
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(atg.subprocess, "run", fake_run)
        assert atg.main(["ruff"]) == 0
        assert calls[-1][1] == "-m" and calls[-1][2] == "ruff" and calls[-1][3] == "check"
        assert calls[-1][4:] == atg.RUFF_TARGETS
        assert atg.main(["bandit"]) == 0
        assert "bandit.yaml" in calls[-1] and "-ll" in calls[-1] and "-r" in calls[-1]
        assert atg.main([]) == 0  # 默认 all = ruff + bandit
        assert len(calls) == 4
        # 统一经 sys.executable -m 调用（不依赖 PATH 安装形态）
        assert all(cmd[0] == sys.executable for cmd in calls)
        capsys.readouterr()  # 消费 gate 日志输出

    def test_failure_exit_code_propagates(self, monkeypatch, capsys):
        import active_tree_gates as atg

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, "", "")

        monkeypatch.setattr(atg.subprocess, "run", fake_run)
        assert atg.main(["ruff"]) == 1
        assert atg.main(["bandit"]) == 1
        assert atg.main([]) == 1  # all：任一失败即失败
        capsys.readouterr()

    def test_bad_gate_choice_rejected(self):
        import active_tree_gates as atg
        with pytest.raises(SystemExit) as excinfo:
            atg.main(["nope"])
        assert excinfo.value.code == 2


# 脚本可独立运行（无 pytest 环境时的最低验证）
if __name__ == "__main__":
    rc = subprocess.run([sys.executable, "-m", "pytest", __file__, "-q"],
                        check=False).returncode
    sys.exit(rc)
