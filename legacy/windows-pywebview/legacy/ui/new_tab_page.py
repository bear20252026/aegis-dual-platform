"""new_tab_page.py —— 新建标签页（快捷拨号首页，v2.1.3 视觉升级）。

极光云母玻璃态背景 + 中央玻璃搜索胶囊 + 玻璃拨号卡网格（最近常用 + 书签），
点击拨号卡片打开对应网址。

视觉语言（Fluent mesh × Apple glass）：拨号卡为半透明玻璃卡片——
顶部镜面高光、发丝描边、悬停轻微上浮感；站名 Apple 式紧排。
安全不变式：所有 URL 仅来自历史记录/书签/内置白名单常量，
导航统一经 navigate 信号走主窗口 safe_url 关口。
"""

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .glass import AuroraBackground
from .icons_dial import brand_char, brand_palette
from .theme import APP_FONT_FAMILY, RADIUS_CARD, ApplePalette, _adjust_alpha, to_qcolor

# 极光背景恒为深色，故此页固定用深色 token
_P = ApplePalette(True)

# 与 HTML 新标签页同一套排印参数
_TITLE_PX = 56
_TITLE_LS = -0.28
_ICO_PX = 56            # 品牌 squircle 图标边长（与 HTML 版 56px 一致）
_ICO_TEXT_PX = 24       # 图标内字符基准字号（CJK）
_NAME_PX = 14
_NAME_LS = -0.224
_CARD_W, _CARD_H = 108, 122

# 默认快捷拨号（常见网站）
DEFAULT_DIALS = [
    ("百度", "https://www.baidu.com", "B"),
    ("必应", "https://www.bing.com", "M"),
    ("知乎", "https://www.zhihu.com", "知"),
    ("哔哩哔哩", "https://www.bilibili.com", "b"),
    ("GitHub", "https://github.com", "G"),
    ("掘金", "https://juejin.cn", "掘"),
    ("CSDN", "https://www.csdn.net", "C"),
    ("腾讯新闻", "https://news.qq.com", "Q"),
    ("淘宝", "https://www.taobao.com", "淘"),
    ("京东", "https://www.jd.com", "京"),
]


