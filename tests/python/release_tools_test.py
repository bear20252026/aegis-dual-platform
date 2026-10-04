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

import build_metadata
import native_artifact_manifest as nam
import pytest
from update_verifier import (
    UpdateRejected,
    canonical_unsigned,
)
from update_verifier import verify_manifest as verify_update_manifest
from verify_checksum_json import verify_manifest
from write_checksum_json import build_manifest


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
            "schema": 1, "product": "Aegis", "version": version, "channel": "stable",
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

    # ---------------------------------------- R7-TOOL-03（第七轮）：计票按公钥字节
    def test_same_key_under_two_key_ids_counts_one_vote(self, tmp_path):
        # R7-TOOL-03：R6-24 在 Rust `update_manifest::verify_threshold` 修掉的洞，
        # 未回落到实际执行的本份（agent/broker.py 引用它）——同一把公钥以两个
        # key_id 登记（两个信任锚槽位指向同一把密钥）各签一次，按 key_id 计票
        # 即凑满 threshold=2，t-of-n 被单一密钥满足。票数是「多少把不同的密钥
        # 签了」，不是「多少条署名记录存在」→ 必须按公钥字节去重。
        keys, signers = _make_keys(("k1",))
        keys["k2"] = keys["k1"]  # 第二个锚位 = 同一把公钥
        manifest = self._manifest()
        sig = base64.b64encode(signers["k1"].sign(canonical_unsigned(manifest))).decode()
        manifest["signatures"] = [{"key_id": "k1", "sig": sig}, {"key_id": "k2", "sig": sig}]
        with pytest.raises(UpdateRejected, match="签名阈值未满足"):
            verify_update_manifest(manifest, keys, "1.0.0", NOW, threshold=2)

    def test_two_distinct_keys_under_two_key_ids_meets_threshold(self, tmp_path):
        # 反向对照（防「改成恒拒」式假修复）：与上例逐项同形——两条签名、两个
        # key_id、threshold=2，唯一差别是两把**不同的**真钥 → 必须通过。
        keys, signers = _make_keys(("k1", "k2"))
        manifest = _signed_manifest(self._manifest(), signers, ("k1", "k2"))
        verify_update_manifest(manifest, keys, "1.0.0", NOW, threshold=2)  # 不抛即通过

    def test_rollback_rejected(self, tmp_path):
        # PY-145：版本低于已接受最低版本 → 拒绝回滚清单
        keys, signers = _make_keys(("k1", "k2"))
        manifest = _signed_manifest(self._manifest("2.1.0"), signers, ("k1", "k2"))
        with pytest.raises(UpdateRejected, match="回滚"):
            verify_update_manifest(manifest, keys, "2.2.0", NOW, threshold=2)


# ---------------------------------------------------------------- PY-244
class TestCanonicalBytesGoldenVectors:
    """PY-244（2026-10-01 审计）：contracts/vectors/update-manifest-canonical.json
    的 canonical 字节金标此前仅 Rust tests/vectors.rs 消费——Python 侧改
    canonical_unsigned 序列化（键序/分隔/ensure_ascii）不红。逐条向量断言
    canonical_unsigned(manifest).hex() == expected_canonical_hex——Python
    序列化漂移即本门禁红（跨端字节级兼容锁定补 Python 面）。
    """

    VECTORS = Path(__file__).resolve().parents[2] / "contracts" / "vectors" / "update-manifest-canonical.json"

    def test_every_golden_vector_matches_python_canonicalization(self):
        doc = json.loads(self.VECTORS.read_text(encoding="utf-8"))
        vectors = doc["vectors"]
        assert len(vectors) >= 3, "canonical 金标向量不得静默缩水（增删须同步 Rust tests/vectors.rs）"
        for v in vectors:
            assert canonical_unsigned(v["manifest"]).hex() == v["expected_canonical_hex"], (
                f"canonical 字节漂移: {v['name']}（Python 序列化与金标不一致）")


