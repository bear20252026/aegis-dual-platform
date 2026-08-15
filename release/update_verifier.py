"""update_verifier.py —— R-17 整改（更新协议：强制签名/防回滚/可轮换）。

体验/功能审查（R-17）：更新清单必须强制签名、规范字节、key ID、阈值、
过期、版本单调性（防回滚）。本模块为客户端验证器（canonical_unsigned +
verify_manifest——Ed25519 阈值签名）——基于实施手册 R-17 示例。
发布期接入更新客户端：下载后先验证 size → 流式 SHA-256 → 平台/版本 →
verify_manifest → 持久化最高已接受 version（回滚拒绝）。

P0-04 修复（专家审查 2026-08-16——TUF 阈值签名对齐）：
- version 统一为 SemVer 字符串（与 Schema 契约一致——修复整数/字符串
  TypeError——N-04）
- signatures[] 数组（与 Schema 一致——单数 signature 改为复数）
- 重复 key_id 只计一次（防阈值重复计数）
- 所有异常封装为 UpdateRejected（稳定拒绝——失败闭合）
"""

import base64
import json
import re
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class UpdateRejected(Exception):
    """更新被拒绝（签名/过期/回滚/阈值）。"""


def canonical_unsigned(manifest: dict) -> bytes:
    """规范字节（剔除 signatures——排序键/紧凑分隔——R-17 规范字节）。"""
    unsigned = {k: v for k, v in manifest.items() if k != "signatures"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


# P0-04 修复（专家审查）：SemVer 字符串版本解析（替代整数比较——
# 与 Schema（SemVer 字符串 pattern）契约一致——TUF 阈值签名对齐）
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def _version_tuple(value: object) -> tuple:
    """解析 SemVer 字符串为元组（无效格式抛 UpdateRejected——稳定拒绝）。"""
    if not isinstance(value, str):
        raise UpdateRejected("版本格式无效")
    matched = _SEMVER.fullmatch(value)
    if not matched:
        raise UpdateRejected("版本格式无效")
    return tuple(int(part) for part in matched.groups())


def verify_manifest(manifest: dict, trusted_keys: dict[str, bytes],
                    min_version: str, now: datetime,
                    threshold: int = 2) -> None:
    """验证更新清单：版本单调（防回滚）/过期/签名阈值（Ed25519）。

    任意一项失败抛 UpdateRejected（失败闭合——绝不静默放行）。
    P0-04（专家审查）：SemVer 字符串比较/signatures[]/重复 key_id 只计
    一次/异常封装为 UpdateRejected（不再 TypeError）。
    """
    try:
        if not isinstance(manifest, dict) or threshold < 1:
            raise UpdateRejected("更新清单结构无效")
        if _version_tuple(manifest.get("version")) < _version_tuple(min_version):
            raise UpdateRejected("拒绝回滚清单")
        expires_raw = manifest.get("expires_at")
        if not isinstance(expires_raw, str):
            raise UpdateRejected("缺少过期时间")
        expires = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        if expires.tzinfo is None or expires <= now.astimezone(UTC):
            raise UpdateRejected("更新清单已过期或缺少时区")

        signatures = manifest.get("signatures")
        if not isinstance(signatures, list):
            raise UpdateRejected("签名结构无效")
        valid_key_ids: set[str] = set()
        payload = canonical_unsigned(manifest)
        for item in signatures:
            if not isinstance(item, dict):
                continue
            key_id = item.get("key_id")
            if not isinstance(key_id, str) or key_id in valid_key_ids:
                continue
            key = trusted_keys.get(key_id)
            if not key:
                continue
            try:
                sig = base64.b64decode(item["sig"], validate=True)
                Ed25519PublicKey.from_public_bytes(key).verify(sig, payload)
                valid_key_ids.add(key_id)  # 重复 key_id 只计一次
            except (KeyError, TypeError, ValueError):
                continue
        if len(valid_key_ids) < threshold:
            raise UpdateRejected("签名阈值未满足")
    except UpdateRejected:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise UpdateRejected("更新清单结构无效") from exc
