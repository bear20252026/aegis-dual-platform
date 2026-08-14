# -*- coding: utf-8 -*-
"""theme.py —— Fluent Mica × Apple Liquid Glass 融合设计系统主题（v2.1.3 重设计）。

设计来源（两者兼收，服从项目 P0 规则）：
- Microsoft Edge / Fluent 2：云母（Mica）着色半透明框架表面、活动标签与工具栏
  「融合成一体」的层级语言、圆角卡片与细发丝分隔线、acrylic 弹层；
- Apple Liquid Glass：玻璃胶囊（地址栏/搜索框/CTA）、顶部镜面高光 + 底部内阴影
  营造的玻璃厚度、单一强调色 #0071e3、全尺寸负字距。

令牌纪律（P0）：
- 全部颜色集中在 _BASE / _CHROME 令牌，其余模块通过 token / to_qcolor / chrome()
  取色，不散落硬编码；不使用 emoji 图标；禁用紫色渐变。
- QSS 与 QPainter 自绘共用同一套令牌（icon_stroke / chrome / to_qcolor），
  保证主题切换时壳层手绘件与控件样式同步。

对外 API（保持向后兼容）：
- APPLE_BLUE 等常量、ApplePalette、style_for / build_qss
- icon_stroke / to_qcolor / _adjust_alpha / font_family_css / load_app_font
- RADIUS_* 圆角档位、TOUCH_TARGET
新增（v2.1.3）：
- chrome(dark)：标签栏/工具栏「云母面」配色（QPainter 自绘与 QSS 同源）
- RADIUS_TAB：标签圆角（Edge 风格 10px）
"""

import os
import sys

# ---------------------------------------------------------------------- #
# 调色板（严格取自 DESIGN.md 的 token）
# ---------------------------------------------------------------------- #
APPLE_BLUE = "#0071e3"          # 唯一强调色（交互元素）
LINK_BLUE_LIGHT = "#0066cc"     # 浅底链接
LINK_BLUE_DARK = "#2997ff"      # 深底链接
NEAR_BLACK = "#1d1d1f"          # 浅底主文本 / 深色按钮填充
LIGHT_BG = "#f5f5f7"            # 浅色系背景
PURE_BLACK = "#000000"          # 深色系背景

# 图标描边：Apple 分层灰（secondaryLabel），对 #f5f5f7 / #000000 均过 WCAG AA
ICON_LIGHT = "rgba(60,60,67,0.6)"
ICON_DARK = "rgba(235,235,245,0.6)"

# ---------------------------------------------------------------------- #
# 圆角档位（U-6：全局统一，禁止再出现游离半径）
# ---------------------------------------------------------------------- #
RADIUS_CONTROL = 8      # 小控件：工具按钮、菜单项、列表项
RADIUS_TAB = 10         # 标签页（v2.1.3：Edge 风格顶部圆角卡片）
RADIUS_INPUT = 12       # 输入类：对话框输入框、下拉框
RADIUS_CARD = 12        # 卡片：菜单、列表面板、拨号卡片
RADIUS_CONTAINER = 18   # 容器：浮动栏、分组框等大块浮层
RADIUS_PILL = 980       # 胶囊概念值（HTML/CSS 适用；980px 真生效）
# v2.1.3 实测：Qt QSS 的 border-radius 超过控件半高后**不会**钳制成胶囊，
# 反而退化为小圆角。因此 QSS 侧一律用 RADIUS_CAPSULE（≈常见控件高度的一半），
# RADIUS_PILL 仅供 HTML 页面使用。
RADIUS_CAPSULE = 20     # Qt QSS 胶囊控件（地址栏/按钮，高度约 32~40px）

# ---------------------------------------------------------------------- #
# 触控目标（U-3）：Apple HIG 桌面指针设备最小 28pt，此处取 40px 兼顾触屏本
# ---------------------------------------------------------------------- #
TOUCH_TARGET = 40
_TOOLBTN_PAD_V = 7
_TOOLBTN_PAD_H = 12