class DialCard(QPushButton):
    """拨号卡片：圆形图标 + 站点名。"""

    # (url)
    activated = Signal(str)

    def __init__(self, name: str, url: str, letter: str, parent=None):
        super().__init__(parent)
        self.url = url
        self._name = name
        # v2.1.4：图标字符跟随品牌表（HTML 版同源逻辑），不再一律取标题首字
        try:
            from urllib.parse import urlparse
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            host = ""
        self._glyph = brand_char(host, name) or letter or "?"
        self._icon_colors = brand_palette(host)
        self.setObjectName("dialCard")
        self.setFixedSize(_CARD_W, _CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(lambda: self.activated.emit(self.url))
        self.setToolTip(f"{name}\n{url}")

    def paintEvent(self, event):
        # 液态玻璃卡片：半透明底 + 顶部镜面高光 + 发丝描边（悬停时提亮）
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        hover = self.underMouse()

        # 玻璃底（悬停提亮，营造"上浮"）
        fill = QColor(255, 255, 255, 42 if hover else 26)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(1, 1, w - 2, h - 2, RADIUS_CARD, RADIUS_CARD)

        # 顶部镜面高光（上 45%）
        hi = QLinearGradient(0, 0, 0, h * 0.5)
        hi.setColorAt(0.0, QColor(255, 255, 255, 68 if hover else 46))
        hi.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(hi)
        painter.drawRoundedRect(1, 1, w - 2, h - 2, RADIUS_CARD, RADIUS_CARD)

        # 底部内阴影（玻璃厚度）
        sh = QLinearGradient(0, h * 0.6, 0, h)
        sh.setColorAt(0.0, QColor(0, 0, 0, 0))
        sh.setColorAt(1.0, QColor(0, 0, 0, 40))
        painter.setBrush(sh)
        painter.drawRoundedRect(1, 1, w - 2, h - 2, RADIUS_CARD, RADIUS_CARD)

        # 发丝描边
        painter.setPen(QPen(QColor(255, 255, 255, 56 if hover else 34), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(1.5, 1.5, w - 3, h - 3,
                                RADIUS_CARD, RADIUS_CARD)

        # 品牌 squircle 图标（v2.1.4：与 HTML 新标签页同源的品牌渐变体系；
        # HTML 版另有品牌图形，Qt 版为品牌渐变 + 精致字符徽标）
        icon = _ICO_PX
        ix = (w - icon) // 2
        iy = 16
        top_c = to_qcolor(self._icon_colors[0])
        bot_c = to_qcolor(self._icon_colors[1])
        grad = QLinearGradient(0, iy, 0, iy + icon)
        grad.setColorAt(0.0, top_c)
        grad.setColorAt(1.0, bot_c)
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawRoundedRect(ix, iy, icon, icon, 14, 14)
        # 顶部镜面高光（上半区，iOS 玻璃感）
        painter.save()
        painter.setClipRect(ix, iy, icon, icon // 2)
        gloss = QLinearGradient(0, iy, 0, iy + icon * 0.55)
        gloss.setColorAt(0.0, QColor(255, 255, 255, 78 if hover else 66))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(gloss)
        painter.drawRoundedRect(ix, iy, icon, icon, 14, 14)
        painter.restore()
        # 发丝边
        painter.setPen(QPen(QColor(255, 255, 255, 46), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(ix + 0.5, iy + 0.5, icon - 1, icon - 1, 14, 14)
        # 居中徽标字符（CJK/拉丁分档字号）
        painter.setPen(QColor("#ffffff"))
        f = QFont(APP_FONT_FAMILY)
        is_cjk = self._glyph and ord(self._glyph[0]) > 0x2E00
        f.setPixelSize(_ICO_TEXT_PX if is_cjk else _ICO_TEXT_PX + 3)
        f.setWeight(QFont.DemiBold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, -0.28)
        painter.setFont(f)
        painter.drawText(QRect(ix, iy, icon, icon),
                         Qt.AlignCenter, self._glyph)
        # 名称（Apple 紧排：14px / -0.224px）
        painter.setOpacity(0.86)
        painter.setPen(to_qcolor(_P.fg))
        f2 = QFont(APP_FONT_FAMILY)
        f2.setPixelSize(_NAME_PX)
        f2.setLetterSpacing(QFont.AbsoluteSpacing, _NAME_LS)
        painter.setFont(f2)
        text_top = iy + icon + 10
        painter.drawText(QRect(4, text_top, w - 8, h - text_top - 12),
                         Qt.AlignHCenter | Qt.AlignTop,
                         painter.fontMetrics().elidedText(
                             self._name, Qt.ElideRight, w - 12))
        painter.end()


class NewTabPage(QWidget):
    """新建标签页。"""

    # (url) 打开网址
    navigate = Signal(str)
    # (query) 搜索
    search = Signal(str)

    def __init__(self, config, history, bookmarks, parent=None):
        super().__init__(parent)
        self.config = config
        self._history = history
        self._bookmarks = bookmarks

        # 极光背景
        bg = AuroraBackground(self, accent=config.accent_color)
        self._bg = bg

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;}")
        outer.addWidget(scroll)

        container = QWidget()
        container.setAttribute(Qt.WA_StyledBackground, True)
        container.setStyleSheet("background: transparent;")
        scroll.setWidget(container)

        lay = QVBoxLayout(container)
        lay.setContentsMargins(24, 40, 24, 24)
        lay.setSpacing(16)
        lay.addStretch(1)

        # 标题（56px / 600 / -0.28px，与 HTML 新标签页一致）
        title = QLabel("Aegis", container)
        title.setObjectName("ntpTitle")
        tf = QFont(APP_FONT_FAMILY)
        tf.setPixelSize(_TITLE_PX)
        tf.setWeight(QFont.DemiBold)
        tf.setLetterSpacing(QFont.AbsoluteSpacing, _TITLE_LS)
        title.setFont(tf)
        title.setStyleSheet(f"color:{_P.fg};background:transparent;")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(18)   # 合计 34px 标题下留白

        # 搜索框
        self.search_edit = QLineEdit(container)
        self.search_edit.setPlaceholderText("搜索或输入网址")
        self.search_edit.setFixedHeight(52)
        self.search_edit.setMaximumWidth(620)
        self.search_edit.setStyleSheet(_searchbox_qss(config.accent_color))
        self.search_edit.returnPressed.connect(self._on_search)
        self.search_edit.setFocus()
        lay.addWidget(self.search_edit, 0, Qt.AlignHCenter)
        lay.addSpacing(36)   # 合计 52px 搜索框下留白

        # 快捷拨号
        dials_label = QLabel("快捷拨号", container)
        dials_label.setStyleSheet(
            f"color:{_P.sub};background:transparent;font-size:{_NAME_PX}px;")
        dials_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(dials_label)
        lay.addSpacing(6)

        self.dials_grid = QGridLayout()
        self.dials_grid.setSpacing(14)   # 与 HTML grid gap 一致
        # 拨号网格整体水平居中（v2.1.3：对齐 HTML 新标签页的居中布局）
        grid_row = QHBoxLayout()
        grid_row.addStretch(1)
        grid_row.addLayout(self.dials_grid)
        grid_row.addStretch(1)
        lay.addLayout(grid_row)
        self._rebuild_dials()

        lay.addStretch(2)

    def _on_search(self):
        self.search.emit(self.search_edit.text())

    def _rebuild_dials(self):
        # 清空
        while self.dials_grid.count():
            item = self.dials_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        dials = self._collect_dials()
        col = 0
        for i, (name, url, letter) in enumerate(dials):
            card = DialCard(name, url, letter, self)
            card.activated.connect(self.navigate.emit)
            row = i // 5
            col = i % 5
            self.dials_grid.addWidget(card, row, col)

    def _collect_dials(self):
        """快捷拨号 = 最近访问(历史) 4 个 + 书签若干 + 默认补全。"""
        result = []
        seen = set()
        # 历史最常访问
        for rec in self._history.most_visited(4):
            url = rec["url"]
            if url not in seen:
                seen.add(url)
                letter = (rec["title"] or "?")[:1].upper()
                result.append((rec["title"] or url, url, letter))
        # 书签
        for b in self._bookmarks.all()[:6]:
            url = b["url"]
            if url not in seen:
                seen.add(url)
                letter = (b["title"] or "?")[:1].upper()
                result.append((b["title"] or url, url, letter))
        # 默认补全
        for name, url, letter in DEFAULT_DIALS:
            if url not in seen:
                seen.add(url)
                result.append((name, url, letter))
        return result[:15]

    def refresh(self):
        self._rebuild_dials()


def _searchbox_qss(accent: str) -> str:
    """液态玻璃药丸搜索框：镜面顶光 + 聚焦时强调色光环（v2.1.3）。"""
    fill_hi = _adjust_alpha("#ffffff", 0.20)
    fill = _adjust_alpha("#ffffff", 0.11)
    fill_lo = _adjust_alpha("#ffffff", 0.085)
    edge = _adjust_alpha("#ffffff", 0.22)
    return f"""
    QLineEdit {{
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 {fill_hi}, stop:0.45 {fill}, stop:1 {fill_lo});
        border: 1px solid {edge};
        border-radius: 26px;
        padding: 13px 26px;
        color: {_P.fg};
        font-size: 17px;
    }}
    QLineEdit:hover {{
        border: 1px solid {_adjust_alpha(accent, 0.55)};
    }}
    QLineEdit:focus {{
        border: 2px solid {accent};
        padding: 12px 25px;
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 {fill_hi}, stop:1 {fill});
    }}
    """
