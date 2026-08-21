"""ima_knowledge.py —— 浏览并阅读 IMA 知识库（如「昆仑山知识库」）。

读取你 IMA 里的知识库列表、某个库下的内容（文件 / 文件夹 / 笔记），
打开文件类条目会在新标签页渲染原文，笔记类条目则直接显示纯文本。
底层复用已审计的 IMA OpenAPI 脚本，凭证仅发往 ima.qq.com。

设计约束（项目 P0 绝对规则）：
- 不使用 emoji 图标；不硬编码颜色（沿用系统主题与项目强调色 #0071e3）。
"""

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app import ima_client

_ACCENT = "#0071e3"


class _KbWorker(QThread):
    """通用后台调用 worker：在子线程跑 ima_client 的纯函数。"""
    done = Signal(object)

    def __init__(self, fn, args):
        super().__init__()
        self._fn = fn
        self._args = args

    def run(self):
        try:
            res = self._fn(*self._args)
        except Exception as exc:  # pragma: no cover - 防御性
            res = (False, None, None, f"调用异常：{exc}")
        self.done.emit(res)


class ImaKnowledgeDialog(QDialog):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self._win = win
        self._worker = None
        self._kb_id = None
        self._folder_stack = []        # 文件夹 media_id 栈（用于下钻）
        self._folder_names = []        # 对应的文件夹名（用于面包屑）
        self.setWindowTitle("IMA 知识库")
        self.resize(640, 560)
        self._build_ui()
        self._load_kbs()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        root = QVBoxLayout(self)

        row_kb = QHBoxLayout()
        row_kb.addWidget(QLabel("知识库"))
        self._kb_combo = QComboBox(self)
        self._kb_combo.setMinimumWidth(220)
        row_kb.addWidget(self._kb_combo, 1)
        self._btn_refresh_kb = QPushButton("刷新", self)
        self._btn_refresh_kb.clicked.connect(self._load_kbs)
        row_kb.addWidget(self._btn_refresh_kb)
        root.addLayout(row_kb)

        row_nav = QHBoxLayout()
        self._btn_back = QPushButton("返回上级", self)
        self._btn_back.clicked.connect(self._go_back)
        self._btn_back.setEnabled(False)
        row_nav.addWidget(self._btn_back)
        self._crumb = QLabel("")
        row_nav.addWidget(self._crumb, 1)
        root.addLayout(row_nav)

        self._list = QListWidget(self)
        self._list.itemDoubleClicked.connect(self._open_selected)
        root.addWidget(self._list, 1)

        row_ops = QHBoxLayout()
        self._btn_open = QPushButton("打开", self)
        self._btn_open.setStyleSheet(
            f"QPushButton{{background:{_ACCENT};color:#fff;border-radius:6px;"
            f"padding:6px 14px;}}")
        self._btn_open.clicked.connect(self._open_selected)
        row_ops.addWidget(self._btn_open)
        root.addLayout(row_ops)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._viewer = QPlainTextEdit(self)
        self._viewer.setReadOnly(True)
        self._viewer.setPlaceholderText(
            "笔记原文显示在这里；文件类条目会在新标签页打开。")
        self._viewer.setMaximumHeight(160)
        root.addWidget(self._viewer)

    # ------------------------------------------------------------------ #
    # 知识库列表
    # ------------------------------------------------------------------ #
    def _load_kbs(self):
        if not ima_client.is_configured():
            self._set_status(ima_client.config_hint(), warn=True)
            return
        self._btn_refresh_kb.setEnabled(False)
        self._run_worker(ima_client.list_knowledge_bases, (20,), self._on_kbs)

    def _on_kbs(self, res):
        self._btn_refresh_kb.setEnabled(True)
        ok, items, err = res
        if not ok:
            self._set_status(f"读取知识库失败：{err}", warn=True)
            return
        self._kb_combo.clear()
        for it in items:
            self._kb_combo.addItem(it["name"], it["kb_id"])
        if items:
            self._kb_id = items[0]["kb_id"]
            self._set_status(f"共 {len(items)} 个知识库，已选「{items[0]['name']}」。",
                            ok=True)
            try:
                self._kb_combo.currentIndexChanged.disconnect()
            except Exception:
                pass
            self._kb_combo.currentIndexChanged.connect(self._on_kb_changed)
            self._folder_stack = []
            self._folder_names = []
            self._load_docs()
        else:
            self._set_status("你还没有任何知识库。", ok=True)

    def _on_kb_changed(self, idx):
        self._kb_id = self._kb_combo.itemData(idx)
        self._folder_stack = []
        self._folder_names = []
        self._load_docs()

    # ------------------------------------------------------------------ #
    # 内容列表（支持文件夹下钻）
    # ------------------------------------------------------------------ #
    def _load_docs(self):
        if not self._kb_id:
            return
        folder_id = self._folder_stack[-1] if self._folder_stack else None
        self._run_worker(ima_client.list_kb_docs,
                         (self._kb_id, folder_id, 20), self._on_docs)

    def _on_docs(self, res):
        ok, items, err = res
        if not ok:
            self._set_status(f"读取内容失败：{err}", warn=True)
            return
        self._list.clear()
        for it in items:
            label = it["title"] + ("  [文件夹]" if it["is_folder"] else "")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, it)
            self._list.addItem(item)
        crumb = " / ".join([self._kb_combo.currentText()] + self._folder_names)
        self._crumb.setText(crumb)
        self._btn_back.setEnabled(bool(self._folder_stack))
        self._set_status(f"共 {len(items)} 条内容。", ok=True)

    # ------------------------------------------------------------------ #
    # 打开条目
    # ------------------------------------------------------------------ #
    def _open_selected(self):
        item = self._list.currentItem()
        if not item:
            self._set_status("请先选择一条内容。", warn=True)
            return
        it = item.data(Qt.ItemDataRole.UserRole)
        if it["is_folder"]:
            self._folder_stack.append(it["media_id"])
            self._folder_names.append(it["title"])
            self._load_docs()
            return
        self._run_worker(ima_client.get_kb_doc_content,
                         (it["media_id"],), self._on_content)

    def _on_content(self, res):
        ok, kind, payload, err = res
        if not ok:
            self._set_status(f"打开失败：{err}", warn=True)
            return
        if kind == "url":
            self._set_status("正在新标签页打开原文…", ok=True)
            self._viewer.clear()
            try:
                self._win.new_tab(payload)
            except Exception as exc:
                self._set_status(f"打开失败：{exc}", warn=True)
        else:
            self._viewer.setPlainText(payload or "")
            self._set_status("已载入笔记原文。", ok=True)

    def _go_back(self):
        if self._folder_stack:
            self._folder_stack.pop()
            self._folder_names.pop()
            self._load_docs()

    # ------------------------------------------------------------------ #
    # 通用
    # ------------------------------------------------------------------ #
    def _run_worker(self, fn, args, handler):
        if self._worker and self._worker.isRunning():
            self._worker.wait()
        self._worker = _KbWorker(fn, args)
        self._worker.done.connect(handler)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _set_status(self, text, ok=False, warn=False):
        color = "#1a7f37" if ok else (_ACCENT if not warn else "#c0392b")
        self._status.setText(f'<span style="color:{color};">{text}</span>')

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.wait()
        super().closeEvent(event)
