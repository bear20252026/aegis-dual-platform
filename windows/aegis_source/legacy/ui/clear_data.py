"""clear_data.py —— 清除浏览数据对话框（对标商业浏览器隐私清理）。

细粒度选择：浏览历史 / Cookie 及其他站点数据 / 缓存 / 已保存密码。
每项独立勾选，执行后返回中文摘要。不触碰书签与设置（与商业浏览器一致）。
"""

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)


class ClearBrowsingData(QDialog):
    """清除浏览数据。"""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self._ctx = ctx
        self.setWindowTitle("清除浏览数据")
        self.resize(420, 300)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        tip = QLabel("选择要清除的内容（不影响书签与已保存的设置）：")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.chk_history = QCheckBox("浏览历史")
        self.chk_cookies = QCheckBox("Cookie 及其他站点数据")
        self.chk_cache = QCheckBox("缓存的图片和文件")
        self.chk_passwords = QCheckBox("已保存的密码")
        for c in (self.chk_history, self.chk_cookies,
                  self.chk_cache, self.chk_passwords):
            c.setChecked(True)
            lay.addWidget(c)

        if ctx.incognito:
            note = QLabel("当前为无痕模式：历史与 Cookie 本就不落盘，仅缓存可清。")
            note.setWordWrap(True)
            lay.addWidget(note)

        lay.addStretch(1)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        btns.button(QDialogButtonBox.Ok).setText("清除数据")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def apply(self) -> str:
        """按勾选执行清除，返回中文摘要。"""
        done = []
        if self.chk_history.isChecked():
            try:
                self._ctx.history.clear()
                done.append("浏览历史")
            except Exception:
                pass
        if self.chk_cookies.isChecked():
            try:
                self._ctx.profile.cookieStore().deleteAllCookies()
                done.append("Cookie")
            except Exception:
                pass
        if self.chk_cache.isChecked():
            try:
                self._ctx.profile.clearHttpCache()
                done.append("缓存")
            except Exception:
                pass
        if self.chk_passwords.isChecked():
            try:
                self._ctx.passwords.clear()
                done.append("已保存密码")
            except Exception:
                pass
        if not done:
            return "未选择任何项目，未做更改。"
        return "已清除：" + "、".join(done) + "。"