# ---------------------------------------------------------------- PY-228/237
class TestExpiryRfc3339AndBoundary:
    def _manifest(self, expires_at):
        return {
            "schema": 1, "product": "Aegis", "version": "2.2.0",
            "channel": "stable", "expires_at": expires_at,
            "artifacts": [], "signatures": [{"key_id": "k", "sig": "AAAA"}],
        }

    def test_non_rfc3339_forms_rejected(self):
        # PY-228：fromisoformat 宽松形态（裸日期/空格分隔/无时区）不再放行
        #（与 schema format:date-time 口径一致）
        keys, _signers = _make_keys(("k1", "k2"))
        for bad in ("2026-01-01", "2026-01-01 00:00:00Z", "2026-01-01T00:00:00",
                    "not-a-timestamp"):
            with pytest.raises(UpdateRejected, match="过期时间格式无效|格式无效"):
                verify_update_manifest(self._manifest(bad), keys, "1.0.0", NOW, threshold=1)

    def test_expiry_boundary_is_inclusive(self):
        # PY-237：expires 恰等于 now 即过期（<= 口径——与 e2e 对齐；
        # 此前 e2e < / verifier <= 两套边界）
        keys, _signers = _make_keys(("k1", "k2"))
        with pytest.raises(UpdateRejected, match="过期"):
            verify_update_manifest(self._manifest("2025-09-25T12:00:00Z"),
                                   keys, "1.0.0", NOW, threshold=1)

    def test_valid_rfc3339_still_accepted(self):
        keys, signers = _make_keys(("k1",))
        manifest = _signed_manifest(self._manifest("2099-01-01T00:00:00Z"), signers, ("k1",))
        verify_update_manifest(manifest, keys, "1.0.0", NOW, threshold=1)  # 不抛即通过

    # ------------------------------------------------------- PY-262 小写双向量
    def test_lowercase_t_z_separator_accepted(self):
        # PY-262（2026-10-02 审计）：_RFC3339 正则放行小写 t/z（RFC3339 大小写
        # 不敏感）但 fromisoformat 拒绝——解析前归一 t→T/z→Z 后小写形态放行
        keys, signers = _make_keys(("k1",))
        manifest = _signed_manifest(self._manifest("2099-01-01t00:00:00z"), signers, ("k1",))
        verify_update_manifest(manifest, keys, "1.0.0", NOW, threshold=1)  # 不抛即通过

    def test_lowercase_separator_expiry_still_enforced(self):
        # PY-262 对偶边界：小写形态同样参与过期判定（归一只改字符不改语义）
        keys, _signers = _make_keys(("k1", "k2"))
        with pytest.raises(UpdateRejected, match="过期"):
            verify_update_manifest(self._manifest("2020-01-01t00:00:00z"),
                                   keys, "1.0.0", NOW, threshold=1)


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
            # PY-257（2026-10-01 审计）长期跳过口径登记：Windows 非特权环境下
            # 创建符号链接需开发者模式（SeCreateSymbolicLinkPrivilege）——
            # 启用「Windows 设置 → 开发者选项 → 开发者模式」后本用例在本机
            # 生效；CI（Linux runner）恒执行。跳过仅限本条符号链接负例，
            # 非测试面缺口（其余用例覆盖 build_manifest 语义面）。
            pytest.skip("平台不支持符号链接（Windows 非特权环境）"
                        "——启用开发者模式后本用例可执行（PY-257 口径登记）")
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
        monkeypatch.setattr(sys, "argv", ["native_artifact_manifest.py", "--root", str(root),
                                          "--output", str(output), "--require", "windows",
                                          "--require", "android"])
        assert nam.main() == 0
        # 制品被替换（重打包/投毒场景）→ --verify 必须拒绝
        (root / "windows" / "win-x64" / "aegis_policy_core.dll").write_bytes(b"tampered")
        monkeypatch.setattr(sys, "argv", ["native_artifact_manifest.py", "--root", str(root),
                                          "--output", str(output), "--require", "windows",
                                          "--require", "android", "--verify"])
        assert nam.main() == 1
        assert "不一致" in capsys.readouterr().err

    def test_verify_reversed_require_order_still_matches(self, tmp_path, monkeypatch, capsys):
        # PY-261（2026-10-02 审计）：manifest 比较此前依赖 --require 旗标序
        # ——artifacts 列表按平台传入序生成，换序重跑（android 在前）即被
        # 误判「不一致」。比较前按 (platform, abi, path) 排序归一——制品集合
        # 相同必须通过（换序回归向量）
        root = _make_native_tree(tmp_path)
        output = tmp_path / "native-manifest.json"
        monkeypatch.setattr(sys, "argv", ["native_artifact_manifest.py", "--root", str(root),
                                          "--output", str(output), "--require", "windows",
                                          "--require", "android"])
        assert nam.main() == 0  # 以 windows 在前的顺序生成
        monkeypatch.setattr(sys, "argv", ["native_artifact_manifest.py", "--root", str(root),
                                          "--output", str(output), "--require", "android",
                                          "--require", "windows", "--verify"])
        assert nam.main() == 0  # 反序复核——集合相同即通过
        assert "verified" in capsys.readouterr().out


