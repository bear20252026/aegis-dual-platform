# -*- coding: utf-8 -*-
"""ima_notes.py —— "边看网页，边存笔记到 IMA 知识库"对话框。

把当前正在看的网页（标题 + 网址）连同你写的备注、选中的原文，整理成一篇
Markdown 笔记，保存到你的 IMA（腾讯云知识库）。全部走 IMA OpenAPI，需先在
~/.config/ima/api_key 配置 API Key（Client ID 已就位）。

设计约束（项目 P0 绝对规则）：
- 不使用 emoji 图标；不硬编码颜色（沿用系统主题与项目强调色 #0071e3）。
- 调用逻辑全部在 app.ima_client 中，UI 只负责组装与展示。
"""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QPlainTextEdit, QLabel, QComboBox, QFrame,
)

import app.ima_client as ima_client

_ACCENT = "#0071e3"


class _ImaWorker(QThread):
    """通用后台调用 worker：在子线程跑 ima_client 的纯函数，避免界面卡顿。"""
    done = Signal(object)  # 结果元组 (ok, payload, error)

    def __init__(self, fn, args):
        super().__init__()
        self._fn = fn
        self._args = args

    def run(self):
        try:
            res = self._fn(*self._args)
        except Exception as exc:  # pragma: no cover - 防御性
            res = (False, None, f"调用异常：{exc}")
        self.done.emit(res)


