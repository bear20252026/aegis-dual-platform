# release_tools_test.py —— release/ 发布工具链单测（pytest）。
# 覆盖审计条目：
#   PY-139 write_checksum_json.build_manifest 三用例
#   PY-140 verify_checksum_json.verify_manifest 用例
#   PY-141 篡改/越界/重复三拒绝
#   PY-142 update_verifier.canonical_unsigned 字节精确断言
#   PY-144 verify_manifest 四用例（Ed25519 阈值签名）
#   PY-145 回滚拒绝单测
#   PY-146 native_artifact_manifest 三类 ValueError
#   PY-147 --verify 拒绝单测
#   PY-148 build_metadata 缺属性 SystemExit
#   PY-185 build_metadata 复用共享 load_properties（行号报错）
# SP-160（2026-09-26 审计）：_version_tuple 重复用例类已删除——全部并入
# release_chain_test.py（本文件只留 canonical_unsigned 字节断言）。
# SP-161：sys.path 注入统一走 conftest.py（本文件不再自带 ROOT/样板）。
from __future__ import annotations

import base64
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from write_checksum_json import build_manifest  # noqa: E402
from verify_checksum_json import verify_manifest  # noqa: E402
from update_verifier import (  # noqa: E402
    UpdateRejected,
    canonical_unsigned,
)
from update_verifier import verify_manifest as verify_update_manifest  # noqa: E402
import native_artifact_manifest as nam  # noqa: E402
import build_metadata  # noqa: E402


# ---------------------------------------------------------------- PY-139
class TestBuildManifest:
    def test_sorted_entries_exclude_output(self, tmp_path):
        (tmp_path / "b.bin").write_bytes(b"2")
        (tmp_path / "a.bin").write_bytes(b"1")
        output = tmp_path / "SHA256SUMS.json"
        entries = build_manifest(tmp_path, output)
        assert [e["Path"] for e in entries] == ["a.bin", "b.bin"]  # 排序 + 输出文件自排除
        assert entries[0]["Hash"] == entries[0]["Hash"].upper()
        assert len(entries[0]["Hash"]) == 64

    def test_recursive_discovery(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "deep.dll").write_bytes(b"x" * 10)
        entries = build_manifest(tmp_path, tmp_path / "SHA256SUMS.json")
        assert [e["Path"] for e in entries] == ["sub/deep.dll"]  # POSIX 相对路径

    def test_empty_root_raises(self, tmp_path):
        with pytest.raises(SystemExit, match="没有可生成摘要的制品"):
            build_manifest(tmp_path, tmp_path / "SHA256SUMS.json")


# ---------------------------------------------------------------- PY-140/141
class TestVerifyChecksumManifest:
    def _make_release(self, tmp_path: Path) -> Path:
        (tmp_path / "app.exe").write_bytes(b"payload")
        (tmp_path / "lib.so").write_bytes(b"native")
        return tmp_path

    def _write_manifest(self, root: Path) -> Path:
        entries = build_manifest(root, root / "SHA256SUMS.json")
        manifest = root / "SHA256SUMS.json"
        manifest.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
        return manifest

    def test_valid_manifest_returns_count(self, tmp_path):
        # PY-140：合规清单 → 返回条目数
        root = self._make_release(tmp_path)
        manifest = self._write_manifest(root)
        assert verify_manifest(root, manifest) == 2

    def test_tampered_hash_rejected(self, tmp_path):
        # PY-141①：哈希篡改 → SystemExit
        root = self._make_release(tmp_path)
        manifest = self._write_manifest(root)
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        entries[0]["Hash"] = "0" * 64
        manifest.write_text(json.dumps(entries), encoding="utf-8")
        with pytest.raises(SystemExit, match="SHA-256 不匹配"):
            verify_manifest(root, manifest)

    def test_path_escape_rejected(self, tmp_path):
        # PY-141②：路径越出发布根 → SystemExit
        root = self._make_release(tmp_path)
        manifest = self._write_manifest(root)
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        entries.append({"Path": "../../escape.bin", "Hash": "A" * 64})
        manifest.write_text(json.dumps(entries), encoding="utf-8")
        with pytest.raises(SystemExit, match="越出发布根目录"):
            verify_manifest(root, manifest)

    def test_duplicate_path_rejected(self, tmp_path):
        # PY-141③：重复路径 → SystemExit
        root = self._make_release(tmp_path)
        manifest = self._write_manifest(root)
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        entries.append(dict(entries[0]))
        manifest.write_text(json.dumps(entries), encoding="utf-8")
        with pytest.raises(SystemExit, match="重复路径"):
            verify_manifest(root, manifest)

    def test_missing_coverage_rejected(self, tmp_path):
        root = self._make_release(tmp_path)
        manifest = self._write_manifest(root)
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        entries = [e for e in entries if e["Path"] != "lib.so"]  # 漏列一个文件
        manifest.write_text(json.dumps(entries), encoding="utf-8")
        with pytest.raises(SystemExit, match="未覆盖文件"):
            verify_manifest(root, manifest)


