"""download_bar.py —— 下载管理条。

固定在窗口底部的下载任务浮层：显示进行中的下载、进度、速度，
支持暂停/继续/取消；可展开全部历史下载。
"""

import os

from app.i18n import tr
from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .icons import icon

STATE_TEXT = {
    "downloading": "下载中",
    "paused": "已暂停",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
}


def _fmt_size(n: int) -> str:
    """字节数 → 人类可读（用于历史记录行展示）。"""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f} GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.0f} KB"
    return f"{n} B"


class HistoryRow(QFrame):
    """历史下载记录行（只读展示，⋯ 打开所在文件夹）。"""

    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.record = record
        self.setObjectName("downloadRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)

        info = QVBoxLayout()
        name = QLabel(record.get("filename") or record.get("url") or "下载", self)
        name.setWordWrap(True)
        state = record.get("state", "")
        st = STATE_TEXT.get(state, state or "未知")
        size = _fmt_size(record.get("total"))
        status = QLabel(f"{st} · {size}", self)
        info.addWidget(name)
        info.addWidget(status)

        btn = QToolButton(self)
        btn.setText("⋯")
        btn.setToolTip("打开所在文件夹")
        btn.clicked.connect(self._open)

        lay.addLayout(info, 1)
        lay.addWidget(btn)

    def _open(self):
        path = self.record.get("path") or ""
        if path and os.path.exists(os.path.dirname(path)):
            self._open_folder(path)

    def _open_folder(self, path):
        import subprocess
        import sys
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])


class DownloadRow(QFrame):
    """单个下载任务的展示行。"""

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("downloadRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)

        info = QVBoxLayout()
        name = QLabel(os.path.basename(item.path) or item.filename, self)
        name.setWordWrap(True)
        self.status = QLabel(STATE_TEXT.get(item.state, item.state), self)
        info.addWidget(name)
        info.addWidget(self.status)

        self.progress = QProgressBar(self)
        self.progress.setMaximumWidth(200)

        self.btn = QToolButton(self)
        self.btn.setText("⋯")
        self.btn.clicked.connect(self._on_btn)

        lay.addLayout(info, 1)
        lay.addWidget(self.progress)
        lay.addWidget(self.btn)

    def _on_btn(self):
        if self.item.state == "downloading":
            self.item.pause()
        elif self.item.state == "paused":
            self.item.resume()
        else:
            # 已完成/失败：打开所在文件夹
            path = self.item.path
            if path and os.path.exists(os.path.dirname(path)):
                self._open_folder(path)

    def _open_folder(self, path):
        import subprocess
        import sys
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def refresh(self):
        self.status.setText(STATE_TEXT.get(self.item.state, self.item.state))
        self.progress.setValue(int(self.item.percent()))
        if self.item.state == "completed":
            self.progress.setValue(100)


class DownloadBar(QWidget):
    """下载管理浮层。"""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setObjectName("downloadBar")
        self.setVisible(False)
        self._rows = {}  # item_id -> DownloadRow

        self._build()
        self.manager.item_added.connect(self._on_added)
        self.manager.item_updated.connect(self._on_updated)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(4)

        head = QHBoxLayout()
        title = QLabel(tr("下载"), self)
        self.history_btn = QToolButton(self)
        self.history_btn.setText(tr("历史"))
        self.history_btn.setCheckable(True)
        self.history_btn.setToolTip("显示/隐藏历史下载记录")
        self.history_btn.clicked.connect(self._toggle_history)
        self.close_btn = QToolButton(self)
        self.close_btn.setIcon(icon("close"))
        self.close_btn.setToolTip("隐藏")
        self.close_btn.clicked.connect(self._hide_slide)
        head.addWidget(title)
        head.addWidget(self.history_btn)
        head.addStretch(1)
        head.addWidget(self.close_btn)
        outer.addLayout(head)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(4)
        # 历史记录区（默认隐藏）：位于进行中任务列表下方
        self.history_frame = QFrame(self.content)
        self.history_frame.setObjectName("historySection")
        self.history_lay = QVBoxLayout(self.history_frame)
        self.history_lay.setContentsMargins(0, 6, 0, 0)
        self.history_lay.setSpacing(4)
        self.history_frame.setVisible(False)
        self.content_layout.addWidget(self.history_frame)
        self.content_layout.addStretch(1)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll, 1)

        self.setFixedHeight(300)
        self.setFixedWidth(420)

    def _on_added(self, item):
        row = DownloadRow(item, self)
        # 插到历史记录区之前（保持：进行中任务在上、历史在下）
        idx = self.content_layout.indexOf(self.history_frame)
        if idx < 0:
            idx = self.content_layout.count() - 1
        self.content_layout.insertWidget(idx, row)
        self._rows[item.id] = row
        self.setVisible(True)
        row.refresh()

    def _on_updated(self, item):
        row = self._rows.get(item.id)
        if row:
            row.refresh()

    def toggle(self):
        self.setVisible(not self.isVisible())

    def set_visible(self):
        self.setVisible(True)

    # ------------------------------------------------------------------ #
    # 下载历史（downloads.json 持久化记录，跨会话保留）
    # ------------------------------------------------------------------ #
    def _toggle_history(self):
        self._refresh_history()
        self.history_frame.setVisible(not self.history_frame.isVisible())

    def _refresh_history(self):
        """用 manager.history() 重建历史记录区（最新 10 条在前）。"""
        while self.history_lay.count():
            item = self.history_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        recs = getattr(self.manager, "history", list)()[:10]
        if not recs:
            lbl = QLabel(tr("暂无历史记录"), self.history_frame)
            lbl.setStyleSheet(
                "color:rgba(128,128,128,0.7);padding:4px 2px;")
            self.history_lay.addWidget(lbl)
            return
        tl = QLabel(tr("历史记录"), self.history_frame)
        tl.setStyleSheet(
            "font-size:12px;color:rgba(128,128,128,0.85);padding:2px;")
        self.history_lay.addWidget(tl)
        for rec in recs:
            self.history_lay.addWidget(HistoryRow(rec, self.history_frame))

    # ------------------------------------------------------------------ #
    # 丝滑动画（Apple 风：OutCubic 缓动的轻微位移）
    # ------------------------------------------------------------------ #
    def showEvent(self, event):
        super().showEvent(event)
        # 每次显示时同步最新历史（重启后也能看到已完成的下载）
        self._refresh_history()
        self._slide(18, 0)

    def _slide(self, dy_from, dy_to, on_finish=None):
        p = self.pos()
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(240)
        anim.setStartValue(QPoint(p.x(), p.y() + dy_from))
        anim.setEndValue(QPoint(p.x(), p.y() + dy_to))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        if on_finish is not None:
            anim.finished.connect(on_finish)
        anim.start(QAbstractAnimation.DeleteWhenStopped)

    def _hide_slide(self):
        if not self.isVisible():
            return
        self._slide(0, 18, on_finish=lambda: self.setVisible(False))