# ---------------------------------------------------------------- PY-148
class TestBuildMetadata:
    def test_missing_properties_file_exits_2(self, tmp_path, monkeypatch, capsys):
        # PY-266（2026-10-02 审计）：缺 version.properties 此前在 read_text 处
        # 裸 FileNotFoundError traceback——前置 is_file 检查后干净报错 exit 2
        #（环境错误语义，区别于缺必需属性的 SystemExit 消息退出）
        monkeypatch.setattr(build_metadata, "ROOT", tmp_path)  # tmp 树无 shared/
        monkeypatch.setattr(sys, "argv", ["build_metadata.py", "--platform", "windows", "--output", str(tmp_path / "out.json")])
        with pytest.raises(SystemExit) as excinfo:
            build_metadata.main()
        assert excinfo.value.code == 2
        assert "version.properties" in capsys.readouterr().err

    def test_missing_required_property_raises_systemexit(self, tmp_path, monkeypatch):
        # PY-148：缺共享版本属性 → SystemExit 且列出缺失键
        (tmp_path / "shared").mkdir()
        props = tmp_path / "shared" / "version.properties"
        props.write_text("PRODUCT=Aegis\n", encoding="utf-8")  # 缺其余 4 个必需键
        monkeypatch.setattr(build_metadata, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["build_metadata.py", "--platform", "windows", "--output", str(tmp_path / "out.json")])
        with pytest.raises(SystemExit, match="缺少共享版本属性"):
            build_metadata.main()

    def test_complete_properties_write_metadata(self, tmp_path, monkeypatch):
        # PY-259（2026-10-01 发布链批）：build_metadata 写侧优先消费 GITHUB_*
        # 环境变量——CI runner 上恒有值，哨兵断言必须显式清场（否则断言的是
        # runner 环境而非被测降级路径——发布链 contracts job 实证）
        for var in ("GITHUB_SHA", "GITHUB_REF", "GITHUB_RUN_ID"):
            monkeypatch.delenv(var, raising=False)
        (tmp_path / "shared").mkdir()
        props = tmp_path / "shared" / "version.properties"
        props.write_text("PRODUCT=Aegis\nDISPLAY_NAME=Aegis WebView\nVERSION_NAME=2.2.0-beta.49\n"
                         "VERSION_CODE=20248\nWINDOWS_PACKAGE_VERSION=2.2.0.0\n", encoding="utf-8")
        monkeypatch.setattr(build_metadata, "ROOT", tmp_path)
        out = tmp_path / "sub" / "build-metadata.json"
        monkeypatch.setattr(sys, "argv", ["build_metadata.py", "--platform", "windows", "--output", str(out)])
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


