# -*- coding: utf-8 -*-
"""address_bar.py —— 商用级地址栏。

特性：
- 玻璃态圆角外观
- 下拉联想：搜索建议（远程）+ 历史 + 书签，聚合展示
- 键盘上下选择 / Enter 确认 / Esc 关闭
- 图标区分建议类型
"""

import urllib.parse
from PySide6.QtCore import Qt, QUrl, QRect, QTimer, QObject, Signal
from PySide6.QtGui import QIcon, QFont, QColor
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QLineEdit, QListWidget, QListWidgetItem, QFrame, QLabel,
    QHBoxLayout, QVBoxLayout,
)

from .icons import icon

# 建议项类型
TYPE_HEADER = -1
TYPE_SEARCH = 0
TYPE_HISTORY = 1
TYPE_BOOKMARK = 2

_ICONS = {
    TYPE_SEARCH: "search",
    TYPE_HISTORY: "history",
    TYPE_BOOKMARK: "bookmark",
}


class SuggestionPopup(QFrame):
    """地址栏下拉联想弹层。"""

    # 用户选中一条 (url)
    activated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("addressPopup")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowOpacity(0.98)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.list_widget = QListWidget(self)
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.itemClicked.connect(self._on_clicked)
        self.list_widget.itemActivated.connect(self._on_clicked)
        layout.addWidget(self.list_widget)
        self._items = []  # 每项对应 url（None=header）

    def set_suggestions(self, suggestions):
        """suggestions: [(kind, title, subtitle, url)]，None url 为分组标题。"""
        self.list_widget.clear()
        self._items = []
        for kind, title, subtitle, url in suggestions:
            self._items.append(url)
            item = QListWidgetItem()
            if kind == TYPE_HEADER:
                item.setData(Qt.UserRole, title)
                item.setFlags(Qt.NoItemFlags)
                item.setSizeHint(item.sizeHint().expandedTo(
                    item.sizeHint()))
            else:
                iname = _ICONS.get(kind)
                if iname:
                    item.setIcon(icon(iname))
                item.setText(title)
                item.setData(Qt.UserRole, title)
                item.setToolTip(subtitle or url or "")
            self.list_widget.addItem(item)

    def _on_clicked(self, item):
        row = self.list_widget.row(item)
        url = self._items[row] if row < len(self._items) else None
        if url:
            self.activated.emit(url)
            self.hide()


