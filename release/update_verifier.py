"""update_verifier.py —— R-17 整改（更新协议：强制签名/防回滚/可轮换）。

体验/功能审查（R-17）：更新清单必须强制签名、规范字节、key ID、阈值、
过期、版本单调性（防回滚）。本模块为客户端验证器（canonical_unsigned +
verify_manifest——Ed25519 阈值签名）——基于实施手册 R-17 示例。
发布期接入更新客户端：下载后先验证 size → 流式 SHA-256 → 平台/版本 →
verify_manifest → 持久化最高已接受 version（回滚拒绝）。
"""

import base64
import json
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class UpdateRejected(Exception):
    """更新被拒绝（签名/过期/回滚/阈值）。"""


def canonical_unsigned(manifest: dict) -> bytes:
    """规范字节（剔除 signatures——排序键/紧凑分隔——R-17 规范字节）。"""
    unsigned = {k: v for k, v in manifest.items() if k != "signatures"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def verify_manifest(manifest: dict, trusted_keys: dict[str, bytes],
                    min_version: int, now: datetime,
                    threshold: int = 2) -> None:
    """验证更新清单：版本单调（防回滚）/过期/签名阈值（Ed25519）。

    任意一项失败抛 UpdateRejected（失败闭合——绝不静默放行）。
    """
    if manifest.get("version", 0) < min_version:
        raise UpdateRejected("拒绝回滚清单")
    expires = datetime.fromisoformat(
        manifest["expires_at"].replace("Z", "+00:00"))
    if expires <= now.astimezone(UTC):
        raise UpdateRejected("更新清单已过期")

    payload = canonical_unsigned(manifest)
    valid = 0
    for item in manifest.get("signatures", []):
        key = trusted_keys.get(item.get("key_id", ""))
        if not key:
            continue
        try:
            Ed25519PublicKey.from_public_bytes(key).verify(
                base64.b64decode(item["sig"]), payload)
            valid += 1
        except Exception:
            continue
    if valid < threshold:
        raise UpdateRejected("签名阈值未满足")
