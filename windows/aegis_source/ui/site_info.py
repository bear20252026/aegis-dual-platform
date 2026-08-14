# -*- coding: utf-8 -*-
"""site_info.py —— 站点信息 / 证书查看器（对标商业浏览器锁形详情）。

展示当前地址、连接安全性，以及（HTTPS 时）证书链：
颁发者、使用者、有效期、序列号、SHA-256 指纹。
颜色不硬编码，不依赖 emoji 图标。指纹用 hashlib 计算，跨版本稳定。
"""

import hashlib

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QFrame,
)
from PySide6.QtCore import Qt


def _fmt_fp(der: bytes) -> str:
    """把 DER 证书算成冒号分隔的大写 SHA-256 指纹。"""
    h = hashlib.sha256(der).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


class SiteInfo(QDialog):
    """站点信息与证书查看器。"""

    def __init__(self, ctx, tab, parent=None):
        super().__init__(parent)
        self.setWindowTitle("站点信息")
        self.resize(540, 480)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        url = tab.url() if tab else ""
        secure = url.startswith("https:")

        # 连接安全状态（用文字 + 系统配色，不硬编码颜色、不用 emoji）
        status = QLabel()
        status.setText("连接已加密（HTTPS）" if secure
                       else "连接未加密（HTTP 或其他协议）")
        status.setWordWrap(True)
        lay.addWidget(status)

        # 地址
        addr = QLabel(f"地址：{url or '(无)'}")
        addr.setWordWrap(True)
        addr.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(addr)

        lay.addWidget(self._hline())

        # 证书链
        chain = []
        try:
            if secure and tab and getattr(tab, "page", None):
                chain = tab.page.certificateChain() or []
        except Exception:
            chain = []

        if not chain:
            lay.addWidget(QLabel("无可用证书信息（HTTP 页面或未加载完成）。"))
            lay.addStretch(1)
            return

        idx = 0
        for cert in chain:
            try:
                der = bytes(cert.toDer())
            except Exception:
                continue
            info = QLabel()
            info.setWordWrap(True)
            info.setTextInteractionFlags(Qt.TextSelectableByMouse)
            try:
                eff = cert.effectiveDate().toString() if cert.effectiveDate() else "?"
                exp = cert.expiryDate().toString() if cert.expiryDate() else "?"
            except Exception:
                eff, exp = "?", "?"
            title = "服务器证书" if idx == 0 else f"中间证书 #{idx}"
            info.setText(
                f"{title}\n"
                f"有效期：{eff}  →  {exp}\n"
                f"SHA-256 指纹：{_fmt_fp(der)}")
            lay.addWidget(info)
            idx += 1

        lay.addWidget(self._hline())

        # 完整证书文本（可读性强，便于高级用户核对）
        detail = QPlainTextEdit(self)
        detail.setReadOnly(True)
        blob = "\n\n".join(
            c.toText() for c in chain if hasattr(c, "toText"))
        detail.setPlainText(blob or "（无文本详情）")
        detail.setMaximumHeight(220)
        lay.addWidget(QLabel("证书详情（完整）："))
        lay.addWidget(detail, 1)

    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line