class ImaNotesDialog(QDialog):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self._win = win
        self._worker = None
        self.setWindowTitle("保存到 IMA 知识库")
        self.resize(560, 600)
        self._build_ui()
        self._prefill_page()
        self._refresh_status()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        root = QVBoxLayout(self)

        tip = QLabel("把当前网页连同你的备注，存进 IMA 知识库（云端，需 API Key）。")
        tip.setWordWrap(True)
        root.addWidget(tip)

        # 标题 + 网址
        row_title = QHBoxLayout()
        row_title.addWidget(QLabel("标题"))
        self._title = QLineEdit(self)
        row_title.addWidget(self._title, 1)
        root.addLayout(row_title)

        row_url = QHBoxLayout()
        row_url.addWidget(QLabel("来源"))
        self._url = QLineEdit(self)
        self._url.setReadOnly(True)
        row_url.addWidget(self._url, 1)
        root.addLayout(row_url)

        # 网页摘录（来自选中文字）
        root.addWidget(QLabel("网页摘录（点下方按钮填入选中文字）"))
        self._excerpt = QPlainTextEdit(self)
        self._excerpt.setPlaceholderText("网页中选中的原文会显示在这里…")
        self._excerpt.setMaximumHeight(130)
        root.addWidget(self._excerpt)

        # 我的笔记
        root.addWidget(QLabel("我的笔记（你的批注）"))
        self._note = QPlainTextEdit(self)
        self._note.setPlaceholderText("在这里写你自己的备注、想法、待办…")
        self._note.setMinimumHeight(120)
        root.addWidget(self._note)

        # 操作按钮
        row_ops = QHBoxLayout()
        self._btn_sel = QPushButton("填入选中文字", self)
        self._btn_sel.clicked.connect(self._fill_selection)
        self._btn_save = QPushButton("保存到 IMA", self)
        self._btn_save.setStyleSheet(
            f"QPushButton{{background:{_ACCENT};color:#fff;border-radius:6px;padding:6px 14px;}}")
        self._btn_save.clicked.connect(self._save)
        row_ops.addWidget(self._btn_sel)
        row_ops.addWidget(self._btn_save)
        root.addLayout(row_ops)

        # 追加到最近笔记
        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)
        row_append = QHBoxLayout()
        row_append.addWidget(QLabel("追加到最近笔记："))
        self._note_combo = QComboBox(self)
        self._note_combo.setMinimumWidth(220)
        row_append.addWidget(self._note_combo, 1)
        self._btn_refresh = QPushButton("刷新列表", self)
        self._btn_refresh.clicked.connect(self._load_notes)
        self._btn_append = QPushButton("追加", self)
        self._btn_append.clicked.connect(self._append)
        row_append.addWidget(self._btn_refresh)
        row_append.addWidget(self._btn_append)
        root.addLayout(row_append)

        # 状态
        self._status = QLabel("")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        root.addStretch(1)
        self._btn_cancel = QPushButton("关闭", self)
        self._btn_cancel.clicked.connect(self.reject)
        root.addWidget(self._btn_cancel)

    # ------------------------------------------------------------------ #
    # 页面信息
    # ------------------------------------------------------------------ #
    def _current_tab(self):
        try:
            return self._win.current_tab()
        except Exception:
            return None

    def _prefill_page(self):
        t = self._current_tab()
        if not t:
            return
        try:
            self._title.setText(t.title() or "")
        except Exception:
            pass
        try:
            self._url.setText(t.url() or "")
        except Exception:
            pass

    def _fill_selection(self):
        t = self._current_tab()
        if not t:
            self._set_status("未找到当前标签页。", warn=True)
            return
        try:
            t.run_js("window.getSelection().toString()", self._on_selection)
        except Exception as exc:
            self._set_status(f"无法获取选中文字：{exc}", warn=True)

    def _on_selection(self, text):
        sel = (text or "").strip()
        if not sel:
            self._set_status("当前网页没有选中文字。", warn=True)
            return
        existing = self._excerpt.toPlainText().strip()
        merged = (existing + "\n\n" + sel).strip() if existing else sel
        self._excerpt.setPlainText(merged)
        self._set_status("已填入选中文字。", ok=True)

    # ------------------------------------------------------------------ #
    # 保存到 IMA（新建）
    # ------------------------------------------------------------------ #
    def _save(self):
        if not ima_client.is_configured():
            self._set_status(ima_client.config_hint(), warn=True)
            return
        title = self._title.text().strip() or "未命名网页剪辑"
        url = self._url.text().strip()
        body = self._note.toPlainText().strip()
        excerpt = self._excerpt.toPlainText().strip()
        if not body and not excerpt and not url:
            self._set_status("没有可保存的内容（备注与摘录都为空）。", warn=True)
            return
        self._btn_save.setEnabled(False)
        self._set_status("正在保存到 IMA…")
        self._run_worker(
            ima_client.save_web_clip,
            (title, url, body, excerpt),
            self._on_saved,
        )

    def _on_saved(self, res):
        self._btn_save.setEnabled(True)
        ok, note_id, err = res
        if not ok:
            self._set_status(f"保存失败：{err}", warn=True)
            return
        self._set_status(f"已保存为笔记（ID: {note_id}）。可去 IMA 查看。", ok=True)
        self._load_notes()

    # ------------------------------------------------------------------ #
    # 追加到已有笔记
    # ------------------------------------------------------------------ #
    def _load_notes(self):
        if not ima_client.is_configured():
            return
        self._btn_refresh.setEnabled(False)
        self._run_worker(ima_client.list_notes, (20,), self._on_notes)

    def _on_notes(self, res):
        self._btn_refresh.setEnabled(True)
        ok, items, err = res
        if not ok:
            self._set_status(f"读取笔记列表失败：{err}", warn=True)
            return
        self._note_combo.clear()
        for it in items:
            label = it.get("title") or "(无标题)"
            self._note_combo.addItem(label, it.get("note_id"))
        if items:
            self._set_status(f"已载入 {len(items)} 篇最近笔记。", ok=True)
        else:
            self._set_status("你还没有任何笔记。", ok=True)

    def _append(self):
        if not ima_client.is_configured():
            self._set_status(ima_client.config_hint(), warn=True)
            return
        note_id = self._note_combo.currentData()
        if not note_id:
            self._set_status("请先在上方选择一篇笔记。", warn=True)
            return
        excerpt = self._excerpt.toPlainText().strip()
        note = self._note.toPlainText().strip()
        content = ""
        if excerpt:
            content += "## 网页摘录\n\n" + excerpt + "\n\n"
        if note:
            content += "## 我的笔记\n\n" + note + "\n\n"
        if not content.strip():
            self._set_status("没有可追加的内容。", warn=True)
            return
        self._btn_append.setEnabled(False)
        self._set_status("正在追加到笔记…")
        self._run_worker(
            ima_client.append_note, (note_id, content.strip()), self._on_appended
        )

    def _on_appended(self, res):
        self._btn_append.setEnabled(True)
        ok, err = res
        if not ok:
            self._set_status(f"追加失败：{err}", warn=True)
            return
        self._set_status("已追加到所选笔记。", ok=True)

    # ------------------------------------------------------------------ #
    # 通用
    # ------------------------------------------------------------------ #
    def _run_worker(self, fn, args, handler):
        if self._worker and self._worker.isRunning():
            self._worker.wait()
        self._worker = _ImaWorker(fn, args)
        self._worker.done.connect(handler)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _refresh_status(self):
        if not ima_client.is_configured():
            self._set_status(ima_client.config_hint(), warn=True)
        else:
            self._set_status("已配置 IMA 凭证，可以保存笔记。", ok=True)

    def _set_status(self, text, ok=False, warn=False):
        color = "#1a7f37" if ok else (_ACCENT if not warn else "#c0392b")
        self._status.setText(f'<span style="color:{color};">{text}</span>')

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.wait()
        super().closeEvent(event)
