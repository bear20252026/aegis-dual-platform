# -*- coding: utf-8 -*-
"""vision_panel.py —— 模式 A：AI 视觉问答面板（设计文档 §6）。

发送当前标签页截图给视觉模型（本地 Ollama / 云端 OpenAI 兼容），
模型看图回答提问。网络请求在后台线程执行，经 QTimer 桥回主线程。

入口：工具菜单 →「视觉问答」/ 命令面板。
"""

import base64

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTextEdit,
)

from app.vision_client import capture_current_tab, describe_screen


class VisionPanel(QDialog):
    """视觉问答面板：截图预览 → 提问 → 视觉模型看图回答。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._win = window
        self.setWindowTitle("视觉问答")
        self.resize(560, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)

        lay.addWidget(QLabel("AI 视觉问答（截图发送给视觉模型）", self))

        # 截图预览
        self.preview = QLabel(self)
        self.preview.setFixedHeight(220)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet(
            "border:1px solid rgba(128,128,128,0.3);border-radius:12px;"
            "background:rgba(128,128,128,0.08);")
        lay.addWidget(self.preview)

        # 模型来源 + 刷新截图
        row = QHBoxLayout()
        row.addWidget(QLabel("模型来源", self))
        self.provider = QComboBox(self)
        self.provider.addItems(["本地 Ollama", "云端 OpenAI 兼容"])
        self.provider.setCurrentIndex(0)
        row.addWidget(self.provider, 1)
        btn_refresh = QPushButton("刷新截图", self)
        btn_refresh.clicked.connect(self._refresh_preview)
        row.addWidget(btn_refresh)
        lay.addLayout(row)

        # 提问
        self.question = QLineEdit(self)
        self.question.setPlaceholderText("问关于当前页面截图的问题…")
        self.question.returnPressed.connect(self._send)
        lay.addWidget(self.question)

        # 回答
        self.answer = QTextEdit(self)
        self.answer.setReadOnly(True)
        self.answer.setPlaceholderText("模型回答会显示在这里")
        lay.addWidget(self.answer, 1)

        # 底部按钮与状态
        btns = QHBoxLayout()
        self.lbl_state = QLabel("", self)
        btns.addWidget(self.lbl_state)
        btns.addStretch(1)
        self.btn_send = QPushButton("发送给 AI", self)
        self.btn_send.clicked.connect(self._send)
        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.accept)
        btns.addWidget(self.btn_send)
        btns.addWidget(btn_close)
        lay.addLayout(btns)

        self._data_uri = None
        self._refresh_preview()

    # ------------------------------------------------------------------ #
    def _refresh_preview(self):
        """抓取当前标签截图并显示预览（先让用户确认"发给 AI 的是什么"）。"""
        self.preview.clear()
        self.preview.setText("")
        t = self._win.current_tab()
        self._data_uri = capture_current_tab(t)
        if self._data_uri:
            try:
                b64 = self._data_uri.split(",", 1)[1]
                img = QImage.fromData(base64.b64decode(b64))
                pm = QPixmap.fromImage(img).scaledToWidth(
                    max(120, self.preview.width() - 40),
                    Qt.SmoothTransformation)
                self.preview.setPixmap(pm)
            except Exception:
                self.preview.setText("截图预览失败")
        else:
            self.preview.setText("无法截取当前页面（可能尚未渲染完成）")

    def _send(self):
        question = self.question.text().strip()
        if not question:
            self.question.setFocus()
            return
        if not self._data_uri:
            self._refresh_preview()
            if not self._data_uri:
                self.answer.setPlainText("没有可用截图，请刷新后重试。")
                return
        self.btn_send.setEnabled(False)
        self.lbl_state.setText("正在请求模型…")
        # 会话内切换来源（不写盘；持久配置走设置页）
        cfg = self._win.config
        cfg.vision_provider = ("cloud" if self.provider.currentIndex() == 1
                               else "ollama")
        data_uri, q = self._data_uri, question

        # v2.1.1 修复：跨线程回调必须经主线程投递桥（原 daemon 线程里
        # QTimer.singleShot 会因无事件循环而静默丢失，视觉问答实际失效）
        from app.qt_bridge import run_in_thread

        def _worker():
            return describe_screen(data_uri, q, cfg)

        def _on_main(payload):
            kind, value = payload
            if kind == "__error__":
                value = f"错误：{value}"
            self._on_reply(value)

        run_in_thread(_worker, _on_main)

    def _on_reply(self, reply):
        self.answer.setPlainText(reply)
        self.btn_send.setEnabled(True)
        self.lbl_state.setText("")
