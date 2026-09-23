# release_chain_test.py —— 发布链离线单测（pytest；PY-149 基建落地）
# PY-004：_version_tuple 预发布段参与比较（防回滚绕过锁定）。
# PY-024：verify_artifact_set 跨平台同名不覆盖 + 递归枚举。
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "release"))

from update_verifier import UpdateRejected, _version_tuple

sys.path.insert(0, str(ROOT / "release" / "tools" / "verify_artifact_set"))
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

    def test_invalid_rejected(self):
        for bad in (None, 123, "", "1.2", "01.2.3", "1.2.3-"):
            try:
                _version_tuple(bad)
            except UpdateRejected:
                continue
            raise AssertionError(f"应拒绝: {bad!r}")


def _write(path: Path, content: bytes) -> None:
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
        assert any("缺失" in f for f in failures)

    def test_unlisted_artifact_rejected(self, tmp_path):
        _write(tmp_path / "windows" / "surprise.zip", b"x")
        manifest = self._manifest([
            {"platform": "windows-x64", "url": "https://c/known.zip", "sha256": "a" * 64},
        ])
        failures = verify_artifact_set(tmp_path, manifest)
        assert any("未列明" in f for f in failures)
        assert any("缺失" in f for f in failures)

    def test_invalid_manifest_entries_fail(self, tmp_path):
        failures = verify_artifact_set(tmp_path, self._manifest(["nope"]))
        assert any("非对象条目" in f for f in failures)