_BASE = {
    "dark": {
        "bg": PURE_BLACK,                       # 窗口主背景：纯黑（Apple 影剧院感）
        "bg_elevated": "#1c1c1e",               # 菜单/对话框浮层（深空灰）
        "surface": "#272729",                   # Dark Surface 1：卡片
        "surface_hi": "#2a2a2d",                # Dark Surface 4：最高层卡片
        "glass": "rgba(29,29,31,0.82)",         # 玻璃工具栏（备用，渐变优先）
        "panel": "rgba(255,255,255,0.05)",      # 面板弱提亮
        "panel_strong": "rgba(255,255,255,0.09)",
        "input": "rgba(255,255,255,0.07)",      # 输入框底色
        "border": "rgba(255,255,255,0.12)",     # 发丝边
        "border_soft": "rgba(255,255,255,0.07)",
        "fg": "#ffffff",                        # 深底主文本：纯白
        "sub": "rgba(255,255,255,0.74)",        # 次要文本
        "muted": "rgba(255,255,255,0.40)",      # 弱化文本
        "hover": "rgba(255,255,255,0.085)",
        "active": "rgba(255,255,255,0.14)",
        "link": LINK_BLUE_DARK,
        "scroll": "rgba(255,255,255,0.24)",
        "scroll_hover": "rgba(255,255,255,0.42)",
        # 液态玻璃：顶部高光 / 中部透色 / 底部微阴影
        "glass_top": "rgba(255,255,255,0.20)",
        "glass_mid": "rgba(29,29,31,0.52)",
        "glass_bottom": "rgba(0,0,0,0.32)",
        "rim": "rgba(255,255,255,0.18)",
        "shadow": "rgba(0,0,0,0.50)",           # 供 HTML 浮层 box-shadow 复用
        "icon": ICON_DARK,                      # SVG 图标描边
    },
    "light": {
        "bg": LIGHT_BG,                         # 浅灰 #f5f5f7
        "bg_elevated": "#ffffff",
        "surface": "#ffffff",
        "surface_hi": "#fafafc",                # Button Default Light
        "glass": "rgba(245,245,247,0.86)",      # 浅色玻璃工具栏
        "panel": "#ffffff",
        "panel_strong": "#fafafc",
        "input": "rgba(0,0,0,0.045)",
        "border": "rgba(0,0,0,0.12)",
        "border_soft": "rgba(0,0,0,0.06)",
        "fg": NEAR_BLACK,                       # 近黑 #1d1d1f
        "sub": "rgba(0,0,0,0.72)",              # Black 72%
        "muted": "rgba(0,0,0,0.45)",            # Black 45%
        "hover": "rgba(0,0,0,0.05)",
        "active": "#e8e8ed",                    # Button Active
        "link": LINK_BLUE_LIGHT,
        "scroll": "rgba(0,0,0,0.20)",
        "scroll_hover": "rgba(0,0,0,0.36)",
        # 液态玻璃：顶部高光 / 中部透色 / 底部微阴影
        "glass_top": "rgba(255,255,255,0.85)",
        "glass_mid": "rgba(245,245,247,0.60)",
        "glass_bottom": "rgba(0,0,0,0.08)",
        "rim": "rgba(0,0,0,0.12)",
        "shadow": "rgba(0,0,0,0.16)",
        "icon": ICON_LIGHT,                     # SVG 图标描边
    },
}

