# -*- coding: utf-8 -*-
"""icons.py —— 统一内联 SVG 图标（套壳浏览器 UI 专用）。

规则（对照项目 P0 绝对规则）：
- 不使用任何 emoji 作为功能图标；
- 统一描边、可矢量缩放、语义明确的 SVG；
- 全项目仅此一套，不混用其他图标库；
- 尺寸由调用方 setIconSize 控制（16/20/24px）。
"""

from PySide6.QtCore import QByteArray, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme import APPLE_BLUE, icon_stroke

# 描边色来自主题 token（Apple 分层灰），不再写死中性灰；set_theme() 随主题切换
_STROKE, _STROKE_OPACITY = icon_stroke(True)
_ACCENT = APPLE_BLUE   # 唯一强调色（DESIGN.md）


def set_theme(dark: bool):
    """跟随应用主题切换图标描边（浅底用深灰、深底用浅灰，满足 WCAG AA）。"""
    global _STROKE, _STROKE_OPACITY
    _STROKE, _STROKE_OPACITY = icon_stroke(dark)
    _CACHE.clear()   # 描边色已变，旧渲染缓存全部失效

_PATHS = {
    "back":     '<path d="M15 5l-7 7 7 7" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "forward":  '<path d="M9 5l7 7-7 7" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "reload":   '<path d="M20 11a8 8 0 1 0-2.3 5.7" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M20 5v6h-6" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "home":     '<path d="M4 11l8-7 8 7" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 10v9h12v-9" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "plus":     '<path d="M12 5v14M5 12h14" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "menu":     '<path d="M4 7h16M4 12h16M4 17h16" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "close":    '<path d="M6 6l12 12M18 6 6 18" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "search":   '<circle cx="11" cy="11" r="7" fill="none" stroke="{s}" stroke-width="1.8"/><path d="M21 21l-4.3-4.3" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round"/>',
    "history":  '<path d="M3 12a9 9 0 1 0 3-6.7" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round"/><path d="M3 4v5h5" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 8v4l3 2" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "bookmark": '<path d="M6 4h12v16l-6-4-6 4z" fill="none" stroke="{s}" stroke-width="1.8" stroke-linejoin="round"/>',
    "lock":     '<rect x="4" y="10" width="16" height="10" rx="2" fill="none" stroke="{s}" stroke-width="1.8"/><path d="M7 10V8a5 5 0 0 1 10 0v2" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round"/>',
    "warning":  '<path d="M12 3 2 20h20L12 3z" fill="none" stroke="{s}" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 9v4M12 16v.6" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round"/>',
    "check":    '<path d="M5 12l5 5 9-11" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "star":     '<path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z" fill="{a}" stroke="none"/>',
    "star_outline": '<path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z" fill="none" stroke="{s}" stroke-width="1.6" stroke-linejoin="round"/>',
    "source":   '<path d="M9 8l-4 4 4 4M15 8l4 4-4 4" fill="none" stroke="{s}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
}

# 渲染结果缓存：(name, size) -> QPixmap。
# 图标集合固定（十几枚），缓存避免高频调用（书签栏/标签栏刷新）反复建
# QPixmap + QSvgRenderer；主题切换时描边色变化，由 set_theme() 整体失效。
_CACHE = {}
_CACHE_MAX = 256


def _render(name: str, size: int = 24) -> QPixmap:
    key = (name, size)
    pm = _CACHE.get(key)
    if pm is not None:
        return pm
    svg = _PATHS[name].format(s=_STROKE, a=_ACCENT)
    doc = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'width="{size}" height="{size}" stroke-opacity="{_STROKE_OPACITY}">'
        f'{svg}</svg>'
    )
    rend = QSvgRenderer(QByteArray(doc.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    rend.render(p)
    p.end()
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = pm
    return pm


def icon(name: str) -> QIcon:
    """返回指定名称的内联 SVG 图标（QIcon）。"""
    if name not in _PATHS:
        name = "search"
    return QIcon(_render(name))


def pixmap(name: str, size: int = 16) -> QPixmap:
    return _render(name, size)
