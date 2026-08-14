"""fingerprint.py —— 可选指纹/隐身设备配置（单文件单职责，默认关闭）。

借鉴 ShardBrowser / CloakBrowser 的"设备配置文件"思路，但遵循
Aegis 的**如实 UA** 安全第一原则：

- **默认关闭**：除非配置显式指定 `fingerprint_profile`，否则一律使用
  浏览器自身的真实 UA（app/browser.py 的 honest_ua），本模块不生效；
- **纯数据 + 纯函数**：只提供设备配置文件目录与 UA 生成，不持有
  窗口/网络引用，可离线单测；
- **不伪造指纹**：本模块仅提供 **UA 字符串**（User-Agent）层面的
  设备配置——不触碰 Canvas/WebGL 等深度伪造（与"如实声明身份"
  的项目承诺一致），如需深度指纹伪造请评估 CloakBrowser 方案。
"""

import re
from collections.abc import Iterable

# 设备配置文件目录：name -> (平台, 说明, UA 模板)
# UA 模板中的 {chrome}/{version}/{safari} 由生成函数填充。
_DEVICE_PROFILES: dict[str, tuple[str, str, str]] = {
    "windows-desktop": (
        "Windows",
        "Windows 10/11 桌面版（与 Aegis 原生平台一致）",
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/{chrome} Safari/{safari}"),
    ),
    "macos-desktop": (
        "macOS",
        "macOS 桌面版 Safari 兼容 UA",
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/{version} Safari/605.1.15"),
    ),
    "android-mobile": (
        "Android",
        "Android 移动端 Chrome UA",
        ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/{chrome} Mobile Safari/{safari}"),
    ),
    "iphone-safari": (
        "iOS",
        "iPhone Safari 兼容 UA",
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{version} "
        "Mobile/15E148 Safari/604.1"),
    ),
    "linux-desktop": (
        "Linux",
        "Linux 桌面版 Chrome UA",
        ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/{chrome} Safari/{safari}"),
    ),
}

# 默认 Chrome/Safari 版本号（2026 参考值；仅用于配置化 UA 生成）
_DEFAULT_CHROME = "126.0.0.0"
_DEFAULT_SAFARI = "537.36"
_DEFAULT_VERSION = "16.0"


def list_profiles() -> list:
    """返回设备配置文件目录 [{name, platform, description}]。"""
    return [
        {"name": n, "platform": p[0], "description": p[1]}
        for n, p in sorted(_DEVICE_PROFILES.items())
    ]


def profile_names() -> Iterable[str]:
    return _DEVICE_PROFILES.keys()


def has_profile(name: str) -> bool:
    return name in _DEVICE_PROFILES


def generate_ua(name: str) -> str:
    """按设备配置文件生成 UA；未知配置返回空串（由调用方回退真实 UA）。"""
    entry = _DEVICE_PROFILES.get(name)
    if entry is None:
        return ""
    template = entry[2]
    return (
        template
        .replace("{chrome}", _DEFAULT_CHROME)
        .replace("{safari}", _DEFAULT_SAFARI)
        .replace("{version}", _DEFAULT_VERSION)
    )


def apply_ua(original_ua: str, profile_name: str) -> str:
    """把 UA 替换为指定设备配置的 UA（配置关闭/未知时返回原 UA）。

    - profile_name 为空 → 返回原 UA（默认关闭，如实声明）
    - profile_name 未知 → 返回原 UA（安全回退）
    """
    if not profile_name:
        return original_ua
    ua = generate_ua(profile_name)
    return ua if ua else original_ua


def is_webkit_compatible(ua: str) -> bool:
    """校验 UA 是否含 AppleWebKit 标记（生成 UA 的一致性自检）。"""
    return bool(ua) and re.search(r"AppleWebKit/[\d.]+", ua) is not None
