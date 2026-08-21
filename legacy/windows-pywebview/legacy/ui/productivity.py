"""productivity.py —— v1.5 生产力功能对话框。

包含：标签搜索（Ctrl+Shift+A）、阅读清单、用户脚本管理器。
样式走全局 Apple QSS，无需单独样式表。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .icons import icon


class TabSearchDialog(QDialog):
    """跨标签搜索：过滤标题/URL，回车激活。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._win = window
        self.setWindowTitle("标签搜索")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("输入标题或网址过滤标签…")
        self.edit.textChanged.connect(self._refresh)
        lay.addWidget(self.edit)
        self.listw = QListWidget(self)
        self.listw.itemDoubleClicked.connect(self._activate)
        lay.addWidget(self.listw, 1)
        self._refresh()
        self.edit.setFocus()

    def _refresh(self):
        kw = self.edit.text().strip().lower()
        self.listw.clear()
        for i in range(self._win.tabs.count()):
            tab = self._win.tabs.widget(i)
            if not tab:
                continue
            title, url = tab.title() or "(无标题)", tab.url()
            if kw and kw not in title.lower() and kw not in url.lower():
                continue
            item = QListWidgetItem(f"{title}\n{url}")
            item.setData(Qt.UserRole, i)
            self.listw.addItem(item)

    def _activate(self, item=None):
        item = item or self.listw.currentItem()
        if item:
            self._win.tabs.setCurrentIndex(item.data(Qt.UserRole))
            self.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._activate()
        else:
            super().keyPressEvent(event)


class ReadingListDialog(QDialog):
    """阅读清单管理。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._win = window
        self._rl = window.ctx.reading
        self.setWindowTitle("阅读清单")
        self.resize(620, 440)
        lay = QVBoxLayout(self)
        self.listw = QListWidget(self)
        lay.addWidget(self.listw, 1)
        btns = QHBoxLayout()
        b_open = QPushButton("打开选中", self)
        b_open.clicked.connect(self._open)
        b_read = QPushButton("标记已读/未读", self)
        b_read.clicked.connect(self._toggle_read)
        b_del = QPushButton("删除", self)
        b_del.clicked.connect(self._remove)
        b_clean = QPushButton("清除已读", self)
        b_clean.clicked.connect(lambda: (self._rl.clear_read(), self._refresh()))
        b_close = QPushButton("关闭", self)
        b_close.clicked.connect(self.accept)
        for b in (b_open, b_read, b_del, b_clean):
            btns.addWidget(b)
        btns.addStretch(1)
        btns.addWidget(b_close)
        lay.addLayout(btns)
        self._refresh()

    def _refresh(self):
        self.listw.clear()
        for r in self._rl.all():
            item = QListWidgetItem(f"{r['title']}\n{r['url']}")
            item.setData(Qt.UserRole, r["url"])
            if r["read"]:
                item.setIcon(icon("check"))
                item.setForeground(Qt.gray)
            self.listw.addItem(item)

    def _current_url(self):
        item = self.listw.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _open(self):
        url = self._current_url()
        if url:
            self._rl.mark_read(url)
            self._win.open_new_tab(url)
            self._refresh()

    def _toggle_read(self):
        url = self._current_url()
        if url:
            rows = self._rl.all()
            cur = next((r for r in rows if r["url"] == url), None)
            if cur is not None:
                self._rl.mark_read(url, not cur["read"])
                self._refresh()

    def _remove(self):
        url = self._current_url()
        if url:
            self._rl.remove(url)
            self._refresh()


class UserScriptsDialog(QDialog):
    """用户脚本管理器（Tampermonkey 式轻量替代）。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._win = window
        self._store = window.ctx.user_scripts
        self.setWindowTitle("用户脚本")
        self.resize(640, 520)
        lay = QVBoxLayout(self)

        self.listw = QListWidget(self)
        self.listw.itemSelectionChanged.connect(self._load_selected)
        lay.addWidget(self.listw, 1)

        self.edit_name = QLineEdit(self)
        self.edit_name.setPlaceholderText("脚本名称")
        self.edit_match = QLineEdit(self)
        self.edit_match.setPlaceholderText("生效站点（* 或 example.com 或 *.example.com）")
        self.edit_code = QPlainTextEdit(self)
        self.edit_code.setPlaceholderText("页面加载完成后执行的 JavaScript")
        self.edit_code.setFixedHeight(150)
        self.chk_enabled = QCheckBox("启用", self)
        form = QVBoxLayout()
        form.addWidget(self.edit_name)
        form.addWidget(self.edit_match)
        form.addWidget(self.chk_enabled)
        form.addWidget(self.edit_code)
        lay.addLayout(form)

        btns = QHBoxLayout()
        b_new = QPushButton("新建", self)
        b_new.clicked.connect(self._new)
        b_save = QPushButton("保存", self)
        b_save.clicked.connect(self._save)
        b_del = QPushButton("删除", self)
        b_del.clicked.connect(self._delete)
        b_close = QPushButton("关闭", self)
        b_close.clicked.connect(self.accept)
        for b in (b_new, b_save, b_del):
            btns.addWidget(b)
        btns.addStretch(1)
        btns.addWidget(b_close)
        lay.addLayout(btns)

        tip = QLabel("说明：脚本在页面就绪后注入主世界；站点匹配外的页面不会执行。", self)
        tip.setStyleSheet("color: gray; font-size: 12px;")
        lay.addWidget(tip)
        self._refresh()

    def _refresh(self, select_name=None):
        self.listw.clear()
        for s in self._store.all():
            state = "启用" if s.get("enabled", True) else "停用"
            item = QListWidgetItem(f"[{state}] {s['name']}（{s['match']}）")
            item.setData(Qt.UserRole, s["name"])
            self.listw.addItem(item)
            if select_name == s["name"]:
                self.listw.setCurrentItem(item)

    def _load_selected(self):
        item = self.listw.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        for s in self._store.all():
            if s["name"] == name:
                self.edit_name.setText(s["name"])
                self.edit_match.setText(s["match"])
                self.edit_code.setPlainText(s["code"])
                self.chk_enabled.setChecked(s.get("enabled", True))
                return

    def _new(self):
        self.listw.clearSelection()
        self.edit_name.clear()
        self.edit_match.setText("*")
        self.edit_code.clear()
        self.chk_enabled.setChecked(True)
        self.edit_name.setFocus()

    def _save(self):
        name = self.edit_name.text().strip()
        if not name:
            return
        existing = [s["name"] for s in self._store.all()]
        if name in existing:
            self._store.remove(name)
        self._store.add(name, self.edit_match.text(),
                        self.edit_code.toPlainText(),
                        self.chk_enabled.isChecked())
        self._refresh(select_name=name)
        self._win.reinject_user_scripts()

    def _delete(self):
        item = self.listw.currentItem()
        if item:
            self._store.remove(item.data(Qt.UserRole))
            self._refresh()
            self._win.reinject_user_scripts()
