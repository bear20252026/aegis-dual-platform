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

from cryptography.exceptions import InvalidSignature
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
# 审计修复：接受预发布后缀（实际版本 2.2.0-beta.21 此前被判"版本格式无效"）
# PY-279（2026-10-02 审计）：预发布/构建段此前 [0-9A-Za-z.-]+ 接受空标识符
# （首尾点/连续点——"2.2.0-beta." 合法过门）。改 dot 分隔的非空
# [0-9A-Za-z-]+ 标识符序列（禁连续/首尾点）；contracts/schemas/
# update-manifest.schema.json 的 version.pattern 同步收紧。
_SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$")

# PY-184（2026-09-26 审计）：预发布段中的数字标识符必须无前导零——SemVer 规范
#（§10："Numeric identifiers MUST NOT include leading zeroes"）："2.2.0-01" 是
# 非法 SemVer；若放行，int("01")==1 会与 "2.2.0-1" 比较相等——防回滚比较存在
# 别名。此前 _SEMVER 的预发布段是宽松的 [0-9A-Za-z.-]+，前导零数字段漏过。
_NUMERIC_ID = re.compile(r"0|[1-9][0-9]*")

# PY-228（2026-10-01 审计）：expires_at 此前用 datetime.fromisoformat——它
# 接受非 RFC3339 形态（"2026-01-01" 裸日期、空格分隔、无秒、无时区），
# 与 schema format:date-time（RFC3339 严格口径）不一致：schema 拒的形态
# 客户端验证器放行。先正则锚定 RFC3339 形态（T 分隔 + 秒 + 时区
# Z/±HH:MM， fractional seconds 可选），再 fromisoformat 解析。
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$")


def _version_tuple(value: object) -> tuple:
    """解析 SemVer 字符串为可比较元组（无效格式抛 UpdateRejected——稳定拒绝）。

    PY-004：预发布段参与比较（SemVer precedence）——此前预发布段被丢弃，
    2.2.0-beta.1 与 2.2.0 比较为相等，回滚到预发布清单可绕过防回滚检查。
    语义：无预发布 > 有预发布（release 高于 beta）；预发布标识逐段比较
    （数字段按数值、字面段按 ASCII，数字段 < 字面段——SemVer 规范）；
    构建元数据（+build）不参与优先级。
    """
    if not isinstance(value, str):
        raise UpdateRejected("版本格式无效")
    matched = _SEMVER.fullmatch(value)
    if not matched:
        raise UpdateRejected("版本格式无效")
    major, minor, patch, pre, _build = matched.groups()
    core = (int(major), int(minor), int(patch))
    if pre is None:
        return (core, (1,), ())
    ids = []
    for part in pre.split("."):
        if part.isdigit():
            # PY-184：纯数字段必须通过无前导零校验（"01"/"00" 违规抛
            # UpdateRejected——失败闭合），否则 int() 归一化引入比较别名
            if not _NUMERIC_ID.fullmatch(part):
                raise UpdateRejected("版本格式无效")
            ids.append((0, int(part), ""))
        else:
            ids.append((1, 0, part))
    return (core, (0,), tuple(ids))


def verify_manifest(manifest: dict, trusted_keys: dict[str, bytes],
                    min_version: str, now: datetime,
                    threshold: int = 2) -> None:
    """验证更新清单：版本单调（防回滚）/过期/签名阈值（Ed25519）。

    任意一项失败抛 UpdateRejected（失败闭合——绝不静默放行）。
    P0-04（专家审查）：SemVer 字符串比较/signatures[]/重复 key_id 只计
    一次/异常封装为 UpdateRejected（不再 TypeError）。
    R7-TOOL-03（审计第七轮）：阈值计票按**公钥字节**去重（同 key_id 重复
    仍只计一次），单一密钥不得以多 key_id 凑满 threshold。
    """
    try:
        if not isinstance(manifest, dict) or threshold < 1:
            raise UpdateRejected("更新清单结构无效")
        if _version_tuple(manifest.get("version")) < _version_tuple(min_version):
            raise UpdateRejected("拒绝回滚清单")
        expires_raw = manifest.get("expires_at")
        if not isinstance(expires_raw, str):
            raise UpdateRejected("缺少过期时间")
        # PY-228：非 RFC3339 形态（裸日期/空格分隔/无时区）与 schema 口径
        # 一致拒绝——不再被 fromisoformat 宽松放行
        if not _RFC3339.fullmatch(expires_raw):
            raise UpdateRejected("过期时间格式无效（须为 RFC3339 date-time）")
        # PY-262（2026-10-02 审计）：正则放行小写 t/z 分隔符（RFC3339 大小写
        # 不敏感）但 fromisoformat 拒绝——解析前归一 t→T/z→Z（正则锚定下
        # 小写字母只可能出现在分隔符/后缀位，全局替换无误伤面）
        expires = datetime.fromisoformat(expires_raw.replace("t", "T").replace("z", "Z"))
        if expires.tzinfo is None or expires <= now.astimezone(UTC):
            raise UpdateRejected("更新清单已过期或缺少时区")

        signatures = manifest.get("signatures")
        if not isinstance(signatures, list):
            raise UpdateRejected("签名结构无效")
        valid_key_ids: set[str] = set()
        # 审计第七轮 R7-TOOL-03（2026-10-04）：**按公钥字节计票**。此前只按
        # key_id 计票——同一把公钥以两个 key_id 登记（两个信任锚槽位指向同一
        # 把密钥）即凑满 threshold=2，t-of-n 门槛被单一密钥满足。这是 R6-24 在
        # Rust `update_manifest::verify_threshold` 修掉的同一缺陷；本份才是
        # 实际执行的那一份（agent/broker.py 引用），修复必须回落到这里。
        # 票数是"多少把不同的密钥签了"，不是"多少条署名记录存在"。
        valid_key_bytes: set[bytes] = set()
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
            # 审计修复：补捕 InvalidSignature（坏签名此前以未捕获异常炸出，
            # 违背"所有异常封装为 UpdateRejected"的声明）
            except (KeyError, TypeError, ValueError, InvalidSignature):
                continue
            if key in valid_key_bytes:
                continue  # 同一把密钥换名重复计票——只算一票（R7-TOOL-03）
            valid_key_bytes.add(key)
            valid_key_ids.add(key_id)  # 重复 key_id 只计一次
        if len(valid_key_ids) < threshold:
            raise UpdateRejected("签名阈值未满足")
    except UpdateRejected:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise UpdateRejected("更新清单结构无效") from exc
