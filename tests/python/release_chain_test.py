# release_chain_test.py —— 发布链离线单测（pytest；PY-149 基建落地）
# PY-004：_version_tuple 预发布段参与比较（防回滚绕过锁定）。
# PY-024：verify_artifact_set 跨平台同名不覆盖 + 递归枚举。
# SP-160（2026-09-26 审计）：_version_tuple 用例单源化——原
# release_tools_test.py 的重复用例类已删，全部并入本文件。
# PY-184/199/210/212 + SP-144：本批次新增发布链用例。
# SP1 批（审计 2026-09-23 清单）：SP-030 verify_provenance mock subprocess
# 单测；SP-031 release-verify.json 测试向量元一致性门禁。
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

import pytest
from update_verifier import UpdateRejected, _version_tuple
from verify_artifact_set import verify_artifact_set
from verify_provenance import verify_provenance as run_provenance


class TestVersionPrereleaseOrdering:
    def test_release_beats_prerelease_same_core(self):
        # PY-004 核心：此前 2.2.0-beta.1 == 2.2.0（预发布段被丢弃）
        assert _version_tuple("2.2.0") > _version_tuple("2.2.0-beta.1")

    def test_numeric_prerelease_segments_compare_numerically(self):
        assert _version_tuple("1.0.0-beta.2") > _version_tuple("1.0.0-beta.1")
        assert _version_tuple("1.0.0-beta.10") > _version_tuple("1.0.0-beta.9")

    def test_numeric_identifier_lower_than_literal(self):
        # SemVer：数字标识 < 字面标识
        assert _version_tuple("1.0.0-1") < _version_tuple("1.0.0-alpha")

    def test_longer_prerelease_list_wins_when_prefix_equal(self):
        assert _version_tuple("1.0.0-beta.1.1") > _version_tuple("1.0.0-beta.1")

    def test_rollback_to_prerelease_rejected_semantically(self):
        # 场景锁定：min=2.2.0（已发布 release）时预发布清单必须判回滚
        assert _version_tuple("2.2.0-beta.44") < _version_tuple("2.2.0")

    def test_plain_semver_unchanged(self):
        assert _version_tuple("2.2.0") == _version_tuple("2.2.0")
        assert _version_tuple("2.2.1") > _version_tuple("2.2.0")

    def test_build_metadata_ignored(self):
        # SP-160：构建元数据不参与优先级（原 release_tools_test.py 用例并入）
        assert _version_tuple("1.0.0+build.5") == _version_tuple("1.0.0")

    def test_invalid_rejected(self):
        for bad in (None, 123, "", "1.2", "01.2.3", "1.2.3-"):
            try:
                _version_tuple(bad)
            except UpdateRejected:
                continue
            raise AssertionError(f"应拒绝: {bad!r}")