# ---------------------------------------------------------------- PY-142
# SP-160：原 TestCanonicalAndVersions 中的 _version_tuple 用例（PY-143）与
# release_chain_test.py 重复——已并入该文件，本类只保留 canonical 断言。
class TestCanonicalBytes:
    def test_canonical_bytes_exact(self):
        # PY-142：排序键 + 紧凑分隔 + 剔除 signatures——字节级精确断言
        manifest = {"version": "1.0.0", "signatures": [{"sig": "x"}], "channel": "stable"}
        assert canonical_unsigned(manifest) == b'{"channel":"stable","version":"1.0.0"}'


# ---------------------------------------------------------------- PY-144/145
NOW = datetime(2025, 9, 25, 12, 0, 0, tzinfo=UTC)


def _make_keys(key_ids: tuple[str, ...]):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    keys: dict[str, bytes] = {}
    signers: dict[str, Ed25519PrivateKey] = {}
    for kid in key_ids:
        sk = Ed25519PrivateKey.generate()
        keys[kid] = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        signers[kid] = sk
    return keys, signers


def _signed_manifest(manifest: dict, signers, key_ids: tuple[str, ...]) -> dict:
    payload = canonical_unsigned(manifest)
    manifest["signatures"] = [
        {"key_id": kid, "sig": base64.b64encode(signers[kid].sign(payload)).decode()}
        for kid in key_ids
    ]
    return manifest


class TestVerifyUpdateManifest:
    def _manifest(self, version: str = "2.2.0") -> dict:
        return {
            "schema": 1,
            "product": "Aegis",
            "version": version,
            "channel": "stable",
            "expires_at": "2099-01-01T00:00:00Z",
            "artifacts": [{"platform": "windows-x64", "url": "https://a/x.msix",
                           "sha256": "a" * 64, "size": 10}],
        }

    def test_threshold_two_valid_signatures_pass(self, tmp_path):
        # PY-144①：双钥阈值满足 → 通过
        keys, signers = _make_keys(("k1", "k2"))
        manifest = _signed_manifest(self._manifest(), signers, ("k1", "k2"))
        verify_update_manifest(manifest, keys, "1.0.0", NOW, threshold=2)  # 不抛即通过

    def test_threshold_unmet_rejected(self, tmp_path):
        # PY-144②：单签名 < 阈值 2 → 拒绝
        keys, signers = _make_keys(("k1", "k2"))
        manifest = _signed_manifest(self._manifest(), signers, ("k1",))
        with pytest.raises(UpdateRejected, match="签名阈值未满足"):
            verify_update_manifest(manifest, keys, "1.0.0", NOW, threshold=2)

    def test_expired_rejected(self, tmp_path):
        # PY-144③：过期清单 → 拒绝
        keys, signers = _make_keys(("k1", "k2"))
        manifest = self._manifest()
        manifest["expires_at"] = "2020-01-01T00:00:00Z"
        manifest = _signed_manifest(manifest, signers, ("k1", "k2"))
        with pytest.raises(UpdateRejected, match="过期"):
            verify_update_manifest(manifest, keys, "1.0.0", NOW, threshold=2)

    def test_tampered_payload_rejected(self, tmp_path):
        # PY-144④：签名后篡改负载 → 签名验证失败 → 阈值不满足拒绝
        keys, signers = _make_keys(("k1", "k2"))
        manifest = _signed_manifest(self._manifest(), signers, ("k1", "k2"))
        manifest["artifacts"][0]["size"] = 999999  # 篡改（不重签）
        with pytest.raises(UpdateRejected, match="签名阈值未满足"):
            verify_update_manifest(manifest, keys, "1.0.0", NOW, threshold=2)

    def test_duplicate_key_id_counted_once(self, tmp_path):
        # P0-04 语义锁定：重复 key_id 只计一次——同钥双签不能凑阈值
        keys, signers = _make_keys(("k1",))
        manifest = self._manifest()
        payload = canonical_unsigned(manifest)
        sig = base64.b64encode(signers["k1"].sign(payload)).decode()
        manifest["signatures"] = [{"key_id": "k1", "sig": sig}, {"key_id": "k1", "sig": sig}]
        with pytest.raises(UpdateRejected, match="签名阈值未满足"):
            verify_update_manifest(manifest, keys, "1.0.0", NOW, threshold=2)

    def test_rollback_rejected(self, tmp_path):
        # PY-145：版本低于已接受最低版本 → 拒绝回滚清单
        keys, signers = _make_keys(("k1", "k2"))
        manifest = _signed_manifest(self._manifest("2.1.0"), signers, ("k1", "k2"))
        with pytest.raises(UpdateRejected, match="回滚"):
            verify_update_manifest(manifest, keys, "2.2.0", NOW, threshold=2)


