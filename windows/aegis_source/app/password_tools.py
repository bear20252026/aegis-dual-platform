# -*- coding: utf-8 -*-
"""password_tools.py —— 密码生成器 + 本地泄露检测（纯逻辑，可单测）。

泄露检测采用 HaveIBeenPwned 的 k-匿名（k-anonymity）模型：
- 仅把密码 SHA-1 的前 5 位（前缀）发送到 HIBP；
- 服务端返回所有以该前缀开头的哈希后缀列表；
- 本地比对完整后缀是否命中。
明文密码与完整哈希绝不离开本机。无需 API Key（公共区间查询接口）。
"""

import hashlib
import secrets
import string
import urllib.request
import urllib.error

# 常见 Windows 上可双击打开的应用名（供快速唤起时提示）
DEFAULT_QWEN_NAMES = ("Qwen.exe", "通义千问.exe", "qwen.exe")
DEFAULT_KIMI_NAMES = ("Kimi.exe", "kimi.exe")

_SYMBOLS = "!@#$%^&*()-_=+[]{};:,.<>?/"


def generate(length: int = 16,
             use_upper: bool = True,
             use_lower: bool = True,
             use_digits: bool = True,
             use_symbols: bool = True) -> str:
    """用 secrets 生成高强度随机密码；保证每类至少含一个字符。"""
    pool = ""
    guaranteed = []
    if use_upper:
        pool += string.ascii_uppercase
        guaranteed.append(secrets.choice(string.ascii_uppercase))
    if use_lower:
        pool += string.ascii_lowercase
        guaranteed.append(secrets.choice(string.ascii_lowercase))
    if use_digits:
        pool += string.digits
        guaranteed.append(secrets.choice(string.digits))
    if use_symbols:
        pool += _SYMBOLS
        guaranteed.append(secrets.choice(_SYMBOLS))
    if not pool:
        pool = string.ascii_letters + string.digits
    chars = list(guaranteed)
    while len(chars) < length:
        chars.append(secrets.choice(pool))
    # 洗牌避免可预测的前缀规律
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars[:length])


def entropy_bits(length: int, pool_size: int) -> float:
    """估算密码熵（bits）：length * log2(pool_size)。"""
    if length <= 0 or pool_size <= 1:
        return 0.0
    import math
    return round(length * math.log2(pool_size), 1)


def strength_label(bits: float) -> str:
    if bits >= 80:
        return "很强"
    if bits >= 60:
        return "强"
    if bits >= 40:
        return "中等"
    if bits > 0:
        return "弱"
    return "未知"


def _sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest().upper()


def check_breach(password: str, timeout: float = 10.0):
    """本地泄露检测。

    返回 (count, status)：
      count  > 0  -> 在泄露库中出现的次数
      count == 0 -> 未命中
      status == "error" -> 网络/请求失败（无法判定），count = -1
    仅发送 SHA-1 前 5 位前缀，完整哈希不出本机。
    """
    if not password:
        return 0, "ok"
    sha = _sha1_hex(password)
    prefix, suffix = sha[:5], sha[5:]
    url = "https://api.pwnedpasswords.com/range/" + prefix
    req = urllib.request.Request(
        url, headers={"User-Agent": "Aegis-Browser",
                      "Add-Padding": "true"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return -1, "error"
    for line in body.splitlines():
        parts = line.split(":")
        if len(parts) == 2 and parts[0].upper() == suffix:
            try:
                return int(parts[1]), "found"
            except ValueError:
                return -1, "error"
    return 0, "ok"