# ---------------------------------------------------------------- PY-184
class TestPrereleaseLeadingZeroRejected:
    def test_leading_zero_numeric_identifier_rejected(self):
        # PY-184："01" 是非法 SemVer 数字标识（前导零）——违规抛 UpdateRejected
        for bad in ("1.0.0-01", "2.2.0-01", "1.0.0-beta.01", "1.0.0-00"):
            try:
                _version_tuple(bad)
            except UpdateRejected:
                continue
            raise AssertionError(f"前导零数字段应拒绝: {bad!r}")

    def test_no_alias_between_01_and_1(self):
        # PY-184 核心：防回滚比较不得存在别名——"01" 被拒绝（不归一化为 1），
        # "2.2.0-01" 与 "2.2.0-1" 永不可能比较相等
        with pytest.raises(UpdateRejected):
            _version_tuple("2.2.0-01")
        assert _version_tuple("2.2.0-1") == _version_tuple("2.2.0-1")

    def test_legal_numeric_and_literal_identifiers_still_accepted(self):
        # 合法形态不受影响：0、多位无前导零数字、字面段、混合段
        assert _version_tuple("1.0.0-0") == _version_tuple("1.0.0-0")
        assert _version_tuple("1.0.0-10.20.30") == _version_tuple("1.0.0-10.20.30")
        assert _version_tuple("1.0.0-alpha.beta.1") == _version_tuple("1.0.0-alpha.beta.1")


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class TestVerifyArtifactSet:
    def _manifest(self, artifacts):
        return {"artifacts": artifacts}

    def test_cross_platform_same_basename_not_collapsed(self, tmp_path):
        # PY-024：同名制品（windows/android 各一份 x.zip）此前以 basename 为键
        # 互相覆盖——只验一份；改 platform/basename 复合键后两份都验
        content_a, content_b = b"A" * 10, b"B" * 10
        _write(tmp_path / "windows" / "x.zip", content_a)
        _write(tmp_path / "android" / "x.zip", content_b)
        manifest = self._manifest([
            {"platform": "windows-x64", "url": "https://c/x.zip", "sha256": hashlib.sha256(content_a).hexdigest()},
            {"platform": "android-universal", "url": "https://c/x.zip", "sha256": hashlib.sha256(content_b).hexdigest()},
        ])
        assert verify_artifact_set(tmp_path, manifest) == []

    def test_recursive_discovery(self, tmp_path):
        # PY-024：子目录工件此前被静默跳过
        content = b"payload"
        _write(tmp_path / "latest-release" / "win" / "setup.exe", content)
        manifest = self._manifest([
            {"platform": "latest-release", "url": "https://c/setup.exe",
             "sha256": hashlib.sha256(content).hexdigest()},
        ])
        assert verify_artifact_set(tmp_path, manifest) == []

    def test_hash_mismatch_detected(self, tmp_path):
        _write(tmp_path / "windows" / "a.zip", b"actual")
        manifest = self._manifest([
            {"platform": "windows-x64", "url": "https://c/a.zip", "sha256": "f" * 64},
        ])
        failures = verify_artifact_set(tmp_path, manifest)
        assert any("哈希不符" in f for f in failures)

    def test_missing_detected(self, tmp_path):
        manifest = self._manifest([
            {"platform": "windows-x64", "url": "https://c/ghost.zip", "sha256": "a" * 64},
        ])
        failures = verify_artifact_set(tmp_path, manifest)
        assert any("缺失工件" in f for f in failures)

    def test_unlisted_artifact_rejected(self, tmp_path):
        _write(tmp_path / "windows" / "surprise.zip", b"x")
        manifest = self._manifest([
            {"platform": "windows-x64", "url": "https://c/known.zip", "sha256": "a" * 64},
        ])
        failures = verify_artifact_set(tmp_path, manifest)
        assert any("未列明" in f for f in failures)
        assert any("缺失工件" in f for f in failures)

    def test_invalid_manifest_entries_fail(self, tmp_path):
        _write(tmp_path / "windows" / "a.zip", b"x")
        failures = verify_artifact_set(tmp_path, self._manifest(["nope"]))
        assert any("非对象条目" in f for f in failures)

    # ---------------------------------------------------- SP-144 空集恒真
    def test_empty_manifest_fails_even_with_empty_dist(self, tmp_path):
        # SP-144：manifest artifacts 为空 + dist 为空 → failures=[] 的
        # "全部通过"恒真退化必须消除——空集即失败
        failures = verify_artifact_set(tmp_path, self._manifest([]))
        assert failures, "空集必须失败（fail-closed）"
        assert any("manifest 未枚举任何工件" in f for f in failures)

    def test_empty_dist_dir_fails(self, tmp_path):
        # SP-144：dist 目录缺失/为空 + 非空 manifest → 缺失 + 空集双失败
        manifest = self._manifest([
            {"platform": "windows-x64", "url": "https://c/a.zip", "sha256": "a" * 64},
        ])
        failures = verify_artifact_set(tmp_path / "ghost-dist", manifest)
        assert any("dist 未枚举任何工件" in f for f in failures)
        assert any("缺失工件" in f for f in failures)

    # ---------------------------------------------------- PY-210 URL 解码
    def test_percent_encoded_url_matched_to_local_name(self, tmp_path):
        # PY-210：Release browser_url 对含空格资产名是 percent-encoded——
        # unquote 后须与本地文件名匹配
        content = b"payload with space"
        _write(tmp_path / "windows" / "a b.zip", content)
        manifest = self._manifest([
            {"platform": "windows-x64",
             "url": "https://github.com/o/r/releases/download/v1/a%20b.zip",
             "sha256": hashlib.sha256(content).hexdigest()},
        ])
        assert verify_artifact_set(tmp_path, manifest) == []