# ---------------------------------------------------------------- PY-146
def _make_native_tree(tmp_path: Path) -> Path:
    dll = tmp_path / "windows" / "win-x64" / "aegis_policy_core.dll"
    dll.parent.mkdir(parents=True, exist_ok=True)
    dll.write_bytes(b"win-binary")
    so = tmp_path / "android" / "arm64-v8a" / "libaegis_policy_core.so"
    so.parent.mkdir(parents=True, exist_ok=True)
    so.write_bytes(b"android-binary")
    return tmp_path


class TestNativeArtifactManifest:
    def test_missing_artifact_raises(self, tmp_path):
        with pytest.raises(ValueError, match="缺少或不是普通文件"):
            nam.build_manifest(tmp_path, ["windows"])

    def test_empty_artifact_raises(self, tmp_path):
        root = _make_native_tree(tmp_path)
        (root / "windows" / "win-x64" / "aegis_policy_core.dll").write_bytes(b"")
        with pytest.raises(ValueError, match="不能为空"):
            nam.build_manifest(root, ["windows"])

    def test_symlink_artifact_raises(self, tmp_path):
        root = _make_native_tree(tmp_path)
        real = root / "android" / "arm64-v8a" / "libaegis_policy_core.so"
        (root / "windows" / "win-x64").mkdir(parents=True, exist_ok=True)
        link = root / "windows" / "win-x64" / "aegis_policy_core.dll"
        try:
            link.symlink_to(real)
        except OSError:
            pytest.skip("平台不支持符号链接（Windows 非特权环境）")
        with pytest.raises(ValueError, match="缺少或不是普通文件"):
            nam.build_manifest(root, ["windows", "android"])

    def test_roundtrip_manifest_stable(self, tmp_path):
        root = _make_native_tree(tmp_path)
        manifest = nam.build_manifest(root, ["windows", "android"])
        assert manifest["library"] == "aegis_policy_core"
        assert {a["abi"] for a in manifest["artifacts"]} == {"win-x64", "arm64-v8a"}


# ---------------------------------------------------------------- PY-147
class TestVerifyModeRejects:
    def test_verify_detects_artifact_change(self, tmp_path, monkeypatch, capsys):
        root = _make_native_tree(tmp_path)
        output = tmp_path / "native-manifest.json"
        monkeypatch.setattr(sys, "argv", ["native_artifact_manifest.py",
                                          "--root", str(root),
                                          "--output", str(output),
                                          "--require", "windows", "--require", "android"])
        assert nam.main() == 0
        # 制品被替换（重打包/投毒场景）→ --verify 必须拒绝
        (root / "windows" / "win-x64" / "aegis_policy_core.dll").write_bytes(b"tampered")
        monkeypatch.setattr(sys, "argv", ["native_artifact_manifest.py",
                                          "--root", str(root),
                                          "--output", str(output),
                                          "--require", "windows", "--require", "android",
                                          "--verify"])
        assert nam.main() == 1
        assert "不一致" in capsys.readouterr().err


