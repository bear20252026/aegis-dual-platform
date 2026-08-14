# -*- coding: utf-8 -*-
"""settings_dialog.py —— 设置对话框。

所有设置项均写回 AppConfig 并立即/重启生效，非"摆设"。
"""

import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel,
    QComboBox, QCheckBox, QSpinBox, QPushButton, QGroupBox, QFormLayout,
    QLineEdit, QFileDialog, QDialogButtonBox, QMessageBox, QListWidget,
    QListWidgetItem,
)

from app.password_store import password_security_note
from app.permissions import FEATURE_NAMES
from app.i18n import tr

# U-8：高频对话框统一的"呼吸感"——外边距、分区间距与控件高度
DIALOG_MARGINS = (20, 18, 20, 16)
GROUP_SPACING = 16
CONTROL_HEIGHT = 30


def section_label(text: str, parent=None) -> QLabel:
    """分区标题：仅做字重区分，颜色沿用主题 QSS（不引入硬编码色）。"""
    lbl = QLabel(text, parent)
    font = lbl.font()
    font.setBold(True)
    lbl.setFont(font)
    return lbl


def tune_form(form: QFormLayout) -> QFormLayout:
    """统一表单的行距与标签对齐。"""
    form.setHorizontalSpacing(16)
    form.setVerticalSpacing(12)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
    return form


def unify_control_heights(root, height: int = CONTROL_HEIGHT):
    """把对话框内的输入类控件统一到同一高度，避免参差。"""
    for cls in (QComboBox, QSpinBox, QLineEdit, QPushButton):
        for w in root.findChildren(cls):
            w.setMinimumHeight(height)