# ---------------------------------------------------------------- PY-199
class TestVerifyReleaseSentinel:
    def _metadata(self, **overrides):
        doc = {
            "schema_version": 1,
            "product": "Aegis",
            "platform": "windows",
            "version_name": "2.2.0",
            "source_revision": "9" * 40,
            "source_ref": "refs/tags/v2.2.0",
        }
        doc.update(overrides)
        return doc

    def _write_dist(self, tmp_path, metadata: dict):
        dist = tmp_path / "dist"
        dist.mkdir(parents=True)
        (dist / "build-metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    def test_local_unverified_sentinel_rejected(self, tmp_path):
        # PY-199：本地哨兵值 truthy——校验侧必须显式拒绝（不得当有效溯源）
        from verify_release import verify_bundle
        self._write_dist(tmp_path, self._metadata(source_revision="local-unverified"))
        with pytest.raises(SystemExit, match="local-unverified"):
            verify_bundle(tmp_path)

    def test_sentinel_in_any_provenance_field_rejected(self, tmp_path):
        from verify_release import verify_bundle
        self._write_dist(tmp_path, self._metadata(source_ref="local-unverified",
                                                  workflow_run_id="local-unverified"))
        with pytest.raises(SystemExit, match="source_ref"):
            verify_bundle(tmp_path)

    def test_real_provenance_passes_metadata_gate(self, tmp_path):
        # 真 SHA/ref 通过元数据门禁（走到"缺 SHA256SUMS.json"才停——证明
        # 哨兵检查未误伤正常元数据）
        from verify_release import verify_bundle
        self._write_dist(tmp_path, self._metadata())
        with pytest.raises(SystemExit, match="SHA256SUMS"):
            verify_bundle(tmp_path)

    # ------------------------------------------------ RS-N1 布局兼容
    def test_flat_platform_dir_layout_accepted(self, tmp_path):
        # CI verify-gate 传平铺平台目录（dist/<platform>，无嵌套 dist/）——
        # verify_bundle 须接受该布局并走完全部断言（meta+清单+SBOM）
        import json as _json

        from verify_release import verify_bundle
        (tmp_path / "build-metadata.json").write_text(
            _json.dumps(self._metadata(), ensure_ascii=False), encoding="utf-8")
        payload = tmp_path / "app.exe"
        payload.write_bytes(b"payload")
        (tmp_path / "sbom.cdx.json").write_text("{}", encoding="utf-8")
        # 清单须覆盖根内全部文件（清单自排除）——元数据与 SBOM 同列入账
        manifest = [
            {"Path": p, "Hash": hashlib.sha256((tmp_path / p).read_bytes()).hexdigest().upper()}
            for p in ("app.exe", "build-metadata.json", "sbom.cdx.json")
        ]
        (tmp_path / "SHA256SUMS.json").write_text(
            _json.dumps(manifest), encoding="utf-8")
        assert verify_bundle(tmp_path) is None

    def test_core_txt_checksum_fallback(self, tmp_path):
        # core 平台只有 SHA256SUMS.txt（无 JSON manifest）——PY-225：.txt 回退
        # 现为逐行 `<hash>␣␣<file>` 解析 + hashlib 重算 + 文件集对账。
        # PY-250：deadbeef 假哈希此前把"只数行数"的弱行为锁死——改真实哈希
        # 且清单必须覆盖 dist 全部文件（build-metadata/SBOM 同列入账）。
        import json as _json

        from verify_release import verify_bundle
        (tmp_path / "build-metadata.json").write_text(
            _json.dumps(self._metadata(platform="core"), ensure_ascii=False),
            encoding="utf-8")
        (tmp_path / "libaegis_policy_core.so").write_bytes(b"elf")
        (tmp_path / "sbom.cdx.json").write_text("{}", encoding="utf-8")
        lines = [
            f"{hashlib.sha256((tmp_path / p).read_bytes()).hexdigest()}  {p}"
            for p in ("build-metadata.json", "libaegis_policy_core.so", "sbom.cdx.json")
        ]
        (tmp_path / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert verify_bundle(tmp_path) is None

    def test_core_txt_dot_slash_prefix_and_relative_dist(self, tmp_path, monkeypatch):
        # SP-221（2026-10-01 发布链批 3）：release-core 的清单重生成命令
        #（find -print0 | xargs sha256sum）产出 "./" 前缀条目；verify-gate 以
        # 相对路径（dist/core）调用本脚本。两者叠加时 ③ 文件集对账曾把全部
        # 条目误判 unlisted（"v2.2.0-beta.51 第三次 tag 跑 verify-gate 实证）——
        # 归一化后必须通过，且以相对 dist 路径复现 CI 调用形态。
        import json as _json

        from verify_release import verify_bundle
        (tmp_path / "build-metadata.json").write_text(
            _json.dumps(self._metadata(platform="core"), ensure_ascii=False),
            encoding="utf-8")
        (tmp_path / "libaegis_policy_core.so").write_bytes(b"elf")
        (tmp_path / "sbom-core.cdx.json").write_text("{}", encoding="utf-8")
        lines = [
            f"{hashlib.sha256((tmp_path / p).read_bytes()).hexdigest()}  ./{p}"
            for p in ("build-metadata.json", "libaegis_policy_core.so", "sbom-core.cdx.json")
        ]
        (tmp_path / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path.parent)  # 相对路径调用（CI 形态）
        assert verify_bundle(Path(tmp_path.name)) is None

    def test_core_txt_fake_hash_rejected(self, tmp_path):
        # PY-225/PY-250：伪造哈希（deadbeef 填充）必须被哈希重算拒绝——
        # 此前"只数非空行"时该清单可通过（弱行为已消除）
        import json as _json

        from verify_release import verify_bundle
        (tmp_path / "build-metadata.json").write_text(
            _json.dumps(self._metadata(platform="core"), ensure_ascii=False),
            encoding="utf-8")
        (tmp_path / "libaegis_policy_core.so").write_bytes(b"elf")
        (tmp_path / "sbom.cdx.json").write_text("{}", encoding="utf-8")
        lines = [
            f"{hashlib.sha256((tmp_path / p).read_bytes()).hexdigest()}  {p}"
            for p in ("build-metadata.json", "sbom.cdx.json")
        ]
        lines.append("deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
                     "  libaegis_policy_core.so")
        (tmp_path / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="哈希不符"):
            verify_bundle(tmp_path)

    def test_core_txt_malformed_line_rejected(self, tmp_path):
        # PY-225：非 `<64hex>␣␣<file>` 形态（伪造单行文本）即拒——
        # 此前一行的任意非空文本即可通过门禁
        import json as _json

        from verify_release import verify_bundle
        (tmp_path / "build-metadata.json").write_text(
            _json.dumps(self._metadata(platform="core"), ensure_ascii=False),
            encoding="utf-8")
        (tmp_path / "a.bin").write_bytes(b"x")
        (tmp_path / "sbom.cdx.json").write_text("{}", encoding="utf-8")
        (tmp_path / "SHA256SUMS.txt").write_text("totally-not-a-checksum\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="格式无效"):
            verify_bundle(tmp_path)

    def test_core_txt_unlisted_file_rejected(self, tmp_path):
        # PY-225：文件集双向对账——dist 内存在未列入清单的文件即拒
        import json as _json

        from verify_release import verify_bundle
        (tmp_path / "build-metadata.json").write_text(
            _json.dumps(self._metadata(platform="core"), ensure_ascii=False),
            encoding="utf-8")
        (tmp_path / "libaegis_policy_core.so").write_bytes(b"elf")
        (tmp_path / "rogue.dll").write_bytes(b"rogue")  # 幽灵文件——清单漏列
        (tmp_path / "sbom.cdx.json").write_text("{}", encoding="utf-8")
        lines = [
            f"{hashlib.sha256((tmp_path / p).read_bytes()).hexdigest()}  {p}"
            for p in ("build-metadata.json", "libaegis_policy_core.so", "sbom.cdx.json")
        ]
        (tmp_path / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="未列入"):
            verify_bundle(tmp_path)

    def test_core_txt_path_escape_rejected(self, tmp_path):
        # PY-225：清单条目越出发布根（../ 逃逸）即拒
        import json as _json

        from verify_release import verify_bundle
        (tmp_path / "build-metadata.json").write_text(
            _json.dumps(self._metadata(platform="core"), ensure_ascii=False),
            encoding="utf-8")
        (tmp_path / "sbom.cdx.json").write_text("{}", encoding="utf-8")
        outside = tmp_path / "outside.bin"
        outside.write_bytes(b"o")
        lines = [
            f"{hashlib.sha256((tmp_path / p).read_bytes()).hexdigest()}  {p}"
            for p in ("build-metadata.json", "sbom.cdx.json")
        ]
        lines.append(f"{hashlib.sha256(outside.read_bytes()).hexdigest()}  ../outside.bin")
        (tmp_path / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="越出发布根"):
            verify_bundle(tmp_path)

    def test_empty_txt_checksum_rejected(self, tmp_path):
        # .txt 回退路径空清单同样 fail-closed
        import json as _json

        from verify_release import verify_bundle
        (tmp_path / "build-metadata.json").write_text(
            _json.dumps(self._metadata(platform="core"), ensure_ascii=False),
            encoding="utf-8")
        (tmp_path / "SHA256SUMS.txt").write_text("\n", encoding="utf-8")
        (tmp_path / "sbom.cdx.json").write_text("{}", encoding="utf-8")
        with pytest.raises(SystemExit, match="SHA256SUMS.txt 为空"):
            verify_bundle(tmp_path)

    def test_broken_metadata_json_clean_exit(self, tmp_path):
        # PY-235：build-metadata.json 坏 JSON → SystemExit 干净报告
        #（此前 json.JSONDecodeError 原始栈直接 traceback）
        from verify_release import verify_bundle
        (tmp_path / "build-metadata.json").write_text("{ broken", encoding="utf-8")
        with pytest.raises(SystemExit, match="无法解析"):
            verify_bundle(tmp_path)


# ---------------------------------------------------------------- PY-212
class TestIterReleaseFilesSingleSource:
    def test_write_and_verify_file_sets_identical(self, tmp_path):
        # PY-212：写/读两侧"排除清单自身"的文件集合必须来自同一
        # iter_release_files——对同一棵树分别构建清单与校验，集合一致
        from verify_checksum_json import verify_manifest
        from write_checksum_json import build_manifest, iter_release_files
        (tmp_path / "app.exe").write_bytes(b"payload")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "lib.so").write_bytes(b"native" * 1000)
        manifest = tmp_path / "SHA256SUMS.json"
        entries = build_manifest(tmp_path, manifest)
        manifest.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        expected = {p.relative_to(tmp_path).as_posix()
                    for p in iter_release_files(tmp_path, manifest)}
        observed = {e["Path"] for e in entries}
        assert expected == observed == {"app.exe", "sub/lib.so"}
        assert verify_manifest(tmp_path, manifest) == 2

    def test_manifest_itself_never_enumerated(self, tmp_path):
        # 排除清单自身规则单源后仍成立：清单文件不出现在枚举结果里
        from write_checksum_json import iter_release_files
        manifest = tmp_path / "SHA256SUMS.json"
        manifest.write_text("[]", encoding="utf-8")
        (tmp_path / "a.bin").write_bytes(b"x")
        assert [p.relative_to(tmp_path).as_posix()
                for p in iter_release_files(tmp_path, manifest)] == ["a.bin"]


# ---------------------------------------------------------------- SP-030
# SP1 批（审计 2026-09-23 清单）：verify_provenance 此前零单测——mock
# subprocess 覆盖全部分支（SP-026 目录缺失/SP-144 空集/SP-027 超时/
# SP-028 stderr 摘要/SP-029 递归枚举/成功路径）。
class TestVerifyProvenanceTool:
    OWNER = "acme"
    WORKFLOW = "acme/repo/.github/workflows/release.yml@refs/tags/v1"

    @staticmethod
    def _fake_run(returncode: int = 0, stderr: str = "", stdout: str = ""):
        def _run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
        return _run

    def test_missing_dist_dir_fails_clean(self, tmp_path):
        # SP-026：目录不存在此前 iterdir() FileNotFoundError traceback——
        # 改 is_dir 检查后必须返回失败明细（fail-closed，不抛异常）
        failures = run_provenance(tmp_path / "ghost-dist", self.OWNER, self.WORKFLOW)
        assert failures and any("dist 目录不存在" in f for f in failures)

    def test_empty_dist_dir_fails(self, tmp_path):
        # SP-144：空目录零循环恒真退化——空集即失败
        failures = run_provenance(tmp_path, self.OWNER, self.WORKFLOW)
        assert failures and any("dist 未枚举任何工件" in f for f in failures)

    def test_recursive_discovery_covers_subdirs(self, tmp_path, monkeypatch):
        # SP-029：子目录工件（latest-release/）此前被顶层 iterdir 静默跳过——
        # 递归枚举后每个文件都必须被验证（subprocess 收到对应路径）
        seen: list[str] = []

        def _run(cmd, **kwargs):
            seen.append(cmd[3])
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(subprocess, "run", _run)
        (tmp_path / "latest-release").mkdir()
        (tmp_path / "latest-release" / "setup.exe").write_bytes(b"pkg")
        failures = run_provenance(tmp_path, self.OWNER, self.WORKFLOW)
        assert failures == []
        assert seen == [str(tmp_path / "latest-release" / "setup.exe")]

    def test_nonzero_returncode_attaches_stderr_summary(self, tmp_path, monkeypatch):
        # SP-028：失败明细此前不含 stderr——排障需重跑；现在附首行摘要
        monkeypatch.setattr(subprocess, "run", self._fake_run(1, stderr="boom: no attestation\n"))
        (tmp_path / "a.exe").write_bytes(b"x")
        failures = run_provenance(tmp_path, self.OWNER, self.WORKFLOW)
        assert failures and any("no attestation" in f for f in failures)

    def test_timeout_counts_as_failure(self, tmp_path, monkeypatch):
        # SP-027：subprocess 无 timeout 此前可无限挂起——超时按失败计
        def _hang(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 120)

        monkeypatch.setattr(subprocess, "run", _hang)
        (tmp_path / "a.exe").write_bytes(b"x")
        failures = run_provenance(tmp_path, self.OWNER, self.WORKFLOW)
        assert failures and any("超时" in f for f in failures)

    def test_all_verified_passes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._fake_run(0))
        (tmp_path / "a.exe").write_bytes(b"x")
        (tmp_path / "b.msi").write_bytes(b"y")
        assert run_provenance(tmp_path, self.OWNER, self.WORKFLOW) == []

    def test_main_exit_codes(self, tmp_path, monkeypatch, capsys):
        # 三退出码语义：用法 2 / 失败 1 / 通过 0
        import verify_provenance as vp
        monkeypatch.setattr(sys, "argv", ["verify_provenance.py", "dist", "owner"])
        assert vp.main() == 2  # 参数不足
        monkeypatch.setattr(sys, "argv", ["verify_provenance.py",
                                          str(tmp_path / "ghost"), self.OWNER, self.WORKFLOW])
        assert vp.main() == 1  # dist 缺失 → 失败
        monkeypatch.setattr(subprocess, "run", self._fake_run(0))
        (tmp_path / "a.exe").write_bytes(b"x")
        monkeypatch.setattr(sys, "argv", ["verify_provenance.py",
                                          str(tmp_path), self.OWNER, self.WORKFLOW])
        assert vp.main() == 0  # 全部通过
        assert "✅" in capsys.readouterr().out


# ---------------------------------------------------------------- SP-031
# SP1 批（审计 2026-09-23 清单）：release/test-vectors/release-verify.json 的
# 8 条发布验证向量此前零执行消费者——落为元一致性门禁：向量集与实现面的
# 映射锁定，任何新增/删除向量都必须同步接线实现，否则本门禁红。
class TestReleaseVerifyVectorsMetaGate:
    VECTORS = Path(__file__).resolve().parents[2] / "release" / "test-vectors" / "release-verify.json"

    # 向量 case → 实现载体（工具分支/单测类）——映射本身即"执行消费者"
    # RUF012：映射是门禁常量——显式 ClassVar（非可变实例默认）
    IMPLEMENTED: ClassVar[dict[str, str]] = {
        "missing_artifact": "verify_artifact_set 缺失工件分支（release_chain_test.TestVerifyArtifactSet.test_missing_detected）",
        "hash_mismatch": "verify_artifact_set 哈希不符分支（release_chain_test.TestVerifyArtifactSet.test_hash_mismatch_detected）",
        "unlisted_artifact": "verify_artifact_set 双向集合相等分支（release_chain_test.TestVerifyArtifactSet.test_unlisted_artifact_rejected）",
        "rollback_version": "update_verifier 防回滚分支（release_tools_test.TestVerifyUpdateManifest.test_rollback_rejected）",
        "threshold_insufficient": "update_verifier 阈值分支（release_tools_test.TestVerifyUpdateManifest.test_threshold_unmet_rejected）",
        "sbom_missing": "发布门禁 SBOM 分支（verify_release.verify_bundle——SHA256SUMS/SBOM 缺失拒绝）",
        "provenance_missing": "verify_provenance 失败分支（release_chain_test.TestVerifyProvenanceTool.test_nonzero_returncode_attaches_stderr_summary）",
        "signer_identity_mismatch": "verify_provenance --signer-workflow 固定身份分支（SP-143 接线面）",
    }

    def test_vector_file_shape(self):
        doc = json.loads(self.VECTORS.read_text(encoding="utf-8"))
        assert doc["description"], "向量文件必须带说明"
        vectors = doc["vectors"]
        assert len(vectors) == 8, "发布验证向量必须 8 条（增删须同步本门禁映射）"
        for v in vectors:
            assert v["expected"] == "deny", f"发布验证向量恒 deny: {v['case']}"
            assert v.get("note"), f"向量须带语义说明: {v['case']}"

    def test_every_vector_has_implemented_consumer(self):
        doc = json.loads(self.VECTORS.read_text(encoding="utf-8"))
        for v in doc["vectors"]:
            assert v["case"] in self.IMPLEMENTED, \
                f"向量 {v['case']} 无实现映射——先接线实现再登记向量（fail-closed）"

    def test_no_orphan_implementations(self):
        # 反向：映射里的实现载体不得指向已删除的向量（防实现漂移出向量面）
        doc = json.loads(self.VECTORS.read_text(encoding="utf-8"))
        vector_cases = {v["case"] for v in doc["vectors"]}
        assert set(self.IMPLEMENTED) == vector_cases