# ---------------------------------------------------------------- PY-148
class TestBuildMetadata:
    def test_missing_required_property_raises_systemexit(self, tmp_path, monkeypatch):
        # PY-148：缺共享版本属性 → SystemExit 且列出缺失键
        (tmp_path / "shared").mkdir()
        props = tmp_path / "shared" / "version.properties"
        props.write_text("PRODUCT=Aegis\n", encoding="utf-8")  # 缺其余 4 个必需键
        monkeypatch.setattr(build_metadata, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["build_metadata.py", "--platform", "windows",
                                          "--output", str(tmp_path / "out.json")])
        with pytest.raises(SystemExit, match="缺少共享版本属性"):
            build_metadata.main()

    def test_complete_properties_write_metadata(self, tmp_path, monkeypatch):
        (tmp_path / "shared").mkdir()
        props = tmp_path / "shared" / "version.properties"
        props.write_text(
            "PRODUCT=Aegis\nDISPLAY_NAME=Aegis WebView\nVERSION_NAME=2.2.0-beta.49\n"
            "VERSION_CODE=20248\nWINDOWS_PACKAGE_VERSION=2.2.0.0\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(build_metadata, "ROOT", tmp_path)
        out = tmp_path / "sub" / "build-metadata.json"
        monkeypatch.setattr(sys, "argv", ["build_metadata.py", "--platform", "windows",
                                          "--output", str(out)])
        build_metadata.main()
        doc = json.loads(out.read_text(encoding="utf-8"))
        assert doc["version_name"] == "2.2.0-beta.49"
        # PY-199 写侧对照：无 GITHUB_SHA 时降级写哨兵——校验侧 verify_release
        # 显式拒绝该哨兵（用例见 release_chain_test.TestVerifyReleaseSentinel）
        assert doc["source_revision"] == "local-unverified"


# ---------------------------------------------------------------- PY-185
class TestBuildMetadataSharedLoader:
    def test_load_properties_reused_from_sync_versions(self, tmp_path):
        # PY-185：build_metadata 不再自带 load_properties 副本——复用
        # scripts/sync_versions.load_properties（保留行号报错：无 "=" 行
        # 抛 RuntimeError 带 文件:行号，而非裸 ValueError）
        p = tmp_path / "version.properties"
        p.write_text("GOOD=1\nBROKEN\n", encoding="utf-8")
        with pytest.raises(RuntimeError) as excinfo:
            build_metadata.load_properties(p)
        msg = str(excinfo.value)
        assert "version.properties" in msg and ":2:" in msg and "BROKEN" in msg

    def test_load_properties_shared_object_identity(self):
        # 双源消除的结构性锁定：build_metadata.load_properties 与
        # scripts/sync_versions.load_properties 是同一个函数对象
        import sync_versions
        assert build_metadata.load_properties is sync_versions.load_properties


# ---------------------------------------------------------------- PY-214/SP-175
class TestLoadThresholdStructuredYaml:
    def _policy(self, tmp_path: Path, text: str) -> Path:
        p = tmp_path / "signing-policy.yaml"
        p.write_text(text, encoding="utf-8")
        return p

    def test_valid_policy_threshold_read(self, tmp_path):
        # PY-214：yaml.safe_load 结构化读取——合法策略读出 threshold
        from verify_manifest import _load_threshold
        p = self._policy(tmp_path, 'policy:\n  version: "1.1"\n  threshold: 2\n')
        assert _load_threshold(p) == 2

    def test_missing_threshold_exit_2(self, tmp_path):
        # 负例①：threshold 缺失 → SystemExit(2)（fail-closed，不回退默认值）
        from verify_manifest import _load_threshold
        p = self._policy(tmp_path, "policy:\n  version: \"1.1\"\n")
        with pytest.raises(SystemExit) as excinfo:
            _load_threshold(p)
        assert excinfo.value.code == 2

    def test_cross_block_binding_eliminated(self, tmp_path):
        # 负例②：threshold 只出现在嵌套子块（rollback.threshold）→ 拒绝——
        # 手写 MULTILINE+DOTALL 正则时代会跨块误绑该键
        from verify_manifest import _load_threshold
        p = self._policy(tmp_path, "policy:\n  rollback:\n    threshold: 5\n")
        with pytest.raises(SystemExit) as excinfo:
            _load_threshold(p)
        assert excinfo.value.code == 2

    def test_non_integer_threshold_exit_2(self, tmp_path):
        # 负例③：非整数/越界 threshold → SystemExit(2)
        from verify_manifest import _load_threshold
        for text in ("policy:\n  threshold: two\n",
                     "policy:\n  threshold: 0\n",
                     "policy:\n  threshold: -1\n"):
            p = self._policy(tmp_path, text)
            with pytest.raises(SystemExit) as excinfo:
                _load_threshold(p)
            assert excinfo.value.code == 2

    def test_real_policy_threshold_is_two(self):
        # SP-006 单源回归：仓库真实 signing-policy.yaml 读出阈值 2
        from verify_manifest import _load_threshold
        assert _load_threshold() == 2
