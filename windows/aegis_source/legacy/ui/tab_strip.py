"""tab_strip.py —— Edge 风格融合式标签栏（v2.1.3 重设计）。

视觉语言（Fluent Mica × Apple Liquid Glass，色值全部来自 theme 令牌）：
- 活动标签与下方工具栏「融合」：填充色 == 云母工具栏渐变首段，
  顶部一道镜面高光、两侧发丝边，像从框架表面隆起的一片玻璃；
- 非活动标签透明，悬停浮现柔和洗色；相邻非活动标签之间有发丝分隔线；
- 顶部大圆角（RADIUS_TAB）+ 底部小圆角，卡片式边缘；
- favicon + 标题、加载旋转环、静音指示、固定标签、分组色带、
  悬停关闭按钮等交互能力全部保留。
"""

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QTabBar,
    QTabWidget,
)

from .theme import APPLE_BLUE, RADIUS_TAB, chrome

# 标签切换淡入（U-5）：150ms 平滑缓动，不用弹性曲线
_FADE_MS = 150
_FADE_FROM = 0.55

# 各状态角标类型
_BADGE_LOADING = 0
_BADGE_MUTED = 1
_BADGE_CLOSE = 2


class BrowserTabBar(QTabBar):
    """增强型标签栏。"""

    # 中键/关闭请求关闭某标签（index）
    close_requested = Signal(int)
    # 双击空白新建标签
    new_tab_requested = Signal()
    # 请求固定/取消固定（index, pinned）
    pin_requested = Signal(int, bool)
    # 请求切换静音（index, muted）
    mute_requested = Signal(int, bool)
    # 请求刷新 / 关闭其他
    refresh_requested = Signal(int)
    close_others_requested = Signal(int)
    # 编辑标签分组（打开命名对话框）
    group_edit_requested = Signal(int)
    # 悬停标签变化（-1 = 离开标签栏；用于缩略图预览，B2）
    hover_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDrawBase(False)
        self.setExpanding(False)
        self.setMovable(True)
        self.setUsesScrollButtons(True)
        self.setElideMode(Qt.ElideRight)
        self.setSelectionBehaviorOnRemove(QTabBar.SelectPreviousTab)
        self.setStyleSheet("QTabBar{background:transparent;}")

        self._pinned = {}       # index -> True
        self._muted = {}        # index -> True
        self._loading = {}      # index -> bool
        self._groups = {}       # index -> QColor（分组标签）
        self._hover = -1
        self._last_hover = -1
        self._spin = 0.0
        self._close_hover = None
        self._dark = True
        self._accent = APPLE_BLUE
        # v2.1.5：标签朝向（top=水平顶栏 / left=垂直侧栏，Edge 风）
        self._vertical = False

        # 加载动画计时器（丝滑：约 15fps 步进）
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(66)
        self._spin_timer.timeout.connect(self._advance_spin)

        # 切换/新增标签时的淡入（仅动画期间挂效果，平时不影响玻璃合成）
        self._fade_fx = QGraphicsOpacityEffect(self)
        self._fade_fx.setOpacity(1.0)
        self._fade_fx.setEnabled(False)
        self.setGraphicsEffect(self._fade_fx)
        self._fade = QPropertyAnimation(self._fade_fx, b"opacity", self)
        self._fade.setDuration(_FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.finished.connect(lambda: self._fade_fx.setEnabled(False))

        self.setMouseTracking(True)
        self.currentChanged.connect(self._stop_anim)
        self.currentChanged.connect(lambda _i: self._fade_in())

    # ------------------------------------------------------------------ #
    # 状态设置
    # ------------------------------------------------------------------ #
    def set_pinned(self, index, pinned: bool):
        self._pinned[index] = pinned
        self.update()

    def set_muted(self, index, muted: bool):
        self._muted[index] = muted
        self.update()

    def set_loading(self, index, loading: bool):
        prev = self._loading.get(index, False)
        self._loading[index] = loading
        if loading and not prev:
            if not self._spin_timer.isActive():
                self._spin_timer.start()
        elif not loading:
            self.update()
        if loading and index == self.currentIndex():
            self.update()

    def set_group(self, index, color):
        """设置标签分组色（None 表示移除分组）。"""
        if color is None:
            self._groups.pop(index, None)
        else:
            self._groups[index] = color
        self.update()

    def is_pinned(self, index) -> bool:
        return self._pinned.get(index, False)

    def is_muted(self, index) -> bool:
        return self._muted.get(index, False)

    def _advance_spin(self):
        self._spin = (self._spin + 0.35) % 6.28
        # 仅重绘当前与加载中的标签
        self.update()

    def _stop_anim(self):
        if not any(self._loading.values()):
            self._spin_timer.stop()

    def set_loading_all(self, index_loading: dict):
        """批量设置（用于恢复会话后统一刷新）。"""
        self._loading = index_loading
        if any(self._loading.values()):
            self._spin_timer.start()

    def set_theme(self, dark: bool, accent: str = APPLE_BLUE):
        """跟随应用主题，保证深/浅切换与强调色变更后配色正确刷新。"""
        self._dark = dark
        self._accent = accent or APPLE_BLUE
        self.update()

    def set_vertical(self, vertical: bool):
        """v2.1.5：切换标签朝向（top=水平顶栏 / left=垂直侧栏）。

        垂直模式下把形状置为 RoundedWest（QTabWidget.setTabPosition(West)
        会同步），自绘改走行式渲染（_paint_tab_v）。
        """
        self._vertical = bool(vertical)
        self.setShape(QTabBar.RoundedWest if vertical
                      else QTabBar.RoundedNorth)
        self.update()

    # ------------------------------------------------------------------ #
    # 切换动画
    # ------------------------------------------------------------------ #
    def _fade_in(self):
        """标签成为当前项 / 新标签出现时的 150ms 淡入。"""
        self._fade.stop()
        self._fade_fx.setEnabled(True)
        self._fade.setStartValue(_FADE_FROM)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def tabInserted(self, index):
        super().tabInserted(index)
        self._fade_in()

    # ------------------------------------------------------------------ #
    # 交互事件
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            index = self.tabAt(event.pos())
            if index >= 0:
                self.close_requested.emit(index)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        index = self.tabAt(event.pos())
        self._hover = index
        # 检测悬停在关闭按钮上
        if index >= 0:
            close_rect = self._close_rect(index)
            self._close_hover = index if close_rect.contains(event.pos()) else None
        else:
            self._close_hover = None
        if index != self._last_hover:
            self._last_hover = index
            self.hover_changed.emit(index)
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover = -1
        self._close_hover = None
        if self._last_hover != -1:
            self._last_hover = -1
            self.hover_changed.emit(-1)
        self.update()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.tabAt(event.pos()) < 0:
                self.new_tab_requested.emit()
                return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        index = self.tabAt(event.pos())
        if index < 0:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        a_new = menu.addAction("新建标签页")
        a_close = menu.addAction("关闭标签页")
        a_closeothers = menu.addAction("关闭其他标签页")
        a_pin = menu.addAction("取消固定" if self.is_pinned(index) else "固定标签页")
        a_mute = menu.addAction("取消静音" if self.is_muted(index) else "静音标签页")
        a_group = menu.addAction("设置标签分组…")
        a_refresh = menu.addAction("刷新")
        chosen = menu.exec(event.globalPos())
        if chosen == a_new:
            self.new_tab_requested.emit()
        elif chosen == a_close:
            self.close_requested.emit(index)
        elif chosen == a_closeothers:
            self.close_others_requested.emit(index)
        elif chosen == a_pin:
            self.pin_requested.emit(index, not self.is_pinned(index))
        elif chosen == a_mute:
            self.mute_requested.emit(index, not self.is_muted(index))
        elif chosen == a_group:
            self.group_edit_requested.emit(index)
        elif chosen == a_refresh:
            self.refresh_requested.emit(index)

    # ------------------------------------------------------------------ #
    # 尺寸与几何
    # ------------------------------------------------------------------ #
    def tabSizeHint(self, index):
        pinned = self.is_pinned(index)
        base = super().tabSizeHint(index)
        if self._vertical:
            # 垂直（Edge 风）：整列宽 212，每行高 36；固定行同高
            return QSize(212, 36)
        if pinned:
            base.setWidth(44)
        else:
            base.setWidth(min(max(base.width() + 24, 150), 224))
        base.setHeight(36)
        return base

    def _close_rect(self, index) -> QRect:
        r = self.tabRect(index)
        size = 18
        # 固定标签无关闭按钮
        if self.is_pinned(index):
            return QRect()
        return QRect(r.right() - size - 6, r.center().y() - size // 2,
                     size, size)

    def _left_badge_rect(self, index) -> QRect:
        r = self.tabRect(index)
        size = 14
        return QRect(r.left() + 10, r.center().y() - size // 2, size, size)

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        draw = self._paint_tab_v if self._vertical else self._paint_tab
        for i in range(self.count()):
            draw(painter, i)
        painter.end()

    @staticmethod
    def _tab_path(r: QRectF, top_radius: float, bottom_radius: float):
        """顶部大圆角 + 底部小圆角的卡片路径（Edge 标签形态）。"""
        path = QPainterPath()
        path.moveTo(r.left(), r.bottom() - bottom_radius)
        path.arcTo(r.left(), r.top(), top_radius * 2, top_radius * 2,
                   180, -90)
        path.lineTo(r.right() - top_radius, r.top())
        path.arcTo(r.right() - top_radius * 2, r.top(),
                   top_radius * 2, top_radius * 2, 90, -90)
        path.lineTo(r.right(), r.bottom() - bottom_radius)
        path.arcTo(r.right() - bottom_radius * 2,
                   r.bottom() - bottom_radius * 2,
                   bottom_radius * 2, bottom_radius * 2, 0, -90)
        path.lineTo(r.left() + bottom_radius, r.bottom())
        path.arcTo(r.left(), r.bottom() - bottom_radius * 2,
                   bottom_radius * 2, bottom_radius * 2, 270, -90)
        path.closeSubpath()
        return path

    def _paint_tab(self, painter: QPainter, index: int):
        rect = self.tabRect(index)
        if not rect.isValid():
            return
        current = index == self.currentIndex()
        hovered = index == self._hover
        pinned = self.is_pinned(index)
        muted = self.is_muted(index)
        loading = self._loading.get(index, False)
        c = chrome(self._dark, self._accent)

        # 卡片几何：左右留 3px 间隙；底部贴住条底，与云母工具栏无缝融合
        gap = 3
        r = QRectF(rect.adjusted(gap, 3, -gap, 0))
        path = self._tab_path(r, RADIUS_TAB, 5)

        # ---- 底面填充 ----
        painter.setPen(Qt.NoPen)
        if current:
            # 活动标签 == 工具栏云母首段色：视觉融为一体
            painter.setBrush(QColor(c["tab_active"]))
            painter.drawPath(path)
            # 顶部镜面高光（玻璃厚度）
            hi = QLinearGradient(0, r.top(), 0, r.top() + r.height() * 0.55)
            hi.setColorAt(0.0, QColor(c["tab_rim"]))
            hi.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(hi)
            painter.drawPath(path)
            # 底部内阴影（玻璃下沉感）
            sh = QLinearGradient(0, r.bottom() - 14, 0, r.bottom())
            sh.setColorAt(0.0, QColor(0, 0, 0, 0))
            sh.setColorAt(1.0, QColor(0, 0, 0, 34 if c["dark"] else 14))
            painter.setBrush(sh)
            painter.drawPath(path)
            # 发丝描边（两侧 + 顶部，营造浮起层次）
            edge = QColor(c["tab_edge"])
            painter.setPen(QPen(edge, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            fg = QColor(c["tab_active_fg"])
        else:
            # v2.1.6：非活动标签也画可见底色（悬停更亮），标签清晰可辨、
            # 深底白字 / 浅底黑字，便于识别与切换。
            painter.setBrush(QColor(c["tab_hover"] if hovered
                                    else c["tab_inactive_bg"]))
            painter.drawPath(path)
            fg = QColor(c["tab_inactive_fg"])
            # 发丝描边让非活动卡片边界更清楚
            painter.setPen(QPen(QColor(c["tab_edge"]), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            # 非活动标签之间的发丝分隔线（两侧邻居都不是活动标签时才画）
            painter.setPen(QPen(QColor(c["separator"]), 1))
            if index > 0 and self.currentIndex() != index - 1 \
                    and self._hover != index - 1:
                prev = self.tabRect(index - 1)
                if prev.isValid():
                    x = rect.left() + gap / 2
                    painter.drawLine(QPointF(x, rect.top() + 9),
                                     QPointF(x, rect.bottom() - 7))

        # ---- 分组色带（顶部 3px，裁剪进卡片） ----
        gcolor = self._groups.get(index)
        if gcolor is not None:
            painter.save()
            painter.setClipPath(path)
            painter.setPen(Qt.NoPen)
            painter.setBrush(gcolor)
            painter.drawRoundedRect(QRectF(r.left() + 8, r.top() + 2.5,
                                           max(0, r.width() - 16), 3),
                                    1.5, 1.5)
            painter.restore()

        # ---- 图标区（favicon / 加载环 / 首字母玻璃圆） ----
        icon_x = rect.left() + gap + 9
        if loading:
            self._paint_spinner(painter, icon_x, rect.center().y() - 7, 14)
        else:
            icon = self.tabIcon(index)
            if not icon.isNull():
                px = icon.pixmap(16, 16)
                painter.drawPixmap(int(icon_x), rect.center().y() - 8, 16, 16, px)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(c["placeholder_bg"]))
                painter.drawEllipse(int(icon_x), rect.center().y() - 8, 16, 16)
                painter.setPen(fg)
                f = QFont()
                f.setPixelSize(9)
                f.setBold(True)
                f.setLetterSpacing(QFont.AbsoluteSpacing, -0.2)
                painter.setFont(f)
                title = self.tabText(index) or "新标签页"
                painter.drawText(QRect(int(icon_x), rect.center().y() - 8, 16, 16),
                                 Qt.AlignCenter, title[0].upper())

        # ---- 标题（负字距） ----
        text_rect = QRect(rect)
        left_pad = 34 if not pinned else 8
        text_rect.setLeft(rect.left() + gap + left_pad - 12)
        text_rect.setRight(rect.right() - gap - 28)
        title = self.tabText(index) or "新标签页"
        painter.setPen(fg)
        f = QFont()
        f.setPixelSize(13)
        f.setBold(current)
        f.setLetterSpacing(QFont.AbsoluteSpacing, -0.3)
        painter.setFont(f)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                         QFontMetrics(f).elidedText(title, Qt.ElideRight,
                                                    text_rect.width()))

        # ---- 静音指示（非加载时） ----
        if muted and not loading:
            self._paint_muted(painter, rect.right() - gap - 24,
                              rect.center().y() - 6)

        # ---- 关闭按钮（悬停/活动标签显示，圆形玻璃 hover） ----
        if not pinned and (hovered or current):
            close_rect = self._close_rect(index)
            self._paint_close(painter, close_rect,
                              self._close_hover == index, c)

    # ------------------------------------------------------------------ #
    # 垂直标签（v2.1.5，Edge 风）：行式渲染，左侧竖排
    # ------------------------------------------------------------------ #
    def _paint_tab_v(self, painter: QPainter, index: int):
        rect = self.tabRect(index)
        if not rect.isValid():
            return
        current = index == self.currentIndex()
        hovered = index == self._hover
        pinned = self.is_pinned(index)
        muted = self.is_muted(index)
        loading = self._loading.get(index, False)
        c = chrome(self._dark, self._accent)

        # 行几何：左右各留 6px，行间 2px（不贴死，卡片感更接近 Edge）
        r = QRectF(rect.adjusted(6, 1, -6, -1))
        radius = 9.0

        painter.setPen(Qt.NoPen)
        if current:
            # 活动行：云母卡片填充 + 顶部镜面高光 + 发丝边 + 强调色指示条
            painter.setBrush(QColor(c["tab_active"]))
            painter.drawRoundedRect(r, radius, radius)
            hi = QLinearGradient(0, r.top(), 0, r.top() + r.height() * 0.6)
            hi.setColorAt(0.0, QColor(c["tab_rim"]))
            hi.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(hi)
            painter.drawRoundedRect(r, radius, radius)
            painter.setPen(QPen(QColor(c["tab_edge"]), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(
                QRectF(r.adjusted(0.5, 0.5, -0.5, -0.5)), radius, radius)
            # 左侧强调色指示条（Edge 选中态的视觉锚点）
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(self._accent))
            painter.drawRoundedRect(QRectF(r.left() + 2, r.center().y() - 7,
                                           3, 14), 1.5, 1.5)
            fg = QColor(c["tab_active_fg"])
        else:
            # v2.1.6：非活动行也画可见底色（悬停更亮），深底白字 / 浅底黑字
            painter.setBrush(QColor(c["tab_hover"] if hovered
                                    else c["tab_inactive_bg"]))
            painter.drawRoundedRect(r, radius, radius)
            fg = QColor(c["tab_inactive_fg"])
            # 行间发丝分隔（邻居非活动/非悬停时才画）
            painter.setPen(QPen(QColor(c["separator"]), 1))
            if index > 0 and self.currentIndex() != index - 1 \
                    and self._hover != index - 1:
                prev = self.tabRect(index - 1)
                if prev.isValid():
                    y = rect.top()
                    painter.drawLine(QPointF(r.left() + 12, y),
                                     QPointF(r.right() - 12, y))

        # 分组色带（竖向：左侧短竖条，裁剪进卡片）
        gcolor = self._groups.get(index)
        if gcolor is not None:
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(r, radius, radius)
            painter.setClipPath(clip)
            painter.setPen(Qt.NoPen)
            painter.setBrush(gcolor)
            painter.drawRoundedRect(QRectF(r.left(), r.top() + 6,
                                           3, max(0, r.height() - 12)),
                                    1.5, 1.5)
            painter.restore()

        # 图标（favicon / 加载环 / 首字母圆）
        icon_x = r.left() + 8
        if loading:
            self._paint_spinner(painter, icon_x, rect.center().y() - 7, 14)
        else:
            icon = self.tabIcon(index)
            if not icon.isNull():
                px = icon.pixmap(16, 16)
                painter.drawPixmap(int(icon_x), rect.center().y() - 8, 16, 16, px)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(c["placeholder_bg"]))
                painter.drawEllipse(int(icon_x), rect.center().y() - 8, 16, 16)
                painter.setPen(fg)
                f = QFont()
                f.setPixelSize(9)
                f.setBold(True)
                painter.setFont(f)
                title = self.tabText(index) or "新标签页"
                painter.drawText(QRect(int(icon_x), rect.center().y() - 8, 16, 16),
                                 Qt.AlignCenter, title[0].upper())

        # 标题
        text_rect = QRect(rect)
        text_rect.setLeft(int(r.left() + 30))
        text_rect.setRight(int(r.right() - 28))
        title = self.tabText(index) or "新标签页"
        painter.setPen(fg)
        f = QFont()
        f.setPixelSize(13)
        f.setBold(current)
        f.setLetterSpacing(QFont.AbsoluteSpacing, -0.3)
        painter.setFont(f)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                         QFontMetrics(f).elidedText(title, Qt.ElideRight,
                                                    text_rect.width()))

        # 静音指示
        if muted and not loading:
            self._paint_muted(painter, r.right() - 24, rect.center().y() - 6)

        # 关闭按钮
        if not pinned and (hovered or current):
            close_rect = self._close_rect(index)
            self._paint_close(painter, close_rect,
                              self._close_hover == index, c)

    def _paint_spinner(self, painter, x, y, size):
        cx, cy = x + size / 2, y + size / 2
        painter.setPen(QPen(QColor(self._accent), 2))
        painter.setBrush(Qt.NoBrush)
        r = size / 2 - 1
        painter.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2),
                        int(self._spin * 57.3) * 16, 220 * 16)

    def _paint_muted(self, painter, x, y):
        """矢量绘制静音图标（喇叭 + 斜线），避免依赖 emoji 字体。"""
        c = chrome(self._dark, self._accent)
        h = 12
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(c["muted_icon"]))
        # 锥形喇叭
        painter.drawPolygon(QPolygonF([
            QPointF(x + 1, y + 3), QPointF(x + 4, y + 3),
            QPointF(x + 8, y - 1), QPointF(x + 8, y + h + 1),
            QPointF(x + 4, y + h - 3), QPointF(x + 1, y + h - 3)]))
        # 斜杠表示静音（描边用当前标签前景色族）
        pen = QPen(QColor(c["muted_icon"]), 1.8)
        painter.setPen(pen)
        painter.drawLine(x + 6, y + 1, x + 12, y + h)

    def _paint_close(self, painter, rect, hovered, c):
        if hovered:
            painter.setBrush(QColor(c["close_hover"]))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(rect)
        inactive = QColor(c["tab_inactive_fg"])
        pen = QPen(inactive, 1.4)
        painter.setPen(pen)
        pad = 4
        cx, cy = rect.center().x(), rect.center().y()
        painter.drawLine(cx - pad, cy - pad, cx + pad, cy + pad)
        painter.drawLine(cx + pad, cy - pad, cx - pad, cy + pad)


