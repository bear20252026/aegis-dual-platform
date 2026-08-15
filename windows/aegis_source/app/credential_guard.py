"""credential_guard.py —— 凭据脱敏（单文件单职责：内存凭据不落地强化）。

背景（2026-08-15）：借鉴 FreeDom 反 dump（os_no_dump：undumpable +
no core，KNOWLEDGE_BASE 第 14 节）的"凭据值不落地"理念——Aegis 凭据
主路径已走环境变量（Gradle 签名 AEGIS_KEYSTORE_*）与 keyring（Windows
Credential Manager），本模块为**纵深防御**：日志/崩溃报告写入前屏蔽
常见凭据值（防御式脱敏，不改变功能）。

用法：crash_reporter 日志写入前经 redact() 过滤（见接入点）。
"""

import re
from typing import Any

# 常见凭据值模式（环境变量名/日志键）：AEGIS_ 前缀凭据 + 通用密码/令牌键
_CRED_PATTERNS: tuple[re.Pattern, ...] = (
    # AEGIS_ 前缀环境变量（签名凭据/密钥）：AEGIS_KEYSTORE_PASSWORD=x → 脱敏
    re.compile(r"(?i)\b(AEGIS_[A-Z0-9_]+)\s*[:=]\s*([^\s,;\"']+)"),
    # 通用凭据键：password/token/secret/api_key 等
    re.compile(
        r"(?i)\b(keystore_password|key_password|password|passwd|token|"
        r"secret|api_key|apikey)\s*[:=]\s*([^\s,;\"']+)"
    ),
)

_REDACTED = "<redacted>"


def redact(text: Any) -> Any:
    """屏蔽文本中的凭据值；非字符串原样返回（防御式）。

    对每类凭据模式替换 `key=value` → `key=<redacted>`；重复应用覆盖
    嵌套/多值场景。日志内容可能含 URL/普通文本，脱敏仅影响凭据键值，
    不改变其他内容（功能不变）。
    """
    if not isinstance(text, str):
        return text
    out = text
    for pat in _CRED_PATTERNS:
        out = pat.sub(lambda m: f"{m.group(1)}={_REDACTED}", out)
    return out
