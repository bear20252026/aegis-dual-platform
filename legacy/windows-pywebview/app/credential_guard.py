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


# R-08 整改（体验/功能审查）：URL 日志最小化——敏感 query 键脱敏
# （token/code/password/session/key 等——防日志泄露凭据/授权码——
# 实施手册 R-08 日志最小化示例）
SENSITIVE_QUERY_KEYS = {
    "token", "code", "state", "password", "passwd", "session", "key",
    "secret", "api_key", "apikey",
}


def redact_url(raw: str) -> str:
    """脱敏 URL 的敏感 query 参数（R-08 日志最小化——保留主机/路径）。"""
    if not raw:
        return raw
    try:
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
        parsed = urlsplit(raw)
        pairs = [
            (k, "[REDACTED]" if k.lower() in SENSITIVE_QUERY_KEYS else v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        ]
        # 审计第六轮（2026-10-03）：此前用 parsed.netloc 重组——netloc 含
        # user:password@host，userinfo 里的凭据原样进日志（CS-337 在 C# 侧
        # 改用 uri.Authority、AD-264 在 Kotlin 侧剥离 userinfo，同一缺陷类
        # 从未回落到本文件）。现仅取 hostname+port，userinfo 一律丢弃。
        hostname = parsed.hostname or ""
        try:
            port = parsed.port
        except ValueError:
            port = None  # 非法端口——不保留不可解析的 authority 原文
        netloc = f"{hostname}:{port}" if port is not None else hostname
        return urlunsplit(
            (parsed.scheme, netloc, parsed.path,
             urlencode(pairs, safe="[]"), "")  # safe="[]" 保留 [REDACTED] 可读标记
        )
    except Exception:
        # 审计第六轮（2026-10-03）：fail-closed——解析失败绝不回吐原文
        #（原文可能正含 userinfo/令牌）；此前 `return raw` 让脱敏函数在最
        # 需要它的畸形输入上失效
        return "[unparseable-url-redacted]"