class AddressBar(QLineEdit):
    """地址栏控件：输入联想 + 导航。"""

    # 用户按下回车，参数为解析后的 url
    navigate = Signal(str)
    # 用户请求在新标签页打开（Ctrl+Enter）
    navigate_new_tab = Signal(str)

    def __init__(self, search_engines, history, bookmarks, parent=None):
        super().__init__(parent)
        self.setObjectName("addressBar")
        self._engines = search_engines
        self._history = history
        self._bookmarks = bookmarks

        self.setPlaceholderText("搜索或输入网址")
        self.setClearButtonEnabled(True)

        # 联想弹层
        self._popup = SuggestionPopup(self)
        self._popup.activated.connect(self._go_suggestion)

        # 网络建议（异步）
        self._net = QNetworkAccessManager(self)
        self._net.finished.connect(self._on_suggest_finished)
        self._suggest_pending = ""
        self._suggest_timer = QTimer(self)
        self._suggest_timer.setSingleShot(True)
        self._suggest_timer.setInterval(220)
        self._suggest_timer.timeout.connect(self._fetch_suggestions)

        self.textEdited.connect(self._on_text_edited)
        self.returnPressed.connect(self._on_return)

        self._selected_text = ""

    # ------------------------------------------------------------------ #
    def current_url(self) -> str:
        """把当前文本解析为可加载 URL。"""
        return self._engines.parse_input(self.text())

    # ------------------------------------------------------------------ #
    def _on_text_edited(self, text):
        if not text:
            self._popup.hide()
            return
        self._suggest_timer.start()
        # 立即显示本地建议
        self._show_local_suggestions(text)

    def _show_local_suggestions(self, text):
        suggestions = [(TYPE_HEADER, "浏览记录与书签", "", None)]
        for url, title, _score in self._history.suggest(text):
            suggestions.append((TYPE_HISTORY, title, url, url))
        for url, title, _score in self._bookmarks.suggest(text):
            suggestions.append((TYPE_BOOKMARK, title, url, url))
        # 合并去重（URL 去重）
        seen = set()
        merged = [suggestions[0]]
        for s in suggestions[1:]:
            if s[3] and s[3] not in seen:
                seen.add(s[3])
                merged.append(s)
        self._popup.set_suggestions(merged[:20])
        self._popup.setGeometry(self._popup_rect())
        self._popup.show()
        self._popup.raise_()

    def _fetch_suggestions(self):
        # v1.4 L6 修复：远程建议会把输入实时发给搜索引擎，可由用户关闭
        if not getattr(getattr(self._engines, "config", None),
                       "search_suggestions", True):
            return
        text = self.text().strip()
        if not text:
            return
        url = self._suggest_url(text)
        if not url:
            return
        self._suggest_pending = text
        self._net.get(QNetworkRequest(QUrl(url)))

    def _suggest_url(self, text) -> str:
        eng = self._engines.current()
        q = urllib.parse.quote(text)
        suggest = getattr(self._engines, "_suggest_urls", {}).get(eng)
        if suggest:
            return suggest.format(query=q)
        return None

    def _on_suggest_finished(self, reply):
        try:
            if reply.error() != reply.NoError:
                return
            data = bytes(reply.readAll()).decode("utf-8", "ignore")
        except Exception:
            return
        # 解析 bing jsonp:  ["query",["s1","s2",...]]
        kw = self._suggest_pending
        if not kw:
            return
        words = _parse_suggest(data)
        if not words:
            return
        suggestions = [(TYPE_HEADER, "搜索建议", "", None)]
        for w in words[:8]:
            suggestions.append((TYPE_SEARCH, w,
                                f"在搜索引擎中搜索“{w}”",
                                self._engines.search_url(w)))
        # 若地址栏仍显示该关键词，则更新弹层（本地部分已展示，追加搜索建议）
        if self.text().strip() == kw:
            self._show_remote_only(suggestions)

    def _show_remote_only(self, suggestions):
        # 合并本地 + 远程（远程在前）
        text = self.text().strip()
        local = []
        for url, title, _s in self._history.suggest(text):
            local.append((TYPE_HISTORY, title, url, url))
        for url, title, _s in self._bookmarks.suggest(text):
            local.append((TYPE_BOOKMARK, title, url, url))
        seen = set()
        merged = suggestions
        for s in local:
            if s[3] and s[3] not in seen:
                seen.add(s[3])
                merged.append(s)
        self._popup.set_suggestions(merged[:24])
        self._popup.setGeometry(self._popup_rect())
        if not self._popup.isVisible():
            self._popup.show()
        self._popup.raise_()

    def _popup_rect(self) -> QRect:
        # Popup 是顶级窗口，setGeometry 需要全局坐标。
        # 此前用控件本地坐标，会导致下拉弹层飞到屏幕左上角。
        global_tl = self.mapToGlobal(self.rect().bottomLeft())
        return QRect(global_tl.x(), global_tl.y() + 4,
                     max(self.width(), 420), 340)

    def _go_suggestion(self, url):
        self.setText(url)
        self.navigate.emit(url)

    # ------------------------------------------------------------------ #
    def _on_return(self):
        # 若弹层中有选中的建议项，则优先打开该建议
        if self._popup.isVisible():
            row = self._popup.list_widget.currentRow()
            if 0 <= row < len(self._popup._items):
                url = self._popup._items[row]
                if url:
                    self._popup.hide()
                    self.setText(url)
                    self.navigate.emit(url)
                    return
        self._popup.hide()
        text = self.text().strip()
        if not text:
            return
        self.navigate.emit(self._engines.parse_input(text))

    # ------------------------------------------------------------------ #
    def focusInEvent(self, event):
        super().focusInEvent(event)
        # 全选便于覆盖输入
        if self.text():
            QTimer.singleShot(0, self.selectAll)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if not self._popup.underMouse():
            self._popup.hide()

    def keyPressEvent(self, event):
        key = event.key()
        if self._popup.isVisible():
            if key == Qt.Key_Down:
                row = self._popup.list_widget.currentRow()
                self._popup.list_widget.setCurrentRow(row + 1)
                return
            if key == Qt.Key_Up:
                row = self._popup.list_widget.currentRow()
                self._popup.list_widget.setCurrentRow(max(0, row - 1))
                return
            if key == Qt.Key_Escape:
                self._popup.hide()
                return
        # Ctrl+Enter 新标签页打开
        if event.modifiers() & Qt.ControlModifier and key == Qt.Key_Return:
            self._popup.hide()
            self.navigate_new_tab.emit(self._engines.parse_input(self.text()))
            return
        super().keyPressEvent(event)

    def hideEvent(self, event):
        self._popup.hide()
        super().hideEvent(event)


def _parse_suggest(data: str) -> list:
    """解析 Bing 搜索建议 JSONP。"""
    import re
    # 形如 ["kw",["a","b"]] 或 {"q":"kw","s":["a","b"]}
    m = re.search(r'\[".*?"\s*,\s*(\[.*?\])', data, re.DOTALL)
    if m:
        try:
            import json
            arr = json.loads(m.group(1))
            return [str(x) for x in arr]
        except Exception:
            return []
    m2 = re.search(r'"s"\s*:\s*(\[.*?\])', data, re.DOTALL)
    if m2:
        try:
            import json
            arr = json.loads(m2.group(1))
            return [str(x) for x in arr]
        except Exception:
            return []
    return []