from PySide6.QtWidgets import (  # 缩略图浮层依赖（B2，模块级）
    QFrame,
    QLabel,
    QVBoxLayout,
)


class TabPreview(QFrame):
    """标签悬停缩略图浮层（ToolTip 风格：不抢焦点、不激活）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.lbl = QLabel(self)
        lay.addWidget(self.lbl)
        self.hide()

    def show_for(self, pm, global_pos):
        if pm is None or pm.isNull():
            self.hide()
            return
        self.lbl.setPixmap(pm)
        self.adjustSize()
        self.move(global_pos)
        self.show()
        self.raise_()


class BrowserTabWidget(QTabWidget):
    """使用 BrowserTabBar 的标签容器。"""

    close_requested = Signal(int)
    new_tab_requested = Signal()
    pin_requested = Signal(int, bool)
    mute_requested = Signal(int, bool)
    refresh_requested = Signal(int)
    close_others_requested = Signal(int)
    group_edit_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(False)   # 由自定义绘制处理
        self.setMovable(True)
        self.setDocumentMode(True)
        self._bar = BrowserTabBar(self)
        self.setTabBar(self._bar)

        self._bar.close_requested.connect(self.close_requested.emit)
        self._bar.new_tab_requested.connect(self.new_tab_requested.emit)
        self._bar.pin_requested.connect(self.pin_requested.emit)
        self._bar.mute_requested.connect(self.mute_requested.emit)
        self._bar.refresh_requested.connect(self.refresh_requested.emit)
        self._bar.close_others_requested.connect(self.close_others_requested.emit)
        self._bar.group_edit_requested.connect(self.group_edit_requested.emit)
        # 悬停缩略图（B2）：缓存各标签最近可见时的画面
        self._thumbs = {}
        self._preview = TabPreview(self)
        self._bar.hover_changed.connect(self._on_hover)

    def bar(self) -> BrowserTabBar:
        return self._bar

    def set_tab_placement(self, position: str):
        """v2.1.5：标签位置 top=上方 / left=左侧垂直（Edge 风）。"""
        if position == "left":
            self.setTabPosition(QTabWidget.West)
            self._bar.set_vertical(True)
        else:
            self.setTabPosition(QTabWidget.North)
            self._bar.set_vertical(False)

    # ------------------------------------------------------------------ #
    # 悬停缩略图（B2）
    # ------------------------------------------------------------------ #
    def capture_current_thumb(self):
        """抓取当前可见标签的画面，作为其悬停缩略图缓存。

        仅在标签可见时调用（loadFinished / 切换标签），避免不可见
        QWebEngineView 抓图返回空白。
        """
        idx = self.currentIndex()
        w = self.currentWidget()
        if w is None or not getattr(w, "view", None):
            return
        try:
            pm = w.view.grab()
            if pm.isNull():
                return
            pm = pm.scaledToWidth(280, Qt.SmoothTransformation)
            self._thumbs[idx] = pm
        except Exception:
            pass

    def _on_hover(self, index):
        if index < 0:
            self._preview.hide()
            return
        w = self.widget(index)
        if w is None:
            self._preview.hide()
            return
        pm = self._thumbs.get(index)
        if pm is None:
            self._preview.hide()
            return
        r = self._bar.tabRect(index)
        gp = self._bar.mapToGlobal(r.bottomLeft()) + QPoint(0, 6)
        self._preview.show_for(pm, gp)
