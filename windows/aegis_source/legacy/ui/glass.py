"""glass.py —— 液态玻璃控件辅助（v2.1.3 重设计：Fluent mesh × Apple glass）。

提供：
- GlassPanel：半透明圆角玻璃面板（顶部镜面高光 + 发丝描边）
- AuroraBackground：「极光云母」背景 —— 深色基底上漂浮大尺度柔光斑
  （蓝/青/白，无紫），模拟 Edge 新标签页 mesh gradient 与 Apple
  玻璃折射的混合氛围；支持深色/浅色两种基调。

P0：不使用 emoji；光斑颜色取自 Apple 蓝调体系（accent / #5ac8fa / 白），
禁止紫色渐变。
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QFrame, QWidget


class GlassPanel(QFrame):
    """半透明圆角玻璃面板：底色 + 顶部高光带 + 发丝描边。"""

    def __init__(self, parent=None, radius=16, tint=None, dark=True):
        super().__init__(parent)
        self.radius = radius
        self.tint = tint or (255, 255, 255, 24) if dark \
            else tint or (255, 255, 255, 190)
        self.dark = dark
        self.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(*self.tint)))
        painter.drawRoundedRect(rect, self.radius, self.radius)
        # 顶部镜面高光（玻璃厚度）
        hi = QLinearGradient(0, rect.top(), 0, rect.top() + rect.height() * 0.4)
        if self.dark:
            hi.setColorAt(0.0, QColor(255, 255, 255, 40))
        else:
            hi.setColorAt(0.0, QColor(255, 255, 255, 200))
        hi.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(hi)
        painter.drawRoundedRect(rect, self.radius, self.radius)
        # 发丝描边
        rim = QColor(255, 255, 255, 44) if self.dark else QColor(0, 0, 0, 22)
        painter.setPen(rim)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5),
                                self.radius, self.radius)
        painter.end()


class AuroraBackground(QWidget):
    """极光云母背景：渐变基底 + 多团径向柔光斑，营造纵深与玻璃反射。

    dark=True（默认）：近黑基底，蓝光斑漂浮；
    dark=False：浅灰基底，光斑降饱和，用于浅色新标签页。
    """

    def __init__(self, parent=None, accent="#0071e3", dark=True):
        super().__init__(parent)
        self.accent = accent or "#0071e3"
        self.dark = dark

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        side = min(w, h)

        # 基底：竖向微渐变（不是纯平面，避免"贴图感"）
        bg = QLinearGradient(0, 0, 0, h)
        if self.dark:
            bg.setColorAt(0.0, QColor("#050607"))
            bg.setColorAt(0.55, QColor("#0a0d12"))
            bg.setColorAt(1.0, QColor("#10141b"))
        else:
            bg.setColorAt(0.0, QColor("#f7f8fa"))
            bg.setColorAt(1.0, QColor("#eef1f5"))
        painter.fillRect(self.rect(), bg)

        # 光斑配置：(颜色, 不透明度, cx, cy, 半径) —— 蓝 / 青 / 白三色体系
        if self.dark:
            blobs = [
                (self.accent, 0.34, w * 0.22, h * 0.26, side * 0.66),
                ("#5ac8fa", 0.22, w * 0.82, h * 0.16, side * 0.56),
                ("#2997ff", 0.16, w * 0.62, h * 0.86, side * 0.54),
                ("#ffffff", 0.06, w * 0.40, h * 0.66, side * 0.38),
            ]
        else:
            blobs = [
                (self.accent, 0.09, w * 0.20, h * 0.24, side * 0.62),
                ("#5ac8fa", 0.10, w * 0.84, h * 0.14, side * 0.52),
                ("#ffffff", 0.55, w * 0.55, h * 0.88, side * 0.48),
            ]
        for color, alpha, cx, cy, radius in blobs:
            col = QColor(color)
            col.setAlphaF(alpha)
            grad = QRadialGradient(cx, cy, radius)
            grad.setColorAt(0.0, col)
            mid = QColor(col)
            mid.setAlphaF(alpha * 0.45)
            grad.setColorAt(0.5, mid)
            grad.setColorAt(1.0, Qt.transparent)
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(int(cx - radius), int(cy - radius),
                                int(radius * 2), int(radius * 2))

        # 顶部一抹天光（玻璃反射的"天花板光"）
        sky = QLinearGradient(0, 0, 0, h * 0.22)
        sky_white = QColor(255, 255, 255, 16 if self.dark else 90)
        sky.setColorAt(0.0, sky_white)
        sky.setColorAt(1.0, Qt.transparent)
        painter.setBrush(sky)
        painter.setPen(Qt.NoPen)
        painter.drawRect(0, 0, w, int(h * 0.22))
        painter.end()
