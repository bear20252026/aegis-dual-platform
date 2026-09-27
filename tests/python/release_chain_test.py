# release_chain_test.py —— 发布链离线单测（pytest；PY-149 基建落地）
# PY-004：_version_tuple 预发布段参与比较（防回滚绕过锁定）。
# PY-024：verify_artifact_set 跨平台同名不覆盖 + 递归枚举。
# SP-160（2026-09-26 审计）：_version_tuple 用例单源化——原
# release_tools_test.py 的重复用例类已删，全部并入本文件。
# PY-184/199/210/212 + SP-144：本批次新增发布链用例。
from __future__ import annotations

import hashlib
import json

from update_verifier import UpdateRejected, _version_tuple
from verify_artifact_set import verify_artifact_set


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
        import pytest
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
        import pytest
        from verify_release import verify_bundle
        self._write_dist(tmp_path, self._metadata(source_revision="local-unverified"))
        with pytest.raises(SystemExit, match="local-unverified"):
            verify_bundle(tmp_path)

    def test_sentinel_in_any_provenance_field_rejected(self, tmp_path):
        import pytest
        from verify_release import verify_bundle
        self._write_dist(tmp_path, self._metadata(source_ref="local-unverified",
                                                  workflow_run_id="local-unverified"))
        with pytest.raises(SystemExit, match="source_ref"):
            verify_bundle(tmp_path)

    def test_real_provenance_passes_metadata_gate(self, tmp_path):
        # 真 SHA/ref 通过元数据门禁（走到"缺 SHA256SUMS.json"才停——证明
        # 哨兵检查未误伤正常元数据）
        import pytest
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
        # core 平台只有 SHA256SUMS.txt（无 JSON manifest）——.txt 回退计数
        import json as _json
        from verify_release import verify_bundle
        (tmp_path / "build-metadata.json").write_text(
            _json.dumps(self._metadata(platform="core"), ensure_ascii=False),
            encoding="utf-8")
        (tmp_path / "libaegis_policy_core.so").write_bytes(b"elf")
        (tmp_path / "SHA256SUMS.txt").write_text(
            "deadbeef  libaegis_policy_core.so\n", encoding="utf-8")
        (tmp_path / "sbom.cdx.json").write_text("{}", encoding="utf-8")
        assert verify_bundle(tmp_path) is None

    def test_empty_txt_checksum_rejected(self, tmp_path):
        # .txt 回退路径空清单同样 fail-closed
        import json as _json
        import pytest
        from verify_release import verify_bundle
        (tmp_path / "build-metadata.json").write_text(
            _json.dumps(self._metadata(platform="core"), ensure_ascii=False),
            encoding="utf-8")
        (tmp_path / "SHA256SUMS.txt").write_text("\n", encoding="utf-8")
        (tmp_path / "sbom.cdx.json").write_text("{}", encoding="utf-8")
        with pytest.raises(SystemExit, match="SHA256SUMS.txt 为空"):
            verify_bundle(tmp_path)


# ---------------------------------------------------------------- PY-212
class TestIterReleaseFilesSingleSource:
    def test_write_and_verify_file_sets_identical(self, tmp_path):
        # PY-212：写/读两侧"排除清单自身"的文件集合必须来自同一
        # iter_release_files——对同一棵树分别构建清单与校验，集合一致
        from write_checksum_json import build_manifest, iter_release_files
        from verify_checksum_json import verify_manifest
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
