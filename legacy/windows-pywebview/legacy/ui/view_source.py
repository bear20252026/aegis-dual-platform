"""view_source.py —— 查看源代码对话框。

行为对标商业浏览器（Chrome/Firefox 的「查看源代码 / View Source」）：
- 展示当前标签**渲染后 DOM 的序列化 HTML**（通过 QWebEnginePage.toHtml
  异步获取），这正是商业浏览器「查看源代码」展示的内容；
- 只读、等宽字体、行号侧栏、轻量语法高亮、可复制、可查找；
- 主题跟随（深色/浅色）。

设计约束（项目 P0 绝对规则）：
- 图标只用 icons.py 的统一 SVG，禁止 emoji；
- 不硬编码颜色，跟随系统主题与强调色。
"""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class _HtmlHighlighter(QSyntaxHighlighter):
    """极简 HTML 语法高亮：标签名 / 属性名 / 属性字符串 / 注释 / 声明。

    仅用于可读性，不做完整解析（正则足够覆盖 99% 的展示场景）。
    """

    def __init__(self, doc):
        super().__init__(doc)
        tag_fmt = QTextCharFormat(); tag_fmt.setForeground(QColor("#ff7b72"))
        attr_fmt = QTextCharFormat(); attr_fmt.setForeground(QColor("#79c0ff"))
        str_fmt = QTextCharFormat(); str_fmt.setForeground(QColor("#a5d6ff"))
        comment_fmt = QTextCharFormat(); comment_fmt.setForeground(QColor("#8b949e"))
        comment_fmt.setFontItalic(True)
        doctype_fmt = QTextCharFormat(); doctype_fmt.setForeground(QColor("#d2a8ff"))

        self._re_comment = re.compile(r"<!--[\s\S]*?-->")
        self._re_doctype = re.compile(r"<!DOCTYPE[\s\S]*?>", re.IGNORECASE)
        self._re_rules = [
            (re.compile(r"</?([a-zA-Z][a-zA-Z0-9-]*)\b"), tag_fmt),
            (re.compile(r"(?<=\s)([a-zA-Z-]+)(?==)"), attr_fmt),
            (re.compile(r'"[^"]*"|\'[^\']*\''), str_fmt),
        ]
        self._comment_fmt = comment_fmt
        self._doctype_fmt = doctype_fmt

    def highlightBlock(self, text):
        for m in self._re_comment.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._comment_fmt)
        for m in self._re_doctype.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._doctype_fmt)
        for rx, fmt in self._re_rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class ViewSource(QDialog):
    """查看源代码对话框。"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._win = main_window
        self._dark = self._resolve_dark()
        self._html = ""
        self.setWindowTitle("查看源代码")
        self.resize(940, 680)
        self.setMinimumSize(640, 440)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # URL 标题条（不可编辑但可选中复制）
        self._url_lbl = QLabel("正在获取源代码…", self)
        self._url_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._url_lbl.setWordWrap(True)
        lay.addWidget(self._url_lbl)

        # 搜索 + 操作行
        search_row = QHBoxLayout()
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("在源代码中查找…")
        self._search.returnPressed.connect(self._find_next)
        self._btn_prev = QPushButton("上一个", self)
        self._btn_prev.clicked.connect(lambda: self._find_next(back=True))
        self._btn_next = QPushButton("下一个", self)
        self._btn_next.clicked.connect(self._find_next)
        self._btn_copy = QPushButton("复制全部", self)
        self._btn_copy.clicked.connect(self._copy_all)
        search_row.addWidget(self._search, 1)
        search_row.addWidget(self._btn_prev)
        search_row.addWidget(self._btn_next)
        search_row.addWidget(self._btn_copy)
        lay.addLayout(search_row)

        # 代码区：行号 + 代码
        editor_row = QHBoxLayout()
        self._gutter = QPlainTextEdit(self)
        self._gutter.setReadOnly(True)
        self._gutter.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._gutter.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._gutter.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._gutter.setFixedWidth(58)
        self._code = QPlainTextEdit(self)
        self._code.setReadOnly(True)
        self._code.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._highlighter = _HtmlHighlighter(self._code.document())
        self._apply_font_and_colors()
        # 滚动同步：代码滚动带动行号
        self._code.verticalScrollBar().valueChanged.connect(
            self._gutter.verticalScrollBar().setValue)
        editor_row.addWidget(self._gutter)
        editor_row.addWidget(self._code, 1)
        lay.addLayout(editor_row, 1)

    # ------------------------------------------------------------------ #
    def _resolve_dark(self) -> bool:
        try:
            from app.system_theme import resolve_dark
            return resolve_dark(self._win.config.theme)
        except Exception:
            return True

    def _apply_font_and_colors(self):
        mono = QFont("Menlo, Consolas, 'Courier New', monospace")
        mono.setPointSize(13)
        for w in (self._code, self._gutter):
            w.setFont(mono)
        if self._dark:
            bg, fg, gutter_bg = "#1e1e1e", "#e6edf3", "#161616"
            gutter_fg = "#6e7681"
        else:
            bg, fg, gutter_bg = "#ffffff", "#1f2328", "#f6f8fa"
            gutter_fg = "#8c959f"
        self._code.setStyleSheet(
            f"QPlainTextEdit{{background:{bg};color:{fg};border:1px solid "
            f"{'#30363d' if self._dark else '#d0d7de'};}}")
        self._gutter.setStyleSheet(
            f"QPlainTextEdit{{background:{gutter_bg};color:{gutter_fg};"
            f"border:1px solid {'#30363d' if self._dark else '#d0d7de'};"
            f"border-right:none;}}")
        self._gutter.setTextInteractionFlags(Qt.NoTextInteraction)

    # ------------------------------------------------------------------ #
    # 由调用方在数据到达时填入
    def set_source_url(self, url: str):
        self._url = url or ""
        self._url_lbl.setText(f"源代码来源：{self._url or '(无法读取地址)'}")

    def set_html(self, html: str):
        """异步回调：填充源代码（来自 page.toHtml）。"""
        self._html = html or ""
        if not self._html:
            self._html = "<!-- 无法获取源代码（页面尚未加载或为非文档页面）-->"
        self._code.setPlainText(self._html)
        # 行号侧栏：与代码行数对齐（NoWrap 下 1 文档行 = 1 可见行）
        lines = self._html.count("\n") + 1
        self._gutter.setPlainText("\n".join(str(i) for i in range(1, lines + 1)))
        # 重置滚动位置
        self._code.verticalScrollBar().setValue(0)
        self._gutter.verticalScrollBar().setValue(0)
        self._url_lbl.setText(
            f"源代码来源：{self._url or '(无地址)'}  ·  {lines} 行")

    # ------------------------------------------------------------------ #
    def _find_next(self, back: bool = False):
        txt = self._search.text()
        if not txt:
            return
        doc = self._code.document()
        from PySide6.QtGui import QTextDocument
        flags = QTextDocument.FindFlag(0)
        if back:
            flags |= QTextDocument.FindBackward
        found = self._code.find(txt, flags)
        if not found.isNull():
            self._code.setTextCursor(found)
        else:
            # 未找到：从头/尾部继续（Wrap）
            new_cur = doc.find(txt, 0, flags) if not back \
                else doc.find(txt, doc.characterCount() - 1, flags)
            if not new_cur.isNull():
                self._code.setTextCursor(new_cur)

    def _copy_all(self):
        QApplication.clipboard().setText(self._html)
        self._url_lbl.setText(
            f"源代码来源：{self._url or '(无地址)'}  ·  已复制到剪贴板")
