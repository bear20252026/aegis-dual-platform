"""url_utils.py —— URL 规整与导航安全校验（单文件单职责）。

从 api_bridge.py 拆出（结构审计：api_bridge 574 行超 500 行软目标，
本文件收敛其模块级纯函数与常量，不依赖 Api 类状态，可独立单测）。
"""

import urllib.parse
from pathlib import Path

# 应用根目录（aegis_source/），用于定位 shell/start.html
ROOT = Path(__file__).resolve().parent.parent
START_URL = (ROOT / "shell" / "start.html").as_uri()

# 搜索引擎表：key -> (名称, 搜索 URL 模板)
SEARCH_ENGINES: dict[str, tuple[str, str]] = {
    "baidu":  ("百度", "https://www.baidu.com/s?wd={}"),
    "bing":   ("必应", "https://www.bing.com/search?q={}"),
    "google": ("谷歌", "https://www.google.com/search?q={}"),
    "sogou":  ("搜狗", "https://www.sogou.com/web?query={}"),
}
DEFAULT_ENGINE = "baidu"


def normalize_url(text: str | None, engine: str = DEFAULT_ENGINE) -> str:
    """把用户输入变成可导航 URL：无协议补 https://，非网址当搜索词。"""
    text = (text or "").strip()
    if not text:
        return START_URL
    if text == "about:blank":
        return "about:blank"
    lowered = text.lower()
    # L-2 修复（防御性安全审查）：移除 file:// 放行（纵深一致——file://
    # 仅受信路径（START_URL 壳页）单独处理——防新调用点漏配成本地读取面）
    if lowered.startswith(("http://", "https://")):
        return text
    # 含空格或没有点号 → 视为搜索
    if " " in text or "." not in text:
        template = SEARCH_ENGINES.get(engine, SEARCH_ENGINES[DEFAULT_ENGINE])[1]
        return template.format(urllib.parse.quote(text))
    return "https://" + text


def is_navigation_safe(url: str) -> bool:
    """H-C1 审计修复：外部导航目标安全校验。

    只放行 http/https 与显式 about:blank；file:/javascript:/vbscript:/
    data:/blob: 等一律拒绝（复用 security.safe_url 白名单，
    allow_internal=False 确保 data:/blob: 等内部伪协议不被外部输入放行）。
    """
    if not url:
        return False
    if url == "about:blank":
        return True
    from .security import safe_url
    return bool(safe_url(url, allow_internal=False))