class SettingsDialog(QDialog):
    """设置对话框：外观 / 启动 / 隐私 / 性能 / 网络 / 下载。"""

    def __init__(self, config, parent=None, perm_store=None):
        super().__init__(parent)
        self.config = config
        self._perm_store = perm_store
        self.setWindowTitle("设置")
        self.resize(640, 560)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(*DIALOG_MARGINS)
        root.setSpacing(GROUP_SPACING)
        self.tabs = QTabWidget(self)
        root.addWidget(self.tabs, 1)

        self.tabs.addTab(self._tab_appearance(), tr("外观"))
        self.tabs.addTab(self._tab_startup(), tr("启动"))
        self.tabs.addTab(self._tab_privacy(), tr("隐私与安全"))
        self.tabs.addTab(self._tab_performance(), tr("性能"))
        self.tabs.addTab(self._tab_network(), tr("网络"))
        self.tabs.addTab(self._tab_download(), tr("下载"))
        self.tabs.addTab(self._tab_sync(), tr("同步"))
        self.tabs.addTab(self._tab_ai(), tr("AI"))

        btns = QDialogButtonBox(QDialogButtonBox.Save
                                | QDialogButtonBox.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        unify_control_heights(self)

    # ------------------------------------------------------------------ #
    def _tab_sync(self):
        """云同步（WebDAV）：地址/用户名写入配置；token/密码走凭证文件。"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(*DIALOG_MARGINS)
        form = QFormLayout()
        tune_form(form)
        self.edit_sync_url = QLineEdit(self.config.sync_webdav_url)
        self.edit_sync_url.setPlaceholderText("https://dav.example.com/aegis/sync.absync")
        form.addRow("WebDAV 地址", self.edit_sync_url)
        self.edit_sync_user = QLineEdit(self.config.sync_webdav_user)
        self.edit_sync_user.setPlaceholderText("（可留空）")
        form.addRow("WebDAV 用户名", self.edit_sync_user)
        lay.addLayout(form)
        note = QLabel(
            "凭证（token 或密码）不入配置，避免明文落盘：\n"
            "· 环境变量 AEGIS_WEBDAV_TOKEN 或 AEGIS_WEBDAV_PASSWORD\n"
            "· 或写入 ~/.config/aegis/sync.key（一行：token:xxx / password:xxx）\n"
            "地址强制 HTTPS。", w)
        note.setWordWrap(True)
        note.setStyleSheet("color:rgba(128,128,128,0.85);")
        lay.addWidget(note)
        lay.addStretch(1)
        # 输入即写回 config（点保存后由主窗口持久化）
        self.edit_sync_url.textChanged.connect(
            lambda t: setattr(self.config, "sync_webdav_url", t.strip()))
        self.edit_sync_user.textChanged.connect(
            lambda t: setattr(self.config, "sync_webdav_user", t.strip()))
        return w

    # ------------------------------------------------------------------ #
    def _tab_ai(self):
        """AI 视觉能力配置（设计文档 §3）：开关/来源/端点/模型/参数/等级。"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(*DIALOG_MARGINS)
        form = QFormLayout()
        tune_form(form)
        self.chk_vision = QCheckBox("启用 AI 视觉能力（视觉问答 / AI 上网代理）")
        self.chk_vision.setChecked(self.config.vision_enabled)
        form.addRow("", self.chk_vision)
        self.cmb_vision_provider = QComboBox()
        self.cmb_vision_provider.addItems(["本地 Ollama", "云端 OpenAI 兼容"])
        self.cmb_vision_provider.setCurrentIndex(
            1 if self.config.vision_provider in ("cloud", "custom") else 0)
        form.addRow("模型来源", self.cmb_vision_provider)
        self.edit_vision_endpoint = QLineEdit(self.config.vision_endpoint)
        self.edit_vision_endpoint.setPlaceholderText(
            "http://localhost:11434/v1/chat/completions")
        form.addRow("视觉端点", self.edit_vision_endpoint)
        self.edit_vision_model = QLineEdit(self.config.vision_model)
        self.edit_vision_model.setPlaceholderText(
            "本地: qwen2.5-vl:7b / 云端: gpt-4o / qwen-vl-max")
        form.addRow("视觉模型", self.edit_vision_model)
        self.sp_vision_width = QSpinBox()
        self.sp_vision_width.setRange(320, 2560)
        self.sp_vision_width.setValue(self.config.vision_max_image_width)
        form.addRow("截图最长边", self.sp_vision_width)
        self.sp_vision_quality = QSpinBox()
        self.sp_vision_quality.setRange(40, 95)
        self.sp_vision_quality.setValue(self.config.vision_jpeg_quality)
        form.addRow("截图质量", self.sp_vision_quality)
        self.sp_vision_step = QSpinBox()
        self.sp_vision_step.setRange(1, 500)
        self.sp_vision_step.setValue(self.config.vision_step_limit)
        form.addRow("最大步数", self.sp_vision_step)
        self.cmb_vision_level = QComboBox()
        self.cmb_vision_level.addItems(
            ["L0 只读", "L1 浏览", "L2 输入", "L3 凭据"])
        self.cmb_vision_level.setCurrentIndex(
            max(0, min(3, self.config.vision_permission_level)))
        form.addRow("默认等级", self.cmb_vision_level)
        self.chk_vision_l3 = QCheckBox("L3 会话开始前确认（凭据访问）")
        self.chk_vision_l3.setChecked(self.config.vision_l3_confirm)
        form.addRow("", self.chk_vision_l3)
        lay.addLayout(form)
        note = QLabel(
            "云端密钥：环境变量 VISION_API_KEY 或 ~/.config/aegis/vision.key\n"
            "本地 Ollama 需先启动（ollama pull qwen2.5-vl:7b）。", w)
        note.setWordWrap(True)
        note.setStyleSheet("color:rgba(128,128,128,0.85);")
        lay.addWidget(note)
        lay.addStretch(1)
        # 输入即写回 config（点保存后由主窗口持久化）
        self.chk_vision.toggled.connect(
            lambda v: setattr(self.config, "vision_enabled", bool(v)))
        self.cmb_vision_provider.currentIndexChanged.connect(
            lambda i: setattr(
                self.config, "vision_provider", "ollama" if i == 0 else "cloud"))
        self.edit_vision_endpoint.textChanged.connect(
            lambda t: setattr(self.config, "vision_endpoint", t.strip()))
        self.edit_vision_model.textChanged.connect(
            lambda t: setattr(self.config, "vision_model", t.strip()))
        self.sp_vision_width.valueChanged.connect(
            lambda v: setattr(self.config, "vision_max_image_width", v))
        self.sp_vision_quality.valueChanged.connect(
            lambda v: setattr(self.config, "vision_jpeg_quality", v))
        self.sp_vision_step.valueChanged.connect(
            lambda v: setattr(self.config, "vision_step_limit", v))
        self.cmb_vision_level.currentIndexChanged.connect(
            lambda i: setattr(self.config, "vision_permission_level", i))
        self.chk_vision_l3.toggled.connect(
            lambda v: setattr(self.config, "vision_l3_confirm", bool(v)))
        return w

    # ------------------------------------------------------------------ #
    def _tab_appearance(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(*DIALOG_MARGINS)
        lay.setSpacing(GROUP_SPACING)
        lay.addWidget(section_label("主题与配色", w))
        form = tune_form(QFormLayout())

        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(["跟随系统", "深色", "浅色"])
        self.cmb_theme.setCurrentIndex(
            {"auto": 0, "dark": 1, "light": 2}.get(self.config.theme, 0))
        form.addRow("主题", self.cmb_theme)

        self.cmb_accent = QComboBox()
        # 依据 DESIGN.md：整个界面的色彩预算只留给蓝色系
        for name, code in [("Apple 蓝 #0071e3（推荐）", "#0071e3"),
                           ("亮蓝 #2997ff", "#2997ff"),
                           ("链接蓝 #0066cc", "#0066cc")]:
            self.cmb_accent.addItem(name, code)
        idx = self.cmb_accent.findData(self.config.accent_color)
        self.cmb_accent.setCurrentIndex(max(0, idx))
        form.addRow("强调色", self.cmb_accent)

        self.sp_font = QSpinBox()
        self.sp_font.setRange(11, 18)
        self.sp_font.setValue(self.config.font_size)
        form.addRow("界面字号", self.sp_font)

        self.chk_bookmarkbar = QCheckBox("显示书签栏")
        self.chk_bookmarkbar.setChecked(self.config.show_bookmark_bar)
        form.addRow("", self.chk_bookmarkbar)

        # v2.1.5：新标签页壁纸（随包白名单）与标签栏位置（Edge 风）
        self.cmb_wallpaper = QComboBox()
        self.cmb_wallpaper.addItem("无壁纸（渐变背景）", "")
        self.cmb_wallpaper.addItem("极光 · 洋红", "aurora-magenta.jpg")
        self.cmb_wallpaper.addItem("极光 · 青柠", "aurora-lime.jpg")
        self.cmb_wallpaper.addItem("极光 · 暮蓝", "aurora-twilight.jpg")
        self.cmb_wallpaper.addItem("极光 · 紫青", "aurora-violet.jpg")
        idx = self.cmb_wallpaper.findData(
            getattr(self.config, "ntp_wallpaper", "") or "")
        self.cmb_wallpaper.setCurrentIndex(max(0, idx))
        form.addRow("新标签页壁纸", self.cmb_wallpaper)

        self.cmb_tabspos = QComboBox()
        self.cmb_tabspos.addItem("上方标签栏", "top")
        self.cmb_tabspos.addItem("左侧垂直标签（Edge 风）", "left")
        idx = self.cmb_tabspos.findData(
            getattr(self.config, "tabs_position", "top") or "top")
        self.cmb_tabspos.setCurrentIndex(max(0, idx))
        form.addRow("标签栏位置", self.cmb_tabspos)

        lay.addLayout(form)
        lay.addStretch(1)
        return w

    def _tab_startup(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(*DIALOG_MARGINS)
        lay.setSpacing(GROUP_SPACING)
        lay.addWidget(section_label("启动与主页", w))
        form = tune_form(QFormLayout())

        self.cmb_startup = QComboBox()
        self.cmb_startup.addItems(
            ["主页", "新建标签页", "恢复上次会话", "空白页"])
        map_ = {"homepage": 0, "speeddial": 1, "resume": 2, "blank": 3}
        self.cmb_startup.setCurrentIndex(map_.get(self.config.startup_pages, 0))
        form.addRow("启动时", self.cmb_startup)

        self.edit_home = QLineEdit(self.config.homepage)
        form.addRow("主页", self.edit_home)

        self.chk_resume = QCheckBox("关闭时保存并恢复标签页")
        self.chk_resume.setChecked(self.config.resume_session)
        form.addRow("", self.chk_resume)

        lay.addLayout(form)
        lay.addStretch(1)
        return w

    def _tab_privacy(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(*DIALOG_MARGINS)
        lay.setSpacing(GROUP_SPACING)
        grp = QGroupBox("隐私与安全")
        v = QVBoxLayout(grp)
        v.setSpacing(10)
        self.chk_adblock = QCheckBox("拦截广告与跟踪器")
        self.chk_adblock.setChecked(self.config.adblock)
        self.chk_dnt = QCheckBox("发送“禁止跟踪”请求")
        self.chk_dnt.setChecked(self.config.do_not_track)
        self.chk_safe = QCheckBox("恶意/钓鱼网站防护（安全浏览）")
        self.chk_safe.setChecked(self.config.safe_browsing)
        self.chk_pwd = QCheckBox("保存网站密码（加密）")
        self.chk_pwd.setChecked(self.config.save_passwords)
        v.addWidget(self.chk_adblock)
        v.addWidget(self.chk_dnt)
        v.addWidget(self.chk_safe)
        v.addWidget(self.chk_pwd)
        note = QLabel(f"密码加密方式：{password_security_note()}")
        note.setWordWrap(True)
        v.addWidget(note)
        lay.addWidget(grp)

        grp2 = QGroupBox("站点权限")
        v2 = QVBoxLayout(grp2)
        v2.setSpacing(10)
        btn_perm = QPushButton("管理站点权限（摄像头/麦克风/位置/通知）")
        btn_perm.clicked.connect(self._open_permissions)
        v2.addWidget(btn_perm)
        lay.addWidget(grp2)

        lay.addStretch(1)
        return w

    def _open_permissions(self):
        PermissionsDialog(self._perm_store, self).exec()

    def _tab_performance(self):
        """标准 #6：内存与资源占用控制。"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(*DIALOG_MARGINS)
        lay.setSpacing(GROUP_SPACING)
        lay.addWidget(section_label("内存与资源", w))
        form = tune_form(QFormLayout())

        self.sp_hibernate = QSpinBox()
        self.sp_hibernate.setRange(0, 120)
        self.sp_hibernate.setSuffix(" 分钟（0 = 关闭休眠）")
        self.sp_hibernate.setValue(
            getattr(self.config, "hibernate_background_mins", 10))
        form.addRow("后台标签空闲休眠", self.sp_hibernate)

        self.sp_cache = QSpinBox()
        self.sp_cache.setRange(0, 4096)
        self.sp_cache.setSuffix(" MB")
        self.sp_cache.setValue(getattr(self.config, "http_cache_mb", 400))
        form.addRow("HTTP 缓存上限", self.sp_cache)

        self.edit_flags = QLineEdit(getattr(self.config, "chromium_flags", ""))
        self.edit_flags.setPlaceholderText("高级：附加 Chromium 启动参数，空格分隔")
        form.addRow("内核参数", self.edit_flags)

        tip = QLabel("休眠的标签在切换回去时自动恢复，可显著降低长期运行的内存占用。")
        tip.setWordWrap(True)
        lay.addLayout(form)
        lay.addWidget(tip)
        lay.addStretch(1)
        return w

    def _tab_network(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(*DIALOG_MARGINS)
        lay.setSpacing(GROUP_SPACING)
        lay.addWidget(section_label("搜索与代理", w))
        form = tune_form(QFormLayout())
        self.cmb_engine = QComboBox()
        from app.search_engines import ENGINES
        for key, meta in ENGINES.items():
            self.cmb_engine.addItem(meta["name"], key)
        idx = self.cmb_engine.findData(self.config.engine)
        self.cmb_engine.setCurrentIndex(max(0, idx))
        form.addRow("搜索引擎", self.cmb_engine)
        self.chk_proxy = QCheckBox("使用系统代理")
        self.chk_proxy.setChecked(self.config.use_system_proxy)
        form.addRow("", self.chk_proxy)
        self.chk_suggest = QCheckBox("地址栏联网搜索建议（关闭后输入不再发送给搜索引擎）")
        self.chk_suggest.setChecked(
            getattr(self.config, "search_suggestions", True))
        form.addRow("", self.chk_suggest)
        lay.addLayout(form)
        lay.addStretch(1)
        return w

    def _tab_download(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(*DIALOG_MARGINS)
        lay.setSpacing(GROUP_SPACING)
        lay.addWidget(section_label("下载位置", w))
        form = tune_form(QFormLayout())
        self.edit_dldir = QLineEdit(self.config.download_dir)
        self.edit_dldir.setPlaceholderText("默认：系统下载目录")
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._browse_dir)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.edit_dldir, 1)
        row.addWidget(btn_browse)
        form.addRow("下载目录", row)
        self.chk_ask = QCheckBox("下载前询问保存位置")
        self.chk_ask.setChecked(self.config.ask_download_location)
        form.addRow("", self.chk_ask)
        lay.addLayout(form)
        lay.addStretch(1)
        return w

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择下载目录")
        if d:
            self.edit_dldir.setText(d)

    # ------------------------------------------------------------------ #
    def apply(self):
        """把界面值写回 config（立即生效）。"""
        self.config.theme = ["auto", "dark", "light"][self.cmb_theme.currentIndex()]
        self.config.accent_color = self.cmb_accent.currentData()
        self.config.font_size = self.sp_font.value()
        self.config.show_bookmark_bar = self.chk_bookmarkbar.isChecked()
        # v2.1.5：NTP 壁纸与标签栏位置（config.load 已做白名单校验兜底）
        self.config.ntp_wallpaper = self.cmb_wallpaper.currentData() or ""
        self.config.tabs_position = self.cmb_tabspos.currentData() or "top"

        startup_map = ["homepage", "speeddial", "resume", "blank"]
        self.config.startup_pages = startup_map[self.cmb_startup.currentIndex()]
        # v2.1.2 修复：主页在设置界面保存时即过 scheme 白名单，
        # 拒绝 javascript:/file: 等（此前要等下次启动 load 时才兜底，
        # 当前会话内的"主页"按钮仍会带着非法值）。
        from app.security import safe_url
        home = safe_url(self.edit_home.text().strip())
        self.config.homepage = home or "https://www.baidu.com"
        self.config.resume_session = self.chk_resume.isChecked()

        self.config.adblock = self.chk_adblock.isChecked()
        self.config.do_not_track = self.chk_dnt.isChecked()
        self.config.safe_browsing = self.chk_safe.isChecked()
        self.config.save_passwords = self.chk_pwd.isChecked()

        self.config.hibernate_background_mins = self.sp_hibernate.value()
        self.config.http_cache_mb = self.sp_cache.value()
        self.config.chromium_flags = self.edit_flags.text().strip()

        self.config.engine = self.cmb_engine.currentData()
        self.config.use_system_proxy = self.chk_proxy.isChecked()
        self.config.search_suggestions = self.chk_suggest.isChecked()

        self.config.download_dir = self.edit_dldir.text().strip()
        self.config.ask_download_location = self.chk_ask.isChecked()
        return self.config

    def accept(self):
        self.apply()
        super().accept()


class PermissionsDialog(QDialog):
    """站点权限决策清单（标准 #14）。"""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self._store = store
        self.setWindowTitle("站点权限")
        self.resize(540, 420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*DIALOG_MARGINS)
        lay.setSpacing(12)
        lay.addWidget(section_label("已记忆的站点权限决策", self))
        self.listw = QListWidget(self)
        self.listw.setSpacing(2)
        lay.addWidget(self.listw, 1)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btn_del = QPushButton("撤销选中站点的全部权限", self)
        btn_del.clicked.connect(self._revoke)
        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.accept)
        btns.addWidget(btn_del)
        btns.addStretch(1)
        btns.addWidget(btn_close)
        lay.addLayout(btns)
        unify_control_heights(self)
        self._refresh()

    def _refresh(self):
        self.listw.clear()
        from PySide6.QtWidgets import QListWidgetItem
        sites = self._store.all_sites() if self._store else []
        if not sites:
            item = QListWidgetItem("（暂无已记忆的权限决策）")
            item.setFlags(Qt.NoItemFlags)
            self.listw.addItem(item)
            return
        for host, feats in sites:
            labels = []
            for f, d in feats:
                name = FEATURE_NAMES.get(f, f"权限{f}")
                word = {"allow": "允许", "deny": "拒绝"}.get(d, d)
                labels.append(f"{name}:{word}")
            item = QListWidgetItem(f"{host}　{'·'.join(labels)}")
            item.setData(Qt.UserRole, host)
            self.listw.addItem(item)

    def _revoke(self):
        item = self.listw.currentItem()
        if item and self._store:
            host = item.data(Qt.UserRole)
            if host:
                self._store.forget(host)
                self._refresh()
