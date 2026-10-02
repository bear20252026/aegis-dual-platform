#!/usr/bin/env python3
"""verify_manifest.py —— 阶段 E（蓝图 release/tools/verify_manifest）：
更新清单验证——复用 release/update_verifier.py（P0-04 已统一：SemVer 字符串/
signatures[]/重复 key_id 只计一次/异常封装 UpdateRejected——TUF 阈值签名对齐）。

发布链独立验证（蓝图阶段 E）：manifest 必须通过签名/回滚/过期/阈值验证——
任何失败返回非零（终止发布——fail-closed——不允许跳过或截断验证）。
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# 复用 P0-04 更新验证器（契约统一——contracts/schemas/update-manifest.schema.json）
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from release.update_verifier import UpdateRejected, _version_tuple, verify_manifest

# Ed25519 公钥原始长度（from_public_bytes 契约）
_ED25519_RAW_KEY_BYTES = 32


def _load_threshold(policy_path: Path | None = None) -> int:
    """签名阈值单源：release/manifests/signing-policy.yaml（SP-006 整改）。

    此前脚本硬编码 threshold=2，策略 yaml 可漂移而不被发现。现强制读
    策略文件——文件缺失/解析失败/threshold 非法一律 exit 2（fail-closed，
    不回退到任何默认值）。

    PY-214/SP-175（2026-09-26 审计）：阈值此前以 MULTILINE+DOTALL 手写正则
    抽取——``.*?`` 可跨块误绑（如 rollback 段或后续新增块中先出现的
    threshold 键会被错误采信）。CI 已锁 pyyaml 依赖，改 yaml.safe_load
    结构化读取 policy.threshold（保留 fail-closed 退出码语义）。
    policy_path 参数仅供单测注入合成策略文件。
    """
    import yaml

    if policy_path is None:
        policy_path = (Path(__file__).resolve().parents[2]
                       / "manifests" / "signing-policy.yaml")
    if not policy_path.is_file():
        print(f"❌ 签名策略缺失: {policy_path}（终止发布——fail-closed）")
        raise SystemExit(2)
    # 结构化读取：policy 块下的 threshold 标量——非整数/缺失/越界一律拒绝
    try:
        doc = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"❌ 签名策略 YAML 解析失败: {policy_path.name}（{exc}）"
              "（终止发布——fail-closed）")
        raise SystemExit(2) from exc
    policy = doc.get("policy") if isinstance(doc, dict) else None
    threshold = policy.get("threshold") if isinstance(policy, dict) else None
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:
        print("❌ 签名策略 threshold 缺失或非法（终止发布——fail-closed）")
        raise SystemExit(2)
    return threshold


def _decode_trusted_keys(trusted: object) -> dict[str, bytes] | str:
    """PY-218（2026-10-01 审计）：trusted_keys.json 的键值解码为 Ed25519 原始公钥。

    JSON 无 bytes 类型——真实 trusted_keys.json 的键值是 base64（优先）或
    hex 编码字符串。此前 str 直传 Ed25519PublicKey.from_public_bytes 必抛
    TypeError 且被验证器吞掉——CLI 对任何真实密钥恒拒（工具永久失效，
    单测曾以 monkeypatch shim 掩盖）。现 main() 载入后解码：

    - dict[str, str] → 逐键 base64（严格 validate）→ 失败再 hex → 解出
      必须 32 字节（Ed25519 原始公钥长度）；
    - dict[str, bytes] → 已是原始字节（仅长度校验）——供程序化调用；
    - 其他结构 / 任何解码失败 → 返回错误消息（调用方 exit 2——环境错误，
      与坏 JSON 同语义）。
    """
    if not isinstance(trusted, dict) or not trusted:
        return "trusted_keys 必须是非空对象（key_id → 编码后的 32 字节 Ed25519 公钥）"
    decoded: dict[str, bytes] = {}
    for key_id, value in trusted.items():
        if not isinstance(key_id, str):
            return f"trusted_keys 键必须为字符串 key_id: {key_id!r}"
        if isinstance(value, bytes):
            raw = value
        elif isinstance(value, str):
            raw = None
            # base64 优先（44 字符标准编码；严格校验拒绝静默忽略非法字符）
            try:
                candidate = base64.b64decode(value, validate=True)
            except (binascii.Error, ValueError):
                candidate = None
            if candidate is not None and len(candidate) == _ED25519_RAW_KEY_BYTES:
                raw = candidate
            else:
                try:
                    candidate = bytes.fromhex(value)
                except ValueError:
                    return (f"trusted_keys[{key_id!r}] 既非合法 base64 也非合法 hex: "
                            f"{value[:16]!r}…")
                raw = candidate
        else:
            return f"trusted_keys[{key_id!r}] 值必须为编码字符串: {type(value).__name__}"
        if len(raw) != _ED25519_RAW_KEY_BYTES:
            return (f"trusted_keys[{key_id!r}] 解码后 {len(raw)} 字节——"
                    f"必须为 {_ED25519_RAW_KEY_BYTES} 字节 Ed25519 原始公钥")
        decoded[key_id] = raw
    return decoded


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """PY-286（2026-10-02 审计）：手工 argv 索引改 argparse——必填 positional
    缺参由 argparse 自动报错 exit 2（与既有 0/1/2 退出码语义一致：用法/环境
    错误 2、验证结论失败 1、通过 0）。"""
    parser = argparse.ArgumentParser(
        description="更新清单验证（签名阈值/防回滚/过期——复用 release/update_verifier）")
    parser.add_argument("manifest", type=Path, help="待验证 manifest.json")
    parser.add_argument("trusted_keys", type=Path, help="trusted_keys.json（key_id → 编码公钥）")
    parser.add_argument("min_version", help="已接受最低版本（SemVer——防回滚基线）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    # PY-273（2026-10-02 审计）：min_version 输入错误（非法 SemVer）此前进入
    # 验证器后与清单错误混同报「更新清单验证失败」exit 1——调用方误以为是
    # 清单结论问题去查签名。先预校验：无效即 exit 2 报「min_version 无效」
    #（用法错误语义——fail-fast 不进验证器）
    try:
        _version_tuple(args.min_version)
    except UpdateRejected as exc:
        print(f"❌ min_version 无效: {args.min_version!r}（{exc}）（用法错误——exit 2）")
        return 2
    # SP-024（审计 2026-09-23 清单·SP1 批）：manifest/trusted_keys 坏 JSON 直接
    # traceback 替代干净报告——包 try/except：exit 2 + 文件名上下文（与
    # SP-155 verify_artifact_set/generate_sbom 同一退出码语义——环境错误一律
    # exit 2，验证结论失败才是 exit 1）。
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        trusted = json.loads(args.trusted_keys.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        src = getattr(exc, "filename", None) or args.manifest.name
        print(f"❌ 输入文件读取/解析失败: {src}（{exc}）（终止发布——fail-closed）")
        return 2
    # PY-218：编码字符串在此解码为 32 字节原始公钥再进验证器
    #（此前 str 直传必 TypeError 被吞——CLI 对任何真实密钥恒拒）
    decoded = _decode_trusted_keys(trusted)
    if isinstance(decoded, str):
        print(f"❌ trusted_keys 解码失败: {decoded}（终止发布——fail-closed）")
        return 2
    try:
        verify_manifest(manifest, decoded, args.min_version, datetime.now(UTC),
                        threshold=_load_threshold())
    except UpdateRejected as exc:
        print(f"❌ 更新清单验证失败: {exc}（终止发布——fail-closed）")
        return 1
    print("✅ 更新清单验证通过（签名阈值/防回滚/过期——P0-04 契约统一）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
