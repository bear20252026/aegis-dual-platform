"""task_manager.py —— 任务管理器。

列出当前窗口的标签页（标题/网址/粗略内存），支持跳转与结束标签页。
内存取页面 performance.memory 的近似值（异步刷新）。
"""

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class TaskManagerDialog(QDialog):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._win = window
        self.setWindowTitle("任务管理器")
        self.resize(600, 400)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["标题", "网址", "内存"])
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 300)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self.table, 1)

        btns = QHBoxLayout()
        self.lbl_stats = QLabel("", self)
        btns.addWidget(self.lbl_stats)
        btns.addStretch(1)
        btn_refresh = QPushButton("刷新", self)
        btn_refresh.clicked.connect(self.refresh)
        btn_close = QPushButton("结束标签页", self)
        btn_close.clicked.connect(self._kill)
        btn_ok = QPushButton("关闭", self)
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_refresh)
        btns.addWidget(btn_close)
        btns.addWidget(btn_ok)
        lay.addLayout(btns)

        self.refresh()

    def refresh(self):
        self.table.setRowCount(self._win.tabs.count())
        for i in range(self._win.tabs.count()):
            tab = self._win.tabs.widget(i)
            if not tab:
                continue
            self.table.setItem(i, 0, QTableWidgetItem(tab.title() or "新标签页"))
            self.table.setItem(i, 1, QTableWidgetItem(tab.url()))
            self.table.setItem(i, 2, QTableWidgetItem("…"))
            self._fetch_memory(tab, i)
        self.lbl_stats.setText(f"{self._win.tabs.count()} 个标签页")

    def _fetch_memory(self, tab, row):
        def on_js(m):
            try:
                mb = int(m) / 1048576
                self.table.setItem(row, 2, QTableWidgetItem(f"{mb:.1f} MB"))
            except Exception:
                pass
        try:
            tab.run_js("(performance.memory && performance.memory.usedJSHeapSize)||0", on_js)
        except Exception:
            pass

    def _kill(self):
        row = self.table.currentRow()
        if row < 0:
            return
        if QMessageBox.question(self, "确认", "结束该标签页？") == QMessageBox.Yes:
            self._win._close_tab(row)
            self.refresh()