# ---------------------------------------------------------------------- #
# 云母外框（标签栏 + 工具栏）配色：QPainter 自绘与 QSS 同源（v2.1.3 新增）
# Edge 融合式层级：活动标签填充 == 工具栏渐变首段颜色，视觉上"粘"在一起。
# ---------------------------------------------------------------------- #
_CHROME = {
    "dark": {
        "tab_active": "#242529",        # 活动标签表面（== 工具栏顶端）
        "tab_gradient_mid": "#1d1e21",  # 工具栏渐变中段
        "tab_gradient_base": "#141517", # 工具栏渐变底段（贴近内容区）
        "tab_hover": "rgba(255,255,255,0.17)",
        # v2.1.6 对比度拉满：深底一律白字（纯白、全不透明），不再压暗非活动
        # 标签文字；活动/非活动靠"底色亮度 + 强调条 + 加粗"区分，保证可读。
        "tab_inactive_fg": "#ffffff",
        "tab_inactive_bg": "rgba(255,255,255,0.10)",
        "tab_active_fg": "#ffffff",
        "tab_rim": "rgba(255,255,255,0.22)",      # 活动标签顶部镜面高光
        "tab_edge": "rgba(255,255,255,0.12)",     # 标签侧发丝边
        "separator": "rgba(255,255,255,0.14)",    # 非活动标签间分隔线
        "close_hover": "rgba(255,255,255,0.18)",
        "placeholder_bg": "rgba(255,255,255,0.14)",
        "muted_icon": "rgba(235,235,245,0.75)",
    },
    "light": {
        "tab_active": "#ffffff",
        "tab_gradient_mid": "#f7f8fa",
        "tab_gradient_base": "#eef0f3",
        "tab_hover": "rgba(0,0,0,0.10)",
        # v2.1.6 对比度拉满：浅底一律黑字（近黑全不透明）。
        "tab_inactive_fg": "#1d1d1f",
        "tab_inactive_bg": "rgba(0,0,0,0.055)",
        "tab_active_fg": "#1d1d1f",
        "tab_rim": "rgba(255,255,255,0.90)",
        "tab_edge": "rgba(0,0,0,0.07)",
        "separator": "rgba(0,0,0,0.14)",
        "close_hover": "rgba(0,0,0,0.12)",
        "placeholder_bg": "rgba(0,0,0,0.08)",
        "muted_icon": "rgba(60,60,67,0.75)",
    },
}


def chrome(dark: bool, accent: str = APPLE_BLUE) -> dict:
    """返回外框（标签栏/工具栏）配色令牌字典。

    供 tab_strip.py 的 QPainter 自绘与本模块 QSS 共用同一套色，
    保证主题切换时壳层手绘件与控件样式同步。accent 仅影响聚焦/加载环。
    """
    d = dict(_CHROME["dark" if dark else "light"])
    d["accent"] = accent or APPLE_BLUE
    d["dark"] = dark
    return d


def _split_rgba(color: str):
    """把 token 拆成 (#RRGGBB, alpha)，供只认十六进制的场景（SVG）使用。"""
    if color.startswith("rgba"):
        parts = [p.strip() for p in color[5:-1].split(",")]
        r, g, b = (int(float(v)) for v in parts[:3])
        return "#{:02x}{:02x}{:02x}".format(r, g, b), float(parts[3])
    return color, 1.0


def icon_stroke(dark: bool):
    """图标描边色：返回 (hex, opacity)，对应 SVG 的 stroke/stroke-opacity。"""
    return _split_rgba(ICON_DARK if dark else ICON_LIGHT)


def to_qcolor(color: str):
    """把 token（#RRGGBB 或 rgba(...)）转为 QColor，供 QPainter 自绘复用同一套色。"""
    from PySide6.QtGui import QColor
    if color.startswith("rgba"):
        parts = [p.strip() for p in color[5:-1].split(",")]
        r, g, b = (int(float(v)) for v in parts[:3])
        return QColor(r, g, b, max(0, min(255, round(float(parts[3]) * 255))))
    return QColor(color)


def _adjust_alpha(color: str, alpha: float) -> str:
    """把 #RRGGBB / rgba(...) 转为带指定透明度的 rgba 字符串。"""
    if color.startswith("rgba"):
        inner = color[5:-1]
        parts = [p.strip() for p in inner.split(",")]
        return f"rgba({parts[0]},{parts[1]},{parts[2]},{alpha})"
    c = color.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


class ApplePalette:
    """一次主题解析后的调色板。"""

    def __init__(self, dark: bool, accent: str = APPLE_BLUE):
        base = _BASE["dark" if dark else "light"]
        self.dark = dark
        self.accent = accent or APPLE_BLUE
        # hover 态按 DESIGN.md "Hover: background brightens slightly" 提亮
        self.accent_hover = _lighten_hex(self.accent, 0.10)
        self.accent_pressed = _lighten_hex(self.accent, -0.10)
        for k, v in base.items():
            setattr(self, k, v)
        # 云母外框令牌并入调色板（QSS 模板统一用 p.xxx 引用）
        for k, v in _CHROME["dark" if dark else "light"].items():
            setattr(self, k, v)


