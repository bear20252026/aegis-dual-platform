# -*- coding: utf-8 -*-
"""password_tools.py —— 密码生成器 + 本地泄露检测（对标商业浏览器的密码健康）。

- 生成：用 secrets 生成高强度密码，可配长度与字符集，显示熵估算。
- 泄露检测：HaveIBeenPwned k-匿名模型，仅发送 SHA-1 前 5 位，明文与完整哈希不出本机。

设计约束（项目 P0 绝对规则）：
- 不使用 emoji 图标；不硬编码颜色（沿用系统主题与强调色 #0071e3）。
"""

import string

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QTabWidget, QCheckBox, QSpinBox, QApplication, QMessageBox,
)

import app.password_tools as pw


class _BreachWorker(QThread):
    """后台泄露检测（网络请求不放主线程）。"""

    done = Signal(int, str)   # (count, status)

    def __init__(self, password):
        super().__init__()
        self._pwd = password

    def run(self):
        try:
            count, status = pw.check_breach(self._pwd)
            self.done.emit(count, status)
        except Exception as e:  # noqa: BLE001
            self.done.emit(-1, f"error:{e}")


class PasswordToolsDialog(QDialog):
    """密码工具对话框。"""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self._win = win
        self.setWindowTitle("密码工具")
        self.resize(520, 420)
        self._bworker = None

        tabs = QTabWidget(self)
        tabs.addTab(self._build_generate(), "生成")
        tabs.addTab(self._build_breach(), "泄露检测")

        lay = QVBoxLayout(self)
        lay.addWidget(tabs)

    # ------------------------------------------------------------------ #
    # 生成
    # ------------------------------------------------------------------ #
    def _build_generate(self):
        w = QDialog(self)
        v = QVBoxLayout(w)

        opt = QHBoxLayout()
        self._len = QSpinBox(self)
        self._len.setRange(6, 64)
        self._len.setValue(16)
        opt.addWidget(QLabel("长度"))
        opt.addWidget(self._len)
        opt.addStretch(1)
        self._c_up = QCheckBox("大写", self); self._c_up.setChecked(True)
        self._c_lo = QCheckBox("小写", self); self._c_lo.setChecked(True)
        self._c_di = QCheckBox("数字", self); self._c_di.setChecked(True)
        self._c_sy = QCheckBox("符号", self); self._c_sy.setChecked(True)
        for c in (self._c_up, self._c_lo, self._c_di, self._c_sy):
            opt.addWidget(c)
        v.addLayout(opt)

        self._gen_out = QLineEdit(self)
        self._gen_out.setReadOnly(True)
        self._gen_out.setPlaceholderText("点击「生成」创建强密码")
        v.addWidget(self._gen_out)

        self._strength = QLabel("", self)
        v.addWidget(self._strength)

        r = QHBoxLayout()
        self._btn_gen = QPushButton("生成")
        self._btn_copy = QPushButton("复制")
        self._btn_copy.setEnabled(False)
        self._btn_gen.clicked.connect(self._generate)
        self._btn_copy.clicked.connect(self._copy_pwd)
        r.addWidget(self._btn_gen)
        r.addWidget(self._btn_copy)
        r.addStretch(1)
        v.addLayout(r)
        v.addStretch(1)
        return w

    def _generate(self):
        length = self._len.value()
        pwd = pw.generate(
            length=length,
            use_upper=self._c_up.isChecked(),
            use_lower=self._c_lo.isChecked(),
            use_digits=self._c_di.isChecked(),
            use_symbols=self._c_sy.isChecked(),
        )
        self._gen_out.setText(pwd)
        self._btn_copy.setEnabled(True)
        # 熵估算
        pool = 0
        if self._c_up.isChecked():
            pool += len(string.ascii_uppercase)
        if self._c_lo.isChecked():
            pool += len(string.ascii_lowercase)
        if self._c_di.isChecked():
            pool += len(string.digits)
        if self._c_sy.isChecked():
            pool += len(pw._SYMBOLS)
        bits = pw.entropy_bits(length, pool or 1)
        self._strength.setText(
            f"强度：{pw.strength_label(bits)}（约 {bits} bits 熵）")

    def _copy_pwd(self):
        QApplication.clipboard().setText(self._gen_out.text())
        QMessageBox.information(self, "已复制", "密码已复制到剪贴板。")

    # ------------------------------------------------------------------ #
    # 泄露检测
    # ------------------------------------------------------------------ #
    def _build_breach(self):
        w = QDialog(self)
        v = QVBoxLayout(w)

        v.addWidget(QLabel("输入密码进行检测（不会离开本机，仅发送哈希前缀）："))
        self._pwd_in = QLineEdit(self)
        self._pwd_in.setEchoMode(QLineEdit.Password)
        v.addWidget(self._pwd_in)

        r = QHBoxLayout()
        self._btn_check = QPushButton("检测是否泄露")
        self._btn_check.clicked.connect(self._check)
        r.addWidget(self._btn_check)
        r.addStretch(1)
        v.addLayout(r)

        self._breach_out = QLabel("", self)
        self._breach_out.setWordWrap(True)
        v.addWidget(self._breach_out)
        v.addStretch(1)

        note = QLabel(
            "采用 HaveIBeenPwned k-匿名模型：仅把密码 SHA-1 的前 5 位发送到服务端，"
            "比对本地完成，明文与完整哈希绝不外传。无需 API Key。", self)
        note.setWordWrap(True)
        v.addWidget(note)
        return w

    def _check(self):
        pwd = self._pwd_in.text()
        if not pwd:
            return
        self._btn_check.setEnabled(False)
        self._breach_out.setText("正在检测（仅发送哈希前缀）…")
        self._bworker = _BreachWorker(pwd)
        self._bworker.done.connect(self._on_breach)
        self._bworker.start()

    def _on_breach(self, count, status):
        self._btn_check.setEnabled(True)
        if status == "error" or count < 0:
            self._breach_out.setText(
                "检测失败：网络请求出错，无法判定。请检查网络连接后重试。")
            return
        if count > 0:
            self._breach_out.setText(
                f"警告：该密码已在公开泄露库中出现 {count} 次，"
                "强烈建议立即更换。")
        else:
            self._breach_out.setText(
                "未命中公开泄露库（基于 k-匿名前缀查询）。"
                "但仍建议使用上方生成器创建唯一强密码。")
