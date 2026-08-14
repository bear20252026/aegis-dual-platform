"""bookmark_bar.py —— Chrome 风格书签栏。

导航栏下方的一行书签按钮：
- 单击在当前标签打开；中键单击在新标签打开
- 右键菜单：新标签打开 / 复制链接 / 删除
- 书签为空时自动隐藏（由 MainWindow 控制可见性）
QSS 样式见 theme.py 中 `#bookmarkBar` 段落。
"""

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QWidget,
)


class BookmarkBar(QWidget):
    """书签条控件。"""

    navigate = Signal(str)          # 当前标签打开
    open_new_tab = Signal(str)      # 新标签打开

    def __init__(self, bookmarks, parent=None):
        super().__init__(parent)
        self.setObjectName("bookmarkBar")
        self._bookmarks = bookmarks

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 2, 10, 2)
        lay.setSpacing(2)
        self._layout = lay
        self._hint = QLabel("暂无书签 —— 点击地址栏右侧的收藏按钮添加页面", self)
        self._hint.setObjectName("bookmarkHint")
        lay.addWidget(self._hint)
        lay.addStretch(1)
        self.setFixedHeight(32)

    # ------------------------------------------------------------------ #
    def refresh(self):
        """从存储重建全部书签按钮。"""
        # 清空旧按钮
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not self._hint:
                w.deleteLater()
        # 保证 hint 始终在最前
        if self._layout.indexOf(self._hint) != 0:
            self._layout.removeWidget(self._hint)
            self._layout.insertWidget(0, self._hint)

        rows = self._bookmarks.all()
        self._hint.setVisible(not rows)
        for r in rows[:30]:  # 一行放不下太多，限制数量（完整列表见菜单/对话框）
            btn = self._make_button(r["title"] or r["url"], r["url"])
            self._layout.insertWidget(self._layout.count() - 1, btn)

    def _make_button(self, title: str, url: str) -> QToolButton:
        b = QToolButton(self)
        b.setText(self._elide(title))
        b.setToolTip(f"{title}\n{url}")
        b.setCursor(Qt.PointingHandCursor)
        b.setMouseTracking(True)
        b.clicked.connect(lambda _=False, u=url: self.navigate.emit(u))
        # 中键新标签 / 右键菜单
        b.installEventFilter(_ButtonFilter(self, url))
        return b

    @staticmethod
    def _elide(text: str, n: int = 14) -> str:
        return text if len(text) <= n else text[: n - 1] + "…"

    # ------------------------------------------------------------------ #
    def _open_menu(self, url: str, global_pos):
        menu = QMenu(self)
        menu.addAction("在新标签页打开",
                       lambda: self.open_new_tab.emit(url))
        menu.addAction("复制链接地址",
                       lambda: QApplication.clipboard().setText(url))
        menu.addSeparator()
        menu.addAction("删除书签", self._remove(url))
        menu.exec(global_pos)

    def _remove(self, url: str):
        def _do():
            self._bookmarks.remove(url)
            self.refresh()
        return _do


class _ButtonFilter(QObject):
    """书签按钮的事件过滤器：中键新标签 / 右键菜单。"""

    def __init__(self, bar: BookmarkBar, url: str):
        super().__init__()
        self._bar = bar
        self._url = url

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonRelease and \
                event.button() == Qt.MiddleButton:
            self._bar.open_new_tab.emit(self._url)
            return True
        if event.type() == QEvent.ContextMenu:
            self._bar._open_menu(self._url, event.globalPos())
            return True
        return False