def _lighten_hex(color: str, amount: float) -> str:
    """按 amount（-1~1）提亮/压暗一个 hex 色。"""
    try:
        c = color.lstrip("#")
        r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))

        def adj(v):
            return max(0, min(255, int(v + 255 * amount)))
        return "#{:02x}{:02x}{:02x}".format(adj(r), adj(g), adj(b))
    except Exception:
        return color


# ---------------------------------------------------------------------- #
# 字体（U-1：单一家族，QSS 与自绘同源）
# ---------------------------------------------------------------------- #
# 随包字体优先，其后是各平台的 Apple/系统回退（SF Pro 为 Apple 专属，非 macOS 无）
_FONT_FALLBACKS = ("Inter", "SF Pro Display", "SF Pro Text", "Helvetica Neue",
                   "Segoe UI", "Microsoft YaHei")
APP_FONT_FAMILY = _FONT_FALLBACKS[0]   # 载入后覆写为真实家族名
_FONT_LOADED = False


def _font_dir() -> str:
    """随包字体目录（兼容 PyInstaller 冻结后的 _MEIPASS）。"""
    root = getattr(sys, "_MEIPASS", None) or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "assets", "fonts")


def load_app_font(app=None) -> str:
    """载入 assets/fonts 下的字体并设为应用默认字体，返回最终家族名。

    没有随包字体时退化为字体栈里第一个系统已装家族；两种情况下 QSS 与
    QPainter 自绘都会落到同一个家族，不再出现 Segoe UI / 雅黑混排。
    """
    global APP_FONT_FAMILY, _FONT_LOADED
    if _FONT_LOADED:
        return APP_FONT_FAMILY
    _FONT_LOADED = True

    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    families = []
    fdir = _font_dir()
    if os.path.isdir(fdir):
        for name in sorted(os.listdir(fdir)):
            if name.lower().endswith((".otf", ".ttf", ".ttc")):
                fid = QFontDatabase.addApplicationFont(os.path.join(fdir, name))
                if fid >= 0:
                    families += QFontDatabase.applicationFontFamilies(fid)
    if families:
        APP_FONT_FAMILY = families[0]
    else:
        installed = set(QFontDatabase.families())
        for cand in _FONT_FALLBACKS:
            if cand in installed:
                APP_FONT_FAMILY = cand
                break

    app = app or QApplication.instance()
    if app is not None:
        f = app.font()
        f.setFamily(APP_FONT_FAMILY)
        app.setFont(f)
    return APP_FONT_FAMILY


def font_family_css() -> str:
    """CSS/QSS 用字体栈：随包家族在前，系统回退在后（HTML 页面复用同一串）。"""
    stack = [APP_FONT_FAMILY] + [f for f in _FONT_FALLBACKS
                                 if f != APP_FONT_FAMILY]
    return ", ".join(f'"{f}"' for f in stack) + ", sans-serif"


def _font_stack() -> str:
    """QSS 字体栈（与 HTML 新标签页共用同一家族名）。"""
    return font_family_css()


