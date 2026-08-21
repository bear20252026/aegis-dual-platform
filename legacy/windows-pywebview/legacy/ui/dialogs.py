"""dialogs.py —— 主窗口高频对话框（从 main_window 提取，架构瘦身）。

包含：历史记录（按日分组 + 多选删除）、书签管理器（搜索/多选删除）、
密码管理器（加密存储的站点账号）。

样式沿用 settings_dialog 的 U-8 工具（DIALOG_MARGINS / CONTROL_HEIGHT /
section_label / unify_control_heights），与主窗口呼吸感一致。
"""

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .settings_dialog import (
    CONTROL_HEIGHT,
    DIALOG_MARGINS,
    section_label,
    unify_control_heights,
)


class HistoryDialog(QDialog):
    """历史记录对话框。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._win = window
        self.setWindowTitle("历史记录")
        self.resize(600, 520)
        # U-8：与主窗口一致的呼吸感（统一外边距 / 分区间距 / 控件高度）
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*DIALOG_MARGINS)
        lay.setSpacing(12)
        lay.addWidget(section_label("浏览历史", self))
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("搜索历史...")
        self.search.setMinimumHeight(CONTROL_HEIGHT)
        self.search.textChanged.connect(self._refresh)
        lay.addWidget(self.search)
        self.listw = QListWidget(self)
        self.listw.setSpacing(2)
        self.listw.setSelectionMode(QListWidget.ExtendedSelection)
        self.listw.itemDoubleClicked.connect(self._open)
        self.listw.itemSelectionChanged.connect(self._on_selection)
        lay.addWidget(self.listw, 1)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.lbl_stats = QLabel(self)
        btns.addWidget(self.lbl_stats)
        btns.addStretch(1)
        self.btn_del = QPushButton("删除选中", self)
        self.btn_del.setEnabled(False)
        self.btn_del.clicked.connect(self._delete_selected)
        btn_clear = QPushButton("清空历史", self)
        btn_clear.clicked.connect(self._clear)
        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.accept)
        for b in (self.btn_del, btn_clear, btn_close):
            b.setMinimumHeight(CONTROL_HEIGHT)
            btns.addWidget(b)
        lay.addLayout(btns)
        self._refresh()

    def _records(self):
        kw = self.search.text().strip()
        return self._win.ctx.history.search(kw) if kw \
            else self._win.ctx.history.all(1000)

    def _refresh(self):
        self.listw.clear()
        today, yesterday = date.today(), date.today() - timedelta(days=1)
        cur_label = None
        for r in self._records():
            dt = datetime.fromtimestamp(r["visit_time"])
            d = dt.date()
            if d == today:
                label = "今天"
            elif d == yesterday:
                label = "昨天"
            else:
                label = d.strftime("%Y-%m-%d")
            if label != cur_label:
                cur_label = label
                gh = QListWidgetItem(f"── {label} ──")
                gh.setFlags(Qt.ItemIsEnabled)   # 分组头：可见但不可选
                gh.setForeground(QBrush(QColor(120, 120, 120)))
                self.listw.addItem(gh)
            ts = dt.strftime("%m-%d %H:%M")
            item_text = f"{r['title']}  ·  {ts}\n{r['url']}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, r["url"])
            self.listw.addItem(item)
        stats = self._win.ctx.history.stats()
        self.lbl_stats.setText(
            f"共 {stats['total']} 条 · 今日 {stats['today']} 条")

    def _on_selection(self):
        self.btn_del.setEnabled(bool(self.listw.selectedItems()))

    def _open(self, item):
        self.accept()
        self._win.open_new_tab(item.data(Qt.UserRole))

    def _delete_selected(self):
        """批量删除选中的历史记录（对标 Chrome 历史的多选删除）。"""
        urls = set()
        for i in self.listw.selectedItems():
            u = i.data(Qt.UserRole)
            if u:
                urls.add(u)
        if not urls:
            return
        if QMessageBox.question(
                self, "确认", f"删除选中的 {len(urls)} 条记录？") != QMessageBox.Yes:
            return
        for u in urls:
            self._win.ctx.history.delete_url(u)
        self._refresh()

    def _clear(self):
        if QMessageBox.question(self, "确认", "清空全部历史？") == QMessageBox.Yes:
            self._win.ctx.history.clear()
            self._refresh()


class BookmarkManagerDialog(QDialog):
    """书签管理器：搜索 / 多选删除 / 双击打开（对标 Chrome 书签管理）。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._win = window
        self.setWindowTitle("书签管理")
        self.resize(560, 480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*DIALOG_MARGINS)
        lay.setSpacing(12)
        lay.addWidget(section_label("书签", self))
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("搜索书签...")
        self.search.setMinimumHeight(CONTROL_HEIGHT)
        self.search.textChanged.connect(self._refresh)
        lay.addWidget(self.search)
        self.listw = QListWidget(self)
        self.listw.setSpacing(2)
        self.listw.setSelectionMode(QListWidget.ExtendedSelection)
        self.listw.itemDoubleClicked.connect(self._open)
        self.listw.itemSelectionChanged.connect(self._on_selection)
        lay.addWidget(self.listw, 1)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.lbl_stats = QLabel(self)
        btns.addWidget(self.lbl_stats)
        btns.addStretch(1)
        self.btn_del = QPushButton("删除选中", self)
        self.btn_del.setEnabled(False)
        self.btn_del.clicked.connect(self._delete_selected)
        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.accept)
        for b in (self.btn_del, btn_close):
            b.setMinimumHeight(CONTROL_HEIGHT)
            btns.addWidget(b)
        lay.addLayout(btns)
        self._refresh()

    def _refresh(self):
        self.listw.clear()
        kw = self.search.text().strip()
        rows = self._win.ctx.bookmarks.search(kw) if kw \
            else self._win.ctx.bookmarks.all()
        for b in rows:
            item = QListWidgetItem(
                f"{b['title'] or b['url']}\n{b['url']}")
            item.setData(Qt.UserRole, b["url"])
            self.listw.addItem(item)
        self.lbl_stats.setText(f"共 {len(rows)} 条")

    def _on_selection(self):
        self.btn_del.setEnabled(bool(self.listw.selectedItems()))

    def _open(self, item):
        self.accept()
        self._win.open_new_tab(item.data(Qt.UserRole))

    def _delete_selected(self):
        urls = {i.data(Qt.UserRole) for i in self.listw.selectedItems()
                if i.data(Qt.UserRole)}
        if not urls:
            return
        if QMessageBox.question(
                self, "确认", f"删除选中的 {len(urls)} 条书签？") != QMessageBox.Yes:
            return
        for u in urls:
            self._win.ctx.bookmarks.remove(u)
        self._refresh()
        if hasattr(self._win, "_rebuild_bookmark_bar"):
            self._win._rebuild_bookmark_bar()


