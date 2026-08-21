"""command_palette.py —— 命令面板（超标对标：多数商业浏览器无此能力）。

类 VSCode 命令面板：Ctrl+Shift+P 唤起，输入即过滤，↑↓ 选择，Enter 执行。
把高频操作集中到一个键盘可达入口，是"超越商业浏览器"的交互增强。

设计约束（项目 P0 绝对规则）：
- 不使用 emoji 图标；
- 不硬编码颜色（沿用系统主题）。
"""

from app.i18n import tr
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


class CommandPalette(QDialog):
    """命令面板。"""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self._win = win
        self.setWindowTitle("命令面板")
        self.resize(480, 360)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("输入命令，如 查看源代码 / 深色 / 历史 …")
        self._search.textChanged.connect(self._filter)
        lay.addWidget(self._search)

        self._list = QListWidget(self)
        self._list.itemActivated.connect(self._run)
        lay.addWidget(self._list, 1)

        self._build_actions()
        self._filter("")
        self._search.setFocus()
        # 顶部居中显示
        if parent:
            geo = parent.geometry()
            self.move(geo.x() + geo.width() // 2 - self.width() // 2,
                      geo.y() + 80)

    # ------------------------------------------------------------------ #
    def _build_actions(self):
        w = self._win
        self._actions = [
            (tr("查看源代码"), "Ctrl+U", w._open_view_source),
            (tr("安全仪表盘"), "", w._open_security_dashboard),
            (tr("清除浏览数据"), "", w._clear_data),
            (tr("站点信息"), "", w._open_site_info),
            (tr("强制深色模式"), "", w._toggle_force_dark),
            (tr("视觉问答（AI）"), "", w._open_vision_panel),
            (tr("AI 上网代理"), "", w._open_computer_use),
            (tr("AI 助手（本地）"), "", w._open_translate),
            (tr("保存到 IMA 笔记"), "", w._open_ima_notes),
            (tr("IMA 知识库"), "", w._open_ima_kb),
            (tr("密码工具"), "", w._open_password_tools),
            (tr("网页截图 (PNG)"), "", w._capture_screenshot),
            (tr("导入书签"), "", w._import_bookmarks),
            (tr("导出书签"), "", w._export_bookmarks),
            (tr("新建标签页"), "Ctrl+T", lambda: w.new_tab()),
            (tr("关闭当前标签"), "Ctrl+W", w._close_current),
            (tr("书签栏 显示/隐藏"), "", w._toggle_bookmark_bar),
            (tr("历史记录"), "Ctrl+H", w._open_history),
            (tr("任务管理器"), "", w._open_task_manager),
            (tr("阅读模式"), "", w._reader_mode),
            (tr("打印为 PDF"), "", w._print_pdf),
            (tr("全屏"), "F11", w._toggle_fullscreen),
            (tr("后退"), "Alt+←", w._back),
            (tr("前进"), "Alt+→", w._forward),
            (tr("刷新"), "F5", w._reload),
            (tr("停止加载"), "Esc", w._stop),
            (tr("复制当前网址"), "", w._copy_url),
            (tr("查找"), "Ctrl+F", w._show_find),
            (tr("设置"), "", w._open_settings),
            (tr("关于"), "", w._about),
            (tr("无痕新窗口"), "", w._new_incognito),
        ]

    def _filter(self, text):
        self._list.clear()
        t = text.strip().lower()
        for title, shortcut, fn in self._actions:
            if not t or t in title.lower() or t in shortcut.lower():
                label = title + (f"   ({shortcut})" if shortcut else "")
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, fn)
                self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _run(self, item=None):
        if item is None:
            item = self._list.currentItem()
        if not item:
            return
        fn = item.data(Qt.UserRole)
        if callable(fn):
            self.accept()
            fn()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Up and self._list.currentRow() > 0:
            self._list.setCurrentRow(self._list.currentRow() - 1)
        elif e.key() == Qt.Key_Down and self._list.currentRow() < self._list.count() - 1:
            self._list.setCurrentRow(self._list.currentRow() + 1)
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._run()
        elif e.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(e)