# ---------------------------------------------------------------------- #
# QSS 构建（v2.1.3：Fluent Mica × Apple Liquid Glass）
# ---------------------------------------------------------------------- #
def build_qss(p: ApplePalette, font_size: int = 13) -> str:
    """基于调色板生成整套融合风格 QSS（字号随配置实时生效）。"""
    ls = -0.01  # 负字距：Apple 全尺寸紧排
    # 玻璃面：顶部高光 -> 中部透色 -> 底部微阴影
    glass_bar = (
        f"qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        f"stop:0 {p.glass_top},stop:0.45 {p.glass_mid},stop:1 {p.glass_bottom})"
    )
    # 云母工具栏：活动标签色起笔，向下收深——与活动标签"融合"（Edge 语言）
    mica_bar = (
        f"qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        f"stop:0 {p.tab_active},stop:0.55 {p.tab_gradient_mid},"
        f"stop:1 {p.tab_gradient_base})"
    )
    # 输入框玻璃（顶部一抹高光）
    glass_input = (
        f"qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        f"stop:0 {_adjust_alpha(p.glass_top, 0.10)},"
        f"stop:0.5 {p.input},stop:1 {p.input})"
    )
    # 地址栏玻璃胶囊：比普通输入更强的镜面
    glass_address = (
        f"qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        f"stop:0 {_adjust_alpha(p.glass_top, 0.16)},"
        f"stop:0.45 {p.input},stop:1 {_adjust_alpha(p.glass_bottom, 0.10)})"
    )
    # 主 CTA：accent + 顶部白高光（液态玻璃光泽）
    cta = (
        f"qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        f"stop:0 {_lighten_hex(p.accent, 0.22)},"
        f"stop:0.5 {p.accent},stop:1 {p.accent_pressed})"
    )
    sel_bg = _adjust_alpha(p.accent, 0.34 if p.dark else 0.18)
    return f"""
    * {{ outline: none; }}

    QWidget {{
        background-color: {p.bg};
        color: {p.fg};
        font-family: {_font_stack()};
        font-size: {font_size}px;
        letter-spacing: {ls}em;
    }}

    /* 主窗口透明，让 DWM 毛玻璃透出（Liquid Glass 前提） */
    QMainWindow {{ background: transparent; }}
    BrowserTabWidget {{ background: transparent; }}
    QTabWidget::pane {{ border: none; background: transparent; }}
    QStackedWidget {{ background: transparent; }}

    /* ---- 菜单栏（浮于云母之上，菜单本体为 acrylic 弹层） ---- */
    QMenuBar {{
        background: transparent;
        color: {p.sub};
        padding: 2px 8px;
    }}
    QMenuBar::item {{
        padding: 5px 10px; border-radius: {RADIUS_CONTROL}px;
        background: transparent;
    }}
    QMenuBar::item:selected {{ background: {p.hover}; color: {p.fg}; }}

    QMenu {{
        background-color: {p.bg_elevated};
        border: 1px solid {p.border_soft};
        border-radius: {RADIUS_CARD}px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 26px; border-radius: {RADIUS_CONTROL}px; color: {p.fg};
    }}
    QMenu::item:selected {{ background: {p.hover}; }}
    QMenu::item:disabled {{ color: {p.muted}; }}
    QMenu::separator {{ height: 1px; background: {p.border_soft}; margin: 5px 8px; }}

    /* ---- 导航工具栏：云母面（与活动标签融合） ---- */
    QToolBar {{
        background: {mica_bar};
        border: none;
        border-bottom: 1px solid {p.border_soft};
        padding: 6px 10px;
        spacing: 4px;
    }}
    #bookmarkToolBar {{
        background: {p.tab_gradient_base};
        border: none;
        border-bottom: 1px solid {p.border_soft};
        padding: 2px 10px;
    }}

    /* ---- 标签页容器（自绘） ---- */
    QTabBar {{ background: transparent; qproperty-drawBase: 0; }}

    /* ---- 输入框（通用：云 mica 之上的玻璃圆角） ---- */
    QLineEdit {{
        background: {glass_input};
        border: 1px solid {p.border_soft};
        border-radius: {RADIUS_INPUT}px;
        padding: 7px 14px;
        color: {p.fg};
        selection-background-color: {p.accent};
        selection-color: #ffffff;
        letter-spacing: {ls}em;
    }}
    QLineEdit:hover {{ border-color: {p.border}; }}
    QLineEdit:focus {{ border: 1px solid {p.accent}; background: {p.input}; }}
    QLineEdit:disabled {{ color: {p.muted}; }}

    /* 地址栏：液态玻璃胶囊（Edge/Safari 共同语言），聚焦光环为强调色 */
    QLineEdit#addressBar {{
        background: {glass_address};
        border: 1px solid {p.rim};
        border-radius: {RADIUS_CAPSULE}px;
        padding: 7px 18px;
        min-height: 22px;
    }}
    QLineEdit#addressBar:hover {{ border-color: {p.border}; }}
    QLineEdit#addressBar:focus {{
        border: 1px solid {p.accent};
        background: {p.input};
    }}

    /* 地址栏联想浮层：玻璃卡片 + 内嵌列表 */
    QFrame#addressPopup {{
        background-color: {p.bg_elevated};
        border: 1px solid {p.border_soft};
        border-radius: {RADIUS_CARD}px;
    }}
    QFrame#addressPopup QListWidget {{
        background: transparent; border: none; padding: 2px;
    }}
    QFrame#addressPopup QListWidget::item {{
        padding: 6px 10px; border-radius: {RADIUS_CONTROL}px;
    }}

    /* ---- 工具按钮：玻璃 hover / 按下反馈（40px 触控目标） ---- */
    QToolButton {{
        background: transparent;
        border: none;
        border-radius: {RADIUS_CONTROL}px;
        color: {p.fg};
        padding: {_TOOLBTN_PAD_V}px {_TOOLBTN_PAD_H}px;
        min-height: {TOUCH_TARGET - _TOOLBTN_PAD_V * 2}px;
        min-width: {TOUCH_TARGET - _TOOLBTN_PAD_H * 2}px;
    }}
    QToolButton:hover {{
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 {_adjust_alpha(p.glass_top, 0.16)}, stop:1 {p.hover});
    }}
    QToolButton:pressed {{ background: {p.active}; }}
    QToolButton:checked {{ background: {p.accent}; color: #ffffff; }}
    QToolButton:disabled {{ color: {p.muted}; }}

    /* ---- 书签栏 ---- */
    #bookmarkBar {{ background: transparent; }}
    #bookmarkBar QToolButton {{
        font-size: 12px; padding: 4px 10px;
        border-radius: {RADIUS_CONTROL}px;
        min-height: 22px; min-width: 0;
        color: {p.sub};
    }}
    #bookmarkBar QToolButton:hover {{ color: {p.fg}; background: {p.hover}; }}
    #bookmarkHint {{ color: {p.muted}; font-size: 12px; background: transparent; }}

    /* ---- 浮动栏（查找/下载：悬浮玻璃圆角容器） ---- */
    #findBar {{
        background: {glass_bar};
        border: 1px solid {p.rim};
        border-radius: {RADIUS_CONTAINER}px;
    }}
    #findBar QLineEdit {{
        border-radius: 14px; padding: 4px 14px;
        background: {p.input};
    }}
    #downloadBar {{
        background: {glass_bar};
        border: 1px solid {p.rim};
        border-radius: {RADIUS_CONTAINER}px;
    }}

    /* ---- 状态栏（极细发丝线，玻璃上漂浮） ---- */
    QStatusBar {{
        background: {p.tab_gradient_base};
        color: {p.sub};
        border-top: 1px solid {p.border_soft};
    }}
    QStatusBar::item {{ border: none; }}
    QLabel {{ background: transparent; }}

    /* ---- 列表 / 文本区（卡片化） ---- */
    QListWidget, QTreeWidget, QTextEdit, QPlainTextEdit, QTableView {{
        background-color: {p.panel};
        border: 1px solid {p.border_soft};
        border-radius: {RADIUS_CARD}px;
        padding: 6px;
        alternate-background-color: transparent;
    }}
    QListWidget::item, QTreeWidget::item {{
        padding: 8px 10px; border-radius: {RADIUS_CONTROL}px;
    }}
    QListWidget::item:selected, QTreeWidget::item:selected {{
        background: {sel_bg};
        color: {p.fg};
    }}
    QListWidget::item:hover:!selected, QTreeWidget::item:hover:!selected {{
        background: {p.hover};
    }}

    /* ---- 分组框 / 复选框（Fluent 圆角勾选） ---- */
    QGroupBox {{
        border: 1px solid {p.border_soft};
        border-radius: {RADIUS_CONTAINER}px;
        margin-top: 12px;
        padding: 14px;
        background: {p.panel};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; left: 12px; padding: 0 6px;
        color: {p.fg}; font-weight: 600;
    }}
    QCheckBox, QRadioButton {{ color: {p.fg}; spacing: 8px; background: transparent; }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 18px; height: 18px; border-radius: 6px;
        border: 1px solid {p.border}; background: {p.input};
    }}
    QRadioButton::indicator {{ border-radius: 9px; }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
        border-color: {p.accent};
    }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {p.accent}; border-color: {p.accent};
    }}

    /* ---- 数字输入 ---- */
    QSpinBox, QDoubleSpinBox {{
        background: {p.input};
        border: 1px solid {p.border_soft};
        border-radius: {RADIUS_INPUT}px;
        padding: 5px 10px; color: {p.fg};
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {p.accent}; }}

    /* ---- 按钮：次级胶囊 + 光泽主按钮（Fluent accent / Apple gloss） ---- */
    QPushButton {{
        background: transparent;
        border: 1px solid {p.border};
        border-radius: 18px;
        padding: 7px 20px;
        color: {p.fg};
    }}
    QPushButton:hover {{ background: {p.hover}; }}
    QPushButton:pressed {{ background: {p.active}; }}
    QPushButton:disabled {{ color: {p.muted}; border-color: {p.border_soft}; }}
    QPushButton:default {{
        background: {cta};
        color: #ffffff;
        border: 1px solid transparent;
        border-radius: 18px;
        font-weight: 600;
    }}
    QPushButton:default:hover {{
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 {_lighten_hex(p.accent, 0.30)},
            stop:0.5 {p.accent_hover},stop:1 {p.accent});
    }}
    QPushButton:default:pressed {{ background: {p.accent_pressed}; }}

    /* ---- 滚动条（细、弱、圆角：Fluent 悬浮式） ---- */
    QScrollBar:vertical {{
        background: transparent; width: 10px; margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {p.scroll}; border-radius: 4px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {p.scroll_hover}; }}
    QScrollBar:horizontal {{
        background: transparent; height: 10px; margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {p.scroll}; border-radius: 4px; min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {p.scroll_hover}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* ---- 下拉列表（acrylic 弹层） ---- */
    QComboBox {{
        background: {p.input}; border: 1px solid {p.border_soft};
        border-radius: {RADIUS_INPUT}px; padding: 6px 12px; color: {p.fg};
    }}
    QComboBox:hover {{ border-color: {p.border}; }}
    QComboBox:focus {{ border-color: {p.accent}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {p.bg_elevated};
        border: 1px solid {p.border_soft}; border-radius: {RADIUS_CARD}px;
        outline: none; padding: 4px;
        selection-background-color: {p.hover};
        selection-color: {p.fg};
    }}

    /* ---- 滑块（Fluent：轨道 + 悬浮圆钮） ---- */
    QSlider::groove:horizontal {{
        height: 4px; background: {p.border_soft}; border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {p.accent}; border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 18px; height: 18px; margin: -7px 0;
        background: #ffffff;
        border: 1px solid {p.border};
        border-radius: 9px;
    }}

    /* ---- 进度条（细线 accent） ---- */
    QProgressBar {{
        border: none; background: {p.border_soft};
        border-radius: 3px; height: 6px; text-align: center;
    }}
    QProgressBar::chunk {{
        background: {p.accent};
        border-radius: 3px;
    }}

    QToolTip {{
        background: {p.bg_elevated}; color: {p.fg};
        border: 1px solid {p.border_soft}; border-radius: {RADIUS_CONTROL}px;
        padding: 4px 10px;
    }}

    /* 对话框保持不透明以可读（玻璃只留给窗口外框） */
    QDialog {{ background-color: {p.bg}; color: {p.fg}; }}
    """


def style_for(dark: bool, accent: str = APPLE_BLUE, font_size: int = 13) -> str:
    """便捷入口：根据主题返回完整 QSS。"""
    return build_qss(ApplePalette(dark, accent), font_size)


# 兼容旧引用
GlassPalette = ApplePalette