# ---------------------------------------------------------------- SP-024/025
# SP1 批（审计 2026-09-23 清单）：verify_manifest.main() 三退出码路径此前
# 零测试；SP-024 坏 JSON 此前直接 traceback（替代干净报告）。
# PY-218（2026-10-01 审计）：删除 monkeypatch json shim——trusted_keys 的
# base64/hex → 32 字节解码已在 main() 真实路径落地，本组用例全部改走
# 真实 CLI 路径（此前 shim 恰好掩盖了"str 直传必拒"的工具失效）。
class TestVerifyManifestToolMain:
    @staticmethod
    def _write_real_env(tmp_path, monkeypatch, manifest, keys, signers, key_ids):
        """真实路径环境：base64 编码 trusted_keys.json + manifest.json。"""
        import verify_manifest as vm
        trusted = tmp_path / "trusted_keys.json"
        trusted.write_text(json.dumps(
            {k: base64.b64encode(v).decode() for k, v in keys.items()}), encoding="utf-8")
        mpath = tmp_path / "manifest.json"
        mpath.write_text(json.dumps(_signed_manifest(manifest, signers, key_ids)), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["verify_manifest.py", str(mpath), str(trusted), "1.0.0"])
        return vm

    def test_usage_error_exit_2(self, monkeypatch):
        # SP-025①：参数不足 → exit 2（环境/用法错误语义）
        # PY-286：argparse 必填 positional——缺参以 SystemExit(2) 抛出
        import verify_manifest as vm
        monkeypatch.setattr(sys, "argv", ["verify_manifest.py", "a", "b"])
        with pytest.raises(SystemExit) as excinfo:
            vm.main()
        assert excinfo.value.code == 2

    def test_invalid_min_version_exit_2(self, tmp_path, monkeypatch, capsys):
        # PY-273（2026-10-02 审计）：min_version 输入错误（非法 SemVer）此前
        # 进验证器与清单错误混同报「更新清单验证失败」exit 1——先预校验：
        # 无效即 exit 2 报「min_version 无效」（用法错误语义）
        import verify_manifest as vm
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        trusted = tmp_path / "trusted_keys.json"
        trusted.write_text('{"k1": "' + base64.b64encode(b"x" * 32).decode() + '"}',
                           encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["verify_manifest.py", str(manifest), str(trusted), "not-semver"])
        assert vm.main() == 2
        out = capsys.readouterr().out
        assert "min_version 无效" in out and "not-semver" in out

    def test_bad_json_exit_2_no_traceback(self, tmp_path, monkeypatch, capsys):
        # SP-024：manifest 坏 JSON → exit 2 + 文件名上下文（不 traceback）
        import verify_manifest as vm
        bad = tmp_path / "manifest-bad.json"
        bad.write_text("{ nope", encoding="utf-8")
        trusted = tmp_path / "trusted_keys.json"
        trusted.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["verify_manifest.py", str(bad), str(trusted), "1.0.0"])
        assert vm.main() == 2
        assert "manifest-bad.json" in capsys.readouterr().out

    def test_trusted_keys_bad_json_exit_2(self, tmp_path, monkeypatch):
        # SP-024：trusted_keys 坏 JSON 同样 exit 2
        import verify_manifest as vm
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        bad = tmp_path / "trusted-bad.json"
        bad.write_text("[", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["verify_manifest.py", str(manifest), str(bad), "1.0.0"])
        assert vm.main() == 2

    def test_rejected_manifest_exit_1(self, tmp_path, monkeypatch):
        # SP-025②：清单验证不通过（阈值不足——k2 签名被剥离）→ exit 1
        # PY-218：走真实路径（base64 编码 trusted_keys + main() 解码）
        keys, signers = _make_keys(("k1", "k2"))
        vm = self._write_real_env(
            tmp_path, monkeypatch,
            {"schema": 1, "product": "Aegis", "version": "2.2.0",
             "channel": "stable", "expires_at": "2099-01-01T00:00:00Z",
             "artifacts": []},
            keys, signers, ("k1",))  # 单签名 < 阈值 2
        assert vm.main() == 1

    def test_valid_manifest_exit_0(self, tmp_path, monkeypatch, capsys):
        # SP-025③：双钥满足阈值 → exit 0（真实策略文件走 _load_threshold()）
        # PY-218：真实路径——base64 编码键值经 main() 解码后验证通过
        #（修复前 str 直传 from_public_bytes 必 TypeError → 恒拒）
        keys, signers = _make_keys(("k1", "k2"))
        vm = self._write_real_env(
            tmp_path, monkeypatch,
            {"schema": 1, "product": "Aegis", "version": "2.2.0",
             "channel": "stable", "expires_at": "2099-01-01T00:00:00Z",
             "artifacts": []},
            keys, signers, ("k1", "k2"))
        assert vm.main() == 0
        assert "✅" in capsys.readouterr().out

    def test_hex_encoded_keys_also_accepted(self, tmp_path, monkeypatch):
        # PY-218：hex 编码的 32 字节键同样可解码（base64 优先、hex 兜底）
        import verify_manifest as vm
        keys, signers = _make_keys(("k1", "k2"))
        trusted = tmp_path / "trusted_keys.json"
        trusted.write_text(json.dumps(
            {k: v.hex() for k, v in keys.items()}), encoding="utf-8")
        manifest = _signed_manifest({
            "schema": 1, "product": "Aegis", "version": "2.2.0",
            "channel": "stable", "expires_at": "2099-01-01T00:00:00Z",
            "artifacts": [],
        }, signers, ("k1", "k2"))
        mpath = tmp_path / "manifest.json"
        mpath.write_text(json.dumps(manifest), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["verify_manifest.py", str(mpath), str(trusted), "1.0.0"])
        assert vm.main() == 0

    def test_bad_key_encoding_exit_2(self, tmp_path, monkeypatch, capsys):
        # PY-218：非 base64/hex 编码 → exit 2（环境错误，fail-closed）
        import verify_manifest as vm
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        trusted = tmp_path / "trusted_keys.json"
        trusted.write_text(json.dumps({"k1": "not-valid-encoding!!!"}), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["verify_manifest.py", str(manifest), str(trusted), "1.0.0"])
        assert vm.main() == 2
        assert "解码失败" in capsys.readouterr().out

    def test_wrong_length_key_exit_2(self, tmp_path, monkeypatch):
        # PY-218：解码成功但非 32 字节（Ed25519 原始公钥长度）→ exit 2
        import verify_manifest as vm
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        trusted = tmp_path / "trusted_keys.json"
        trusted.write_text(json.dumps(
            {"k1": base64.b64encode(b"short").decode()}), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["verify_manifest.py", str(manifest), str(trusted), "1.0.0"])
        assert vm.main() == 2