class PasswordDialog(QDialog):
    """密码管理器对话框（加密存储的站点账号）。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._win = window
        self.setWindowTitle("密码管理")
        self.resize(520, 420)
        # U-8：与历史/设置对话框统一的边距与分区节奏
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*DIALOG_MARGINS)
        lay.setSpacing(12)
        lay.addWidget(section_label("已保存的站点账号", self))
        self.listw = QListWidget(self)
        self.listw.setSpacing(2)
        lay.addWidget(self.listw, 1)
        lay.addWidget(section_label("新增账号", self))
        form = QHBoxLayout()
        form.setSpacing(8)
        self.edit_url = QLineEdit(self)
        self.edit_url.setPlaceholderText("网站地址 https://...")
        self.edit_user = QLineEdit(self)
        self.edit_user.setPlaceholderText("用户名")
        self.edit_pwd = QLineEdit(self)
        self.edit_pwd.setPlaceholderText("密码")
        self.edit_pwd.setEchoMode(QLineEdit.Password)
        form.addWidget(self.edit_url, 2)
        form.addWidget(self.edit_user, 1)
        form.addWidget(self.edit_pwd, 1)
        lay.addLayout(form)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btn_add = QPushButton("保存", self)
        btn_add.clicked.connect(self._save)
        btn_del = QPushButton("删除选中", self)
        btn_del.clicked.connect(self._delete)
        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.accept)
        btns.addWidget(btn_add)
        btns.addWidget(btn_del)
        btns.addStretch(1)
        btns.addWidget(btn_close)
        lay.addLayout(btns)
        unify_control_heights(self)
        self._refresh()

    def _refresh(self):
        self.listw.clear()
        for url, user in self._win.ctx.passwords.list_sites():
            item = QListWidgetItem(f"{url}  ·  {user or '(无用户名)'}")
            item.setData(Qt.UserRole, url)
            self.listw.addItem(item)

    def _save(self):
        url = self.edit_url.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        if url:
            self._win.ctx.passwords.save_password(
                url, self.edit_user.text(), self.edit_pwd.text())
            self.edit_url.clear(); self.edit_user.clear(); self.edit_pwd.clear()
            self._refresh()

    def _delete(self):
        item = self.listw.currentItem()
        if item:
            self._win.ctx.passwords.delete(item.data(Qt.UserRole))
            self._refresh()


class DialsDialog(QDialog):
    """自定义首页拨号（v2.1.5）：增删、排序、恢复默认。

    拨号即新标签页的快捷图标。自定义后 NTP 只显示该列表；
    点「恢复默认」清空自定义列表，回到"历史+书签+内置"自动组合。
    """

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._win = window
        self._store = window.ctx.dials
        self.setWindowTitle("自定义首页拨号")
        self.resize(560, 480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*DIALOG_MARGINS)
        lay.setSpacing(12)
        lay.addWidget(section_label("首页拨号（新标签页快捷图标）", self))

        self.listw = QListWidget(self)
        self.listw.setSpacing(2)
        lay.addWidget(self.listw, 1)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.btn_del = QPushButton("删除选中", self)
        self.btn_del.clicked.connect(self._delete)
        self.btn_up = QPushButton("上移", self)
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down = QPushButton("下移", self)
        self.btn_down.clicked.connect(lambda: self._move(1))
        self.btn_reset = QPushButton("恢复默认", self)
        self.btn_reset.clicked.connect(self._reset)
        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.accept)
        for b in (self.btn_del, self.btn_up, self.btn_down,
                  self.btn_reset, btn_close):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

        lay.addWidget(section_label("新增拨号", self))
        form = QHBoxLayout()
        form.setSpacing(8)
        self.edit_name = QLineEdit(self)
        self.edit_name.setPlaceholderText("名称（可留空）")
        self.edit_url = QLineEdit(self)
        self.edit_url.setPlaceholderText("网址 https://...")
        btn_add = QPushButton("添加", self)
        btn_add.clicked.connect(self._add)
        form.addWidget(self.edit_name, 1)
        form.addWidget(self.edit_url, 2)
        form.addWidget(btn_add)
        lay.addLayout(form)

        unify_control_heights(self)
        self._refresh()

    def _refresh(self):
        self.listw.clear()
        for name, url in self._store.all():
            item = QListWidgetItem(f"{name}  ·  {url}")
            item.setData(Qt.UserRole, url)
            self.listw.addItem(item)
        if self._store.is_customized():
            self._win.status.showMessage("当前使用自定义首页拨号", 3000)

    def _add(self):
        url = self.edit_url.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        if not url:
            return
        ok = self._store.add(self.edit_name.text(), url)
        if not ok:
            QMessageBox.information(
                self, "添加失败", "该网址无效、已存在，或拨号数量已达上限。")
            return
        self.edit_name.clear(); self.edit_url.clear()
        self._refresh()

    def _delete(self):
        item = self.listw.currentItem()
        if item:
            self._store.remove(item.data(Qt.UserRole))
            self._refresh()

    def _move(self, delta):
        row = self.listw.currentRow()
        if row >= 0:
            self._store.move(row, delta)
            self._refresh()
            self.listw.setCurrentRow(row + delta)

    def _reset(self):
        if QMessageBox.question(
                self, "恢复默认", "清空自定义拨号，恢复自动组合？") \
                == QMessageBox.Yes:
            self._store.clear()
            self._refresh()
