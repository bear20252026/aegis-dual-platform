# -*- coding: utf-8 -*-
"""computer_use_panel.py —— 模式 B：AI 上网代理面板（设计文档 §7）。

截图 → 视觉模型决策（JSON 动作）→ GATE 等级门控 → 页面执行 → 循环，
直到 done/fail/步数上限/用户停止。

- 等级选择 L0~L3，会话开始后锁定（§13.3）
- L3：AI 尝试输入密码框被拦截后，自动走密码库直填（§13.4，
  密码明文只在进程内流转，不进模型上下文）
- 无进展检测（§7.5）：连续 3 步画面指纹不变则暂停
"""

import base64
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QPlainTextEdit, QFrame, QMessageBox,
)

from app.vision_client import (capture_current_tab, decide_action,
                               NATIVE_ACTIONS)
from app.computer_use import (check_level, PageActor, GateError,
                              screen_fingerprint)

LEVEL_NAMES = ["L0 只读", "L1 浏览", "L2 输入", "L3 凭据"]


class ComputerUsePanel(QDialog):
    """AI 上网代理面板（模式 B 闭环）。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._win = window
        self.setWindowTitle("AI 上网代理")
        self.resize(620, 700)
        self._running = False
        self._step = 0
        self._stop = False
        self._no_progress = 0
        self._last_fp = ""
        self._level = 1
        # L3 会话已访问的凭据域名（§13.5：vision_l3_max_sites 限额）
        self._l3_sites = set()
        # R8：原生动作预算与同坐标点击熔断
        self._native_count = 0
        self._click_repeat = 0
        self._last_click_xy = None

        self._build()
        self._log("就绪：填写任务并选择等级后开始（L1 即可自由浏览）。")

    # ------------------------------------------------------------------ #
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("任务", self))
        self.task_edit = QLineEdit(self)
        self.task_edit.setPlaceholderText(
            "如：打开百度搜索 Python，点进第一篇文章看看")
        row.addWidget(self.task_edit, 1)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("等级", self))
        self.level_box = QComboBox(self)
        self.level_box.addItems(LEVEL_NAMES)
        row2.addWidget(self.level_box)
        self.btn_start = QPushButton("开始", self)
        self.btn_start.clicked.connect(self._toggle)
        self.btn_stop = QPushButton("停止", self)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._request_stop)
        row2.addWidget(self.btn_start)
        row2.addWidget(self.btn_stop)
        self.lbl_state = QLabel("未开始", self)
        row2.addWidget(self.lbl_state, 1)
        lay.addLayout(row2)

        # 人工介入区（§14）：扫码 / 短信验证码介入
        self.hint = QFrame(self)
        self.hint.setStyleSheet(
            "background:rgba(255,159,10,0.12);border-radius:10px;")
        hint_lay = QHBoxLayout(self.hint)
        hint_lay.setContentsMargins(10, 6, 10, 6)
        self.hint_lbl = QLabel("", self)
        hint_lay.addWidget(self.hint_lbl, 1)
        self.sms_edit = QLineEdit(self.hint)
        self.sms_edit.setPlaceholderText("输入短信验证码")
        self.sms_edit.setVisible(False)
        hint_lay.addWidget(self.sms_edit)
        self.sms_btn = QPushButton("提交", self.hint)
        self.sms_btn.setVisible(False)
        self.sms_btn.clicked.connect(self._sms_submit)
        hint_lay.addWidget(self.sms_btn)
        self.hint_btn = QPushButton("我已扫码，继续", self.hint)
        self.hint_btn.setVisible(False)
        self.hint_btn.clicked.connect(self._human_done)
        hint_lay.addWidget(self.hint_btn)
        self.hint.setVisible(False)
        lay.addWidget(self.hint)

        self.preview = QLabel(self)
        self.preview.setFixedHeight(200)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet(
            "border:1px solid rgba(128,128,128,0.3);border-radius:12px;"
            "background:rgba(128,128,128,0.08);")
        lay.addWidget(self.preview)

        self.log = QPlainTextEdit(self)
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        lay.addWidget(self.log, 1)

        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self._on_close)
        lay.addWidget(btn_close, 0, Qt.AlignRight)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._step_once)

    # ------------------------------------------------------------------ #
    def _toggle(self):
        if self._running:
            self._request_stop()
            return
        task = self.task_edit.text().strip()
        if not task:
            self._log("请先填写任务描述。")
            return
        self._level = self.level_box.currentIndex()
        # v2.1.2 修复：会话前确认受设置 vision_l3_confirm 控制，
        # 此前该配置项完全未被读取（默认 True 时行为不变）。
        if self._level >= 3 and getattr(self._win.config,
                                        "vision_l3_confirm", True):
            ret = QMessageBox.question(
                self, "L3 权限确认",
                "L3 将允许 AI 在检测到登录页时读取密码库自动填充。\n"
                "密码明文不会发送给 AI 或云端模型。是否继续？")
            if ret != QMessageBox.Yes:
                self._log("已取消 L3 会话。")
                return
        self._running = True
        self._stop = False
        self._step = 0
        self._no_progress = 0
        self._last_fp = ""
        self._l3_sites = set()   # 新会话重置凭据域名计数
        self._native_count = 0   # R8：重置原生动作预算
        self._click_repeat = 0   # R8：重置点击熔断
        self._last_click_xy = None
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.level_box.setEnabled(False)   # 会话中锁定等级（§13.3）
        self._log(f"会话开始（等级 L{self._level}）：{task}")
        self._timer.start(50)

    def _request_stop(self):
        self._stop = True
        self._log("正在停止…")

    # ------------------------------------------------------------------ #
    # 人工介入（§14）：扫码 / 短信验证码（AI 不扫码、不猜验证码，人介入）
    # ------------------------------------------------------------------ #
    def _enter_human(self, kind, text):
        self._human_state = kind
        self.hint.setVisible(True)
        self.hint_lbl.setText(text)
        self.sms_edit.setVisible(kind == "sms")
        self.sms_btn.setVisible(kind == "sms")
        self.hint_btn.setVisible(kind == "qr")
        if kind == "qr":
            self.hint_btn.setText("我已扫码，继续")
        self.lbl_state.setText("等待人工介入…")
        self._log(f"[人工介入] {text}")

    def _human_done(self):
        """扫码完成 / 验证码已提交：结束介入，恢复循环。"""
        self._human_state = None
        self.hint.setVisible(False)
        self.sms_edit.clear()
        self._schedule_next()

    def _sms_submit(self):
        code = self.sms_edit.text().strip()
        if not code:
            return
        t = self._win.current_tab()
        if t is None:
            self._human_done()
            return
        self._log(f"提交短信验证码（{len(code)} 位，明文不进 AI 上下文）")
        actor = PageActor(t.page)
        actor.act({"action": "sms_fill", "code": code},
                  on_done=lambda ok, msg: self._on_acted(ok, msg))
        self._human_done()

    def _on_close(self):
        self._stop = True
        self.accept()

    # ------------------------------------------------------------------ #
    # 状态机（§7.1）：CAPTURE → DECIDE → GATE → ACT → 循环
    # ------------------------------------------------------------------ #
    def _step_once(self):
        if not self._running or self._stop:
            self._finish_run()
            return
        limit = getattr(self._win.config, "vision_step_limit", 50)
        if self._step >= limit:
            self._log(f"已达步数上限（{limit}），结束会话。")
            self._finish_run()
            return
        self._step += 1
        self.lbl_state.setText(f"第 {self._step} 步：截图")
        t = self._win.current_tab()
        data_uri = capture_current_tab(t)
        if not data_uri:
            self._log("截图失败，稍后重试…")
            self._timer.start(1000)
            return
        self._show_preview(data_uri)
        # 无进展检测（§7.5）
        fp = screen_fingerprint(data_uri)
        if fp and fp == self._last_fp:
            self._no_progress += 1
            if self._no_progress >= 3:
                self._log("画面连续 3 步无变化，可能陷入循环，已暂停。")
                self._finish_run()
                return
        else:
            self._no_progress = 0
        self._last_fp = fp

        task = self.task_edit.text().strip()
        cfg = self._win.config
        step = self._step
        # §7.5：单步超时记录（决策线程不可强杀，靠模型端 timeout 兜底）
        self._decide_start = time.time()
        self.lbl_state.setText(f"第 {self._step} 步：AI 决策中…")

        # v2.1.1 修复：跨线程回调经 qt_bridge 主线程桥（原 daemon 线程里
        # QTimer.singleShot 静默丢失，AI 代理闭环实际失效）
        from app.qt_bridge import run_in_thread

        def _worker():
            try:
                return decide_action(data_uri, task, step, cfg)
            except Exception as e:
                # VisionError 亦为 Exception 子类，统一兜底
                return {"action": "fail", "reason": str(e)}

        run_in_thread(_worker, lambda payload: self._on_decided(payload[1]))

    def _on_decided(self, action):
        if not self._running or self._stop:
            self._finish_run()
            return
        # §7.5：单步超时提示（超过 vision_step_timeout 的决策仍继续处理）
        timeout = getattr(self._win.config, "vision_step_timeout", 30.0)
        if (time.time() - getattr(self, "_decide_start", time.time())
                > timeout):
            self._log(f"第 {self._step} 步决策超过 {timeout:.0f}s，"
                      f"已按超时处理")
        name = action.get("action", "")
        try:
            check_level(action, self._level)     # GATE（§13.3）
        except GateError as e:
            self._log(f"[拦截] {e}")
            self._finish_run()
            return
        reason = action.get("reason", "")
        self._log(f"#{self._step} 决策：{name}" + (f"（{reason}）" if reason else ""))
        # R8：同坐标连续点击熔断（±8px 内 ≥3 次暂停，防循环/注入诱导）
        if name == "click":
            xy = (action.get("x", 0), action.get("y", 0))
            if self._last_click_xy is not None:
                dx = abs(xy[0] - self._last_click_xy[0])
                dy = abs(xy[1] - self._last_click_xy[1])
                self._click_repeat = (self._click_repeat + 1
                                      if dx <= 8 and dy <= 8 else 0)
            else:
                self._click_repeat = 0
            self._last_click_xy = xy
            if self._click_repeat >= 3:
                self._log("同一区域连续点击 3 次，疑似循环/注入诱导，已熔断暂停")
                self._finish_run()
                return
        if name == "done":
            self._log(f"完成：{action.get('summary', '')}")
            self._finish_run()
            return
        if name == "fail":
            self._log(f"失败：{action.get('reason', '')}")
            self._finish_run()
            return
        # 人工介入请求（§14）：暂停循环，等待用户扫码 / 输入验证码
        if name == "qrcode":
            self._enter_human(
                "qr",
                "检测到扫码登录：请用手机扫码，完成后点“我已扫码，继续”。")
            return
        if name == "sms_input":
            self._enter_human(
                "sms", "检测到短信验证码：请输入手机收到的验证码。")
            return
        if name == "wait":
            ms = max(100, min(10000, int(action.get("ms", 500))))
            self.lbl_state.setText(f"等待 {ms}ms")
            self._timer.start(ms)
            return
        if name in NATIVE_ACTIONS:
            # 浏览器原生动作（§7.7）：Python 侧执行，不走页面 JS
            self._exec_native(action)
            return
        self._act(action)

    # ------------------------------------------------------------------ #
    # 浏览器原生动作（§7.7）：切换引擎/加书签/新标签/历史/设置
    # ------------------------------------------------------------------ #
    def _exec_native(self, action):
        name = action.get("action")
        # R8：原生动作单会话预算熔断（默认 10 次），防注入诱导反复触发
        budget = getattr(self._win.config, "vision_native_budget", 10)
        if self._native_count >= budget:
            self._log(f"原生动作已达预算上限（{budget} 次），已暂停")
            self._finish_run()
            return
        self._native_count += 1
        ctx = self._win.ctx
        try:
            if name == "set_engine":
                engine = str(action.get("engine", "")).strip()
                if engine in ("baidu", "bing", "sogou", "google",
                              "github", "zhihu"):
                    ctx.config.engine = engine
                    ctx.save_config()
                    self._log(f"已切换搜索引擎：{engine}")
                else:
                    self._log(f"未知搜索引擎：{engine}")
            elif name == "add_bookmark":
                url = str(action.get("url", "")).strip()
                title = str(action.get("title", "") or url)
                if ctx.bookmarks.add(title, url):
                    try:
                        self._win._rebuild_bookmark_bar()
                    except Exception:
                        pass
                    self._log(f"已添加书签：{title}")
                else:
                    self._log("书签已存在或地址无效")
            elif name == "new_tab":
                url = str(action.get("url", "")).strip()
                if url:
                    self._win.open_new_tab(url)
                    self._log(f"新标签：{url}")
            elif name == "open_history":
                self._log("打开历史记录…")
                self._win._open_history()
            elif name == "open_settings":
                self._log("打开设置…")
                self._win._open_settings()
        except Exception as e:
            self._log(f"原生动作失败：{e}")
        self._schedule_next()

    def _act(self, action):
        t = self._win.current_tab()
        if t is None:
            self._finish_run()
            return
        actor = PageActor(t.page)
        actor.sync_dpr()
        self.lbl_state.setText(
            f"第 {self._step} 步：执行 {action.get('action')}")
        actor.act(action, on_done=self._on_acted)

    def _on_acted(self, ok, msg):
        self._log(f"  → {'✓' if ok else '✗'} {msg}")
        # AI 尝试输入密码框被拦截（password-field）：L3 时面板接管直填
        if msg == "password-field" and self._level >= 3:
            self._auto_login_fill()
            return
        self._schedule_next()

    # ------------------------------------------------------------------ #
    # 密码库直填（§13.4）
    # ------------------------------------------------------------------ #
    def _auto_login_fill(self):
        t = self._win.current_tab()
        if t is None:
            self._schedule_next()
            return
        host = ""
        try:
            from urllib.parse import urlparse
            host = urlparse(t.url()).hostname or ""
        except Exception:
            host = ""
        # §13.5：L3 凭据访问域名限额（防模型扫库）
        if host:
            max_sites = getattr(self._win.config, "vision_l3_max_sites", 3)
            if host not in self._l3_sites and len(self._l3_sites) >= max_sites:
                self._log(f"L3 凭据访问已达上限（{max_sites} 个域名），"
                          f"拒绝填充 {host}")
                self._schedule_next()
                return
            self._l3_sites.add(host)
        cred = None
        if host:
            # v2.1.2 修复：按归一化 eTLD+1（R9）匹配凭据——旧的
            # `scheme+host` 精确匹配对带路径的存储 URL 几乎必然失配。
            try:
                cred = self._win.ctx.passwords.find_for_host(host)
            except Exception:
                cred = None
        if not cred:
            self._log("检测到登录页，但密码库无该站点凭据（跳过）。")
            self._schedule_next()
            return
        _url, username, password = cred
        self._log(f"密码库直填：{host}（明文不进 AI 上下文）")
        # R7：L3 凭据访问审计（记录域名与决策）
        try:
            from app.security_audit import audit
            audit(getattr(self._win.ctx, "data_dir", ""),
                  "l3_credential_access", host, "filled")
        except Exception:
            pass
        action = {"action": "login_fill", "username": username,
                  "password": password}
        actor = PageActor(t.page)
        actor.act(action, on_done=lambda ok, msg: self._on_acted(ok, msg))

    def _schedule_next(self):
        if not self._running or self._stop:
            self._finish_run()
            return
        ms = max(500, min(10000,
                          getattr(self._win.config, "vision_interval_ms", 2500)))
        self._timer.start(ms)

    def _finish_run(self):
        self._running = False
        self._timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.level_box.setEnabled(True)
        self.hint.setVisible(False)
        self.lbl_state.setText("已结束")
        self._log("会话结束。")

    # ------------------------------------------------------------------ #
    def _show_preview(self, data_uri):
        try:
            raw = base64.b64decode(data_uri.split(",", 1)[1])
            img = QImage.fromData(raw)
            pm = QPixmap.fromImage(img).scaledToWidth(
                max(120, self.preview.width() - 30), Qt.SmoothTransformation)
            self.preview.setPixmap(pm)
        except Exception:
            pass

    def _log(self, text):
        self.log.appendPlainText(text)
        # §9.2：动作日志同时写入文件日志（隐私字段不上行）
        try:
            logger = getattr(self._win.ctx, "logger", None)
            if logger is not None:
                logger.info(f"[vision] {text}")
        except Exception:
            pass
