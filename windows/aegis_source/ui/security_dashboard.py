# -*- coding: utf-8 -*-
"""security_dashboard.py —— 安全态势仪表盘（超越项：让用户看见"被保护到了什么程度"）。

商业级浏览器往往把安全能力藏在角落，用户无法直观判断自己是否真的被保护。
Aegis 的安全仪表盘如实汇总所有防护开关的真实状态，并诚实标注覆盖度局限
（例如安全浏览若只有种子名单，会明确提示"建议接入真实情报源"）。

设计原则：
- 只读聚合，不修改任何配置；
- 每一项都标注"已启用 / 未启用"，不夸大、不隐瞒局限；
- 颜色仅用语义色（绿=生效，黄=有限，红=关闭/风险），不靠 emoji。
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QScrollArea,
    QFrame, QSizePolicy,
)

from app.version import APP_NAME, APP_VERSION, engine_version, pyside_version
from app.hsts import preload_count


# 语义色（遵循项目唯一强调色体系，不引入紫粉渐变）
_C_GOOD = "#30d158"     # 生效
_C_WARN = "#ff9f0a"     # 有限/需注意
_C_BAD = "#ff453a"      # 关闭/风险
_C_LINE = "rgba(128,128,128,0.18)"
_C_FG = "#1d1d1f"
_C_FG_D = "#ffffff"


class _Row(QWidget):
    """一行：左侧图标圆点 + 标题 + 状态文字 + 说明。"""

    def __init__(self, title: str, state: str, detail: str,
                 color: str, dark: bool, parent=None):
        super().__init__(parent)
        self._dark = dark
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(12)

        dot = QLabel(self)
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(
            f"border-radius:5px;background:{color};"
            f"border:1px solid {color};")
        lay.addWidget(dot)

        text = QVBoxLayout()
        text.setSpacing(2)
        fg = _C_FG_D if dark else _C_FG
        t = QLabel(f"<b>{title}</b>", self)
        t.setStyleSheet(f"color:{fg};font-size:14px;")
        s = QLabel(f"<span style='color:{color};font-weight:600;'>{state}</span>"
                   f"  <span style='color:{'rgba(255,255,255,.55)' if dark else 'rgba(0,0,0,.5)'};'>{detail}</span>",
                   self)
        s.setWordWrap(True)
        s.setStyleSheet(f"font-size:12px;")
        text.addWidget(t)
        text.addWidget(s)
        lay.addLayout(text, 1)


class SecurityDashboard(QDialog):
    """安全态势总览对话框。"""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} 安全仪表盘")
        self.resize(640, 640)
        self.setMinimumSize(560, 520)
        from app.system_theme import resolve_dark
        self._dark = resolve_dark(ctx.config.theme)
        self._build()

    # ------------------------------------------------------------------ #
    def _build(self):
        root = QWidget(self)
        v = QVBoxLayout(root)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(14)

        # ---- 顶部：应用信息条 ----
        info = QLabel(self)
        info.setWordWrap(True)
        fg = _C_FG_D if self._dark else _C_FG
        info.setText(
            f"<b style='font-size:16px;'>{APP_NAME} v{APP_VERSION}</b><br>"
            f"<span style='color:{'rgba(255,255,255,.6)' if self._dark else 'rgba(0,0,0,.55)'};font-size:12px;'>"
            f"引擎：{engine_version()} · 运行时：PySide6 {pyside_version()}</span>")
        info.setStyleSheet(f"color:{fg};")
        v.addWidget(info)

        # ---- 滚动区：分组卡片 ----
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget(self)
        bv = QVBoxLayout(body)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(12)

        bv.addWidget(self._card("恶意/钓鱼防护", self._sb_rows()))
        bv.addWidget(self._card("自动更新（信任链）", self._upd_rows()))
        bv.addWidget(self._card("传输与隐私", self._net_rows()))
        bv.addWidget(self._card("站点权限与凭据", self._perm_rows()))

        scroll.setWidget(body)
        v.addWidget(scroll, 1)

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(root)

    # ------------------------------------------------------------------ #
    def _card(self, title: str, rows: list) -> QWidget:
        fg = _C_FG_D if self._dark else _C_FG
        card = QWidget(self)
        card.setStyleSheet(
            f"background:{'rgba(255,255,255,.04)' if self._dark else 'rgba(0,0,0,.03)'};"
            f"border:1px solid {_C_LINE};border-radius:12px;")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 6)
        cl.setSpacing(0)
        head = QLabel(f"  {title}", self)
        head.setContentsMargins(12, 10, 12, 8)
        head.setStyleSheet(f"color:{fg};font-weight:600;font-size:13px;"
                           f"text-transform:uppercase;letter-spacing:.5px;")
        cl.addWidget(head)
        for r in rows:
            cl.addWidget(r)
        return card

    # ------------------------------------------------------------------ #
    def _sb_rows(self):
        st = self.ctx.safe_browsing.status()
        rows = []
        if st["active"]:
            color = _C_GOOD if st["sources"] != ["local-seed"] else _C_WARN
            rows.append(_Row(
                "安全浏览", "已启用",
                "来源：" + ", ".join(st["sources"]), color, self._dark))
            rows.append(_Row(
                "覆盖度说明", "诚实声明",
                st["note"], _C_WARN if "仅" in st["note"] else _C_GOOD,
                self._dark))
        else:
            rows.append(_Row("安全浏览", "已关闭", st["note"], _C_BAD, self._dark))
        # 拦截统计
        hits = getattr(self.ctx.safe_browsing, "hits", 0)
        rows.append(_Row("累计拦截", f"{hits} 次",
                         "本会话内被安全浏览阻止的访问", _C_FG_D if self._dark else _C_FG,
                         self._dark))
        return rows

    def _upd_rows(self):
        cfg = self.ctx.config
        rows = []
        enabled = self.ctx.updater.enabled()
        if enabled:
            rows.append(_Row("更新通道", "已配置",
                             "已强制 HTTPS + Ed25519 离线签名验签", _C_GOOD,
                             self._dark))
            pin = getattr(cfg, "update_pinned_cert_sha256", "") or ""
            rows.append(_Row(
                "证书锁定", "已启用" if pin else "未设置",
                "对更新服务器证书做 SHA-256 锁定（防中间人）" if pin
                else "建议配置 update_pinned_cert_sha256 进一步提升安全性",
                _C_GOOD if pin else _C_WARN, self._dark))
        else:
            rows.append(_Row(
                "更新通道", "未配置",
                "未设置 update_url：不自动更新，需手动安装新版", _C_WARN,
                self._dark))
        rows.append(_Row(
            "安装包校验", "强制",
            "下载后必须 SHA-256 匹配且 manifest 签名有效才可安装", _C_GOOD,
            self._dark))
        return rows

    def _net_rows(self):
        cfg = self.ctx.config
        rows = []
        pc = preload_count(self.ctx.data_dir)
        rows.append(_Row(
            "HSTS 预加载", f"{pc['total']} 个主机",
            f"内置 {pc['seed']} 条种子" + (f" + 用户 {pc['extra']} 条" if pc['extra'] else "")
            + "；命中即 http→https 强升级，证书错误不可绕过",
            _C_GOOD, self._dark))
        rows.append(_Row(
            "WebRTC IP 防泄漏", "已启用" if cfg.webrtc_ip_leak_protection else "已关闭",
            "限制 WebRTC 仅暴露公网接口，降低真实内网 IP 暴露风险",
            _C_GOOD if cfg.webrtc_ip_leak_protection else _C_BAD, self._dark))
        rows.append(_Row(
            "广告拦截", "已启用" if cfg.adblock else "已关闭",
            "拦截跟踪与广告请求（无痕模式亦生效）",
            _C_GOOD if cfg.adblock else _C_BAD, self._dark))
        rows.append(_Row(
            "Do Not Track", "已启用" if cfg.do_not_track else "已关闭",
            "向站点发送 DNT 请求头",
            _C_GOOD if cfg.do_not_track else _C_WARN, self._dark))
        rows.append(_Row(
            "下载隔离", "已启用",
            "可执行/脚本类下载需二次确认，绝不自动运行", _C_GOOD, self._dark))
        return rows

    def _perm_rows(self):
        from app.password_store import password_security_note
        rows = []
        sites = self.ctx.permissions.all_sites()
        allow = deny = 0
        for _host, feats in sites:
            for _f, dec in feats:
                if dec == "allow":
                    allow += 1
                elif dec == "deny":
                    deny += 1
        rows.append(_Row(
            "站点权限", f"{len(sites)} 个站点",
            f"允许 {allow} · 拒绝 {deny}（摄像头/麦克风/位置/通知）",
            _C_GOOD if not sites else _C_WARN, self._dark))
        note = password_security_note()
        active = "可用" in note and "禁用" not in note
        rows.append(_Row(
            "密码存储", "已加密可用" if active else "不可用",
            note, _C_GOOD if active else _C_BAD, self._dark))
        return rows
