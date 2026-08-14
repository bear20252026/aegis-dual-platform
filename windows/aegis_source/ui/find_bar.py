# -*- coding: utf-8 -*-
"""find_bar.py —— 页面内查找栏（Ctrl+F）。

顶部浮动查找输入框，支持上一个/下一个/区分大小写，实时高亮。
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QLineEdit, QToolButton, QLabel, QHBoxLayout, QCheckBox,
)

from .icons import icon


class FindBar(QWidget):
    """查找栏。"""

    # (text, flags)
    find_requested = Signal(str, object)
    closed = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("findBar")
        self.setVisible(False)
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self.label = QLabel("查找:", self)
        self.input = QLineEdit(self)
        self.input.setPlaceholderText("在页面中查找")
        self.input.setFixedWidth(220)
        self.count = QLabel("", self)

        self.btn_prev = QToolButton(self)
        self.btn_prev.setText("↑")
        self.btn_prev.setToolTip("上一个")
        self.btn_next = QToolButton(self)
        self.btn_next.setText("↓")
        self.btn_next.setToolTip("下一个")
        self.chk_case = QCheckBox("区分大小写", self)
        self.btn_close = QToolButton(self)
        self.btn_close.setIcon(icon("close"))
        self.btn_close.setToolTip("关闭查找 (Esc)")

        layout.addWidget(self.label)
        layout.addWidget(self.input)
        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.chk_case)
        layout.addWidget(self.count)
        layout.addStretch(1)
        layout.addWidget(self.btn_close)

        self.input.textChanged.connect(self._on_change)
        self.input.returnPressed.connect(lambda: self._search(False))
        self.btn_prev.clicked.connect(lambda: self._search(True))
        self.btn_next.clicked.connect(lambda: self._search(False))
        self.btn_close.clicked.connect(self.hide_bar)

    def _on_change(self, text):
        self._search(False)

    def _search(self, backward):
        text = self.input.text()
        case_sensitive = self.chk_case.isChecked()
        from PySide6.QtWebEngineCore import QWebEnginePage
        flags = QWebEnginePage.FindFlags()
        if case_sensitive:
            flags |= QWebEnginePage.FindCaseSensitively
        if backward:
            flags |= QWebEnginePage.FindBackward
        # 主窗口根据 flags 执行 findText，这里仅触发
        self.find_requested.emit(text, flags)

    def show_bar(self):
        self.setVisible(True)
        self.input.setFocus()
        self.input.selectAll()

    def hide_bar(self):
        # 实际隐藏由主窗口配合滑出动画执行，这里发信号并清输入
        self.closed.emit()
        self.input.clear()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide_bar()
        else:
            super().keyPressEvent(event)
