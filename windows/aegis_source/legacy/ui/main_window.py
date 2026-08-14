# -*- coding: utf-8 -*-
"""main_window.py —— 浏览器主窗口（编排层）。

整合地址栏、标签页、书签栏、查找栏、下载栏、菜单与各服务，
并负责主题应用、会话保存、历史/密码管理、导入导出等。
"""

import os
from PySide6.QtCore import (Qt, QUrl, QSize, QPoint, QPropertyAnimation,
                          QEasingCurve, QAbstractAnimation)
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QToolButton, QLabel, QLineEdit,
    QHBoxLayout, QVBoxLayout, QMenu, QStatusBar, QMessageBox, QFileDialog,
    QDialog, QApplication, QToolBar,
)

from app.browser import BrowserContext
from app.hsts import maybe_upgrade
from app.i18n import tr
from .theme import style_for, load_app_font, font_family_css
from .icons import icon, set_theme as set_icon_theme
from .address_bar import AddressBar
from .browser_tab import BrowserTab
from .find_bar import FindBar
from .download_bar import DownloadBar
from .settings_dialog import (SettingsDialog, PermissionsDialog,
                              CONTROL_HEIGHT, DIALOG_MARGINS, section_label,
                              unify_control_heights)
from .dialogs import BookmarkManagerDialog, HistoryDialog, PasswordDialog, DialsDialog
from .tab_strip import BrowserTabWidget
from .bookmark_bar import BookmarkBar
from .security_dashboard import SecurityDashboard
from .view_source import ViewSource
from .clear_data import ClearBrowsingData
from .site_info import SiteInfo
from .command_palette import CommandPalette
from .ai_assistant import AegisAIPanel
from .password_tools import PasswordToolsDialog
from .ima_notes import ImaNotesDialog
from .ima_knowledge import ImaKnowledgeDialog

HOME_PAGE = "https://www.baidu.com"









class MainWindow(QMainWindow):
    """浏览器主窗口。"""

    def __init__(self, ctx: BrowserContext):
        super().__init__()
        self.ctx = ctx
        self.config = ctx.config
        self.setWindowTitle("Aegis")
        self.resize(1280, 840)
        self.setMinimumSize(760, 520)
        # v1.5：恢复已关闭标签的栈
        self._closed_stack = []

        self._build_tabs()
        self._build_nav()
        self._build_menus()
        self._build_findbar()
        self._build_downloadbar()
        self._build_statusbar()

        # 下载事件（profile 级）
        self.ctx.profile.downloadRequested.connect(self._on_download_requested)

        self.apply_theme()

        # 液态玻璃：启用 Windows DWM 毛玻璃（窗口透明区域透出系统级模糊）
        self._enable_glass()

        # 启动内容
        self._initial_startup()

        # 崩溃安全：周期性自动保存会话
        if self.config.resume_session and not self.ctx.incognito:
            from PySide6.QtCore import QTimer
            self._autosave = QTimer(self)
            self._autosave.setInterval(15000)
            self._autosave.timeout.connect(self._autosave_session)
            self._autosave.start()

        # 内存优化（标准 #6）：后台空闲标签定时器休眠
        from PySide6.QtCore import QTimer
        self._hib_timer = QTimer(self)
        self._hib_timer.setInterval(60_000)
        self._hib_timer.timeout.connect(self._check_hibernation)
        if self.config.hibernate_background_mins > 0:
            self._hib_timer.start()

        # 启动后延迟检查更新（非阻塞；未配置更新源时静默）
        if self.config.update_auto_check and self.ctx.updater.enabled():
            QTimer.singleShot(8000, self.ctx.updater.check)
        self._wire_updater()

        # 会话保存于关闭时
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    # ================================================================== #
    # UI 构建
    # ================================================================== #
    def _build_tabs(self):
        self.tabs = BrowserTabWidget(self)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabbar = self.tabs.bar()

        # 自定义标签栏信号
        self.tabs.close_requested.connect(self._close_tab)
        self.tabs.new_tab_requested.connect(self.new_tab)
        self.tabs.pin_requested.connect(self._toggle_pin)
        self.tabs.mute_requested.connect(self._toggle_mute)
        self.tabs.refresh_requested.connect(self._refresh_tab_at)
        self.tabs.close_others_requested.connect(self._close_others)
        self.tabs.group_edit_requested.connect(self._edit_group)

        # 中央区域用布局承载（标签容器 + 下载栏），避免浮层用 move() 绝对定位
        central = QWidget(self)
        central.setObjectName("centralArea")
        # 保持透明，DWM 毛玻璃仍从标签栏空白处透出
        central.setStyleSheet("#centralArea { background: transparent; }")
        self._central_layout = QVBoxLayout(central)
        self._central_layout.setContentsMargins(0, 0, 0, 0)
        self._central_layout.setSpacing(0)
        self._central_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        # v2.1.5：初始标签位置（top=上方 / left=左侧垂直，Edge 风）
        self._apply_tab_placement()

    def _apply_tab_placement(self):
        """按 config.tabs_position 应用标签栏位置（上方/左侧垂直）。"""
        pos = getattr(self.config, "tabs_position", "top") or "top"
        self.tabs.set_tab_placement(pos)
        # 同步视图菜单里的位置提示文案
        act = getattr(self, "_tabs_pos_action", None)
        if act is not None:
            label = tr("标签栏位置：左侧垂直（Ctrl+Shift+Y 切换）") \
                if pos == "left" else tr("标签栏位置：上方（Ctrl+Shift+Y 切换）")
            act.setText(label)

    def _toggle_tab_placement(self):
        """在上方标签栏与左侧垂直标签栏之间切换（Ctrl+Shift+Y）。"""
        cur = getattr(self.config, "tabs_position", "top") or "top"
        self.config.tabs_position = "left" if cur != "left" else "top"
        self._apply_tab_placement()
        self.ctx.save_config()
        state = "左侧垂直标签" if self.config.tabs_position == "left" \
            else "上方标签栏"
        self.status.showMessage(f"已切换到{state}", 3000)

    def _build_nav(self):
        bar = QToolBar("导航", self)
        bar.setObjectName("navBar")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setIconSize(QSize(20, 20))   # 配合 40px 触控目标略放大
        self.addToolBar(bar)

        # 记录按钮与图标名，主题切换时按新描边色重新生成图标
        self._nav_buttons = []

        def btn(icon_name, tip, text=""):
            b = QToolButton(self)
            b.setIcon(icon(icon_name))
            b.setText(text)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            bar.addWidget(b)
            self._nav_buttons.append((b, icon_name))
            return b

        self.btn_back = btn("back", "后退")
        self.btn_forward = btn("forward", "前进")
        self.btn_reload = btn("reload", "刷新")
        self.btn_home = btn("home", "主页")
        bar.addSeparator()

        # 地址栏（占据剩余宽度）
        self.sec_label = QLabel("", self)
        self.sec_label.setToolTip("站点连接安全性")
        self.sec_label.setFixedWidth(22)
        bar.addWidget(self.sec_label)

        self.address = AddressBar(self.ctx.search, self.ctx.history,
                                  self.ctx.bookmarks, self)
        self.address.navigate.connect(self._navigate)
        self.address.navigate_new_tab.connect(
            lambda url: self.open_new_tab(url))
        bar.addWidget(self.address)

        self.btn_star = btn("star_outline", "收藏")
        self.btn_star.clicked.connect(self._toggle_bookmark)
        self.btn_newtab = btn("plus", "新标签页 (Ctrl+T)")
        self.btn_newtab.clicked.connect(lambda: self.new_tab())
        self.btn_menu = btn("menu", "菜单")
        self.btn_menu.setPopupMode(QToolButton.InstantPopup)
        self.btn_menu.setMenu(self._build_burger_menu())

        self.btn_back.clicked.connect(self._back)
        self.btn_forward.clicked.connect(self._forward)
        self.btn_reload.clicked.connect(self._reload)
        self.btn_home.clicked.connect(lambda: self._navigate(self.config.homepage))

        # ---- 书签栏（Chrome 风格，位于导航栏下方独立一行）----
        self.addToolBarBreak(Qt.TopToolBarArea)
        self._bm_toolbar = QToolBar("书签栏", self)
        self._bm_toolbar.setObjectName("bookmarkToolBar")
        self._bm_toolbar.setMovable(False)
        self._bm_toolbar.setFloatable(False)
        self.bookmark_bar = BookmarkBar(self.ctx.bookmarks, self)
        self.bookmark_bar.navigate.connect(self._navigate)
        self.bookmark_bar.open_new_tab.connect(self.open_new_tab)
        self._bm_toolbar.addWidget(self.bookmark_bar)
        self.addToolBar(self._bm_toolbar)
        self._bm_toolbar.setVisible(self.config.show_bookmark_bar)

    def _build_menus(self):
        mb = self.menuBar()
        self._build_file_menu(mb.addMenu("文件"))
        self._build_edit_menu(mb.addMenu("编辑"))
        self._build_view_menu(mb.addMenu("视图"))
        self._build_history_menu(mb.addMenu("历史"))
        self._build_bookmarks_menu(mb.addMenu("书签"))
        self._build_tools_menu(mb.addMenu("工具"))
        self._build_help_menu(mb.addMenu("帮助"))
        # v1.5 全局快捷键：Ctrl+L 地址栏 / Ctrl+Tab 切换标签
        from PySide6.QtGui import QShortcut
        from PySide6.QtGui import QKeySequence
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._focus_address)
        QShortcut(QKeySequence("Ctrl+J"), self,
                  activated=self._show_download_bar)
        QShortcut(QKeySequence("Ctrl+Tab"), self, activated=self._next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self,
                  activated=self._prev_tab)
        QShortcut(QKeySequence("Ctrl+U"), self, activated=self._open_view_source)
        QShortcut(QKeySequence("Ctrl+Shift+P"), self,
                  activated=self._open_command_palette)
        QShortcut(QKeySequence("Ctrl+Shift+I"), self,
                  activated=self._open_devtools)
        QShortcut(QKeySequence("F12"), self,
                  activated=self._open_devtools)
        # v2.1.5：上方/左侧垂直标签栏切换（Edge 风）
        QShortcut(QKeySequence("Ctrl+Shift+Y"), self,
                  activated=self._toggle_tab_placement)

    def _build_bookmarks_menu(self, m):
        """v1.5：填充书签菜单（此前为空菜单）。"""
        self._bookmarks_menu = m
        m.addAction(tr("收藏/取消收藏当前页"), self._toggle_bookmark, "Ctrl+D")
        m.addAction(tr("阅读清单…"), self._open_reading_list)
        m.addAction(tr("书签管理…"), self._open_bookmark_manager)
        m.addSeparator()

        def _rebuild():
            while len(m.actions()) > 3:
                m.removeAction(m.actions()[-1])
            for b in self.ctx.bookmarks.all()[:20]:
                act = m.addAction(b["title"] or b["url"])
                act.triggered.connect(
                    lambda _=False, u=b["url"]: self.open_new_tab(u))
        _rebuild()
        self._bookmarks_menu_rebuild = _rebuild

    def _focus_address(self):
        self.address.setFocus()
        self.address.selectAll()

    def _next_tab(self):
        c = self.tabs.count()
        if c > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % c)

    def _prev_tab(self):
        c = self.tabs.count()
        if c > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1) % c)

    def _build_file_menu(self, m):
        m.addAction(tr("新标签页 (Ctrl+T)"), self.new_tab)
        m.addAction(tr("新窗口 (Ctrl+N)"), self._new_window)
        if not self.ctx.incognito:
            m.addAction(tr("新建无痕会话"), self._new_incognito)
        m.addAction(tr("恢复已关闭标签 (Ctrl+Shift+T)"), self._reopen_closed_tab,
                    "Ctrl+Shift+T")
        m.addAction(tr("关闭标签页 (Ctrl+W)"), self._close_current)
        m.addSeparator()
        m.addAction(tr("打印为 PDF (Ctrl+P)"), self._print_pdf)
        m.addSeparator()
        m.addAction(tr("退出 (Ctrl+Q)"), self.close, "Ctrl+Q")

    def _build_edit_menu(self, m):
        m.addAction(tr("复制 (Ctrl+C)"), self._copy)
        m.addAction(tr("粘贴 (Ctrl+V)"), self._paste)
        m.addSeparator()
        m.addAction(tr("在页面中查找 (Ctrl+F)"), self._show_find)
        m.addAction(tr("密码管理器"), self._open_passwords)

    def _build_view_menu(self, m):
        m.addAction(tr("放大 (Ctrl+=)"), lambda: self._zoom(1), "Ctrl+=")
        m.addAction(tr("缩小 (Ctrl+-)"), lambda: self._zoom(-1), "Ctrl+-")
        m.addAction(tr("重置缩放 (Ctrl+0)"), lambda: self._zoom(0), "Ctrl+0")
        m.addSeparator()
        m.addAction(tr("标签搜索 (Ctrl+Shift+A)"), self._tab_search, "Ctrl+Shift+A")
        # v2.1.5：标签栏位置（上方 / 左侧垂直，Edge 风）
        self._tabs_pos_action = m.addAction(
            tr("标签栏位置：上方（Ctrl+Shift+Y 切换）"),
            self._toggle_tab_placement, "Ctrl+Shift+Y")
        m.addAction(tr("阅读模式"), self._reader_mode)
        m.addAction(tr("保存页面截图 (Ctrl+Shift+S)"), self._save_screenshot,
                    "Ctrl+Shift+S")
        m.addSeparator()
        m.addAction(tr("全屏 (F11)"), self._toggle_fullscreen, "F11")
        m.addAction(tr("下载管理"), lambda: self.download_bar.setVisible(True))

    def _build_history_menu(self, m):
        m.addAction(tr("查看历史记录"), self._open_history)
        m.addSeparator()
        m.addAction(tr("清除浏览数据"), self._clear_data)

    def _build_tools_menu(self, m):
        m.addAction(tr("设置"), self._open_settings)
        m.addAction(tr("任务管理器"), self._open_task_manager)
        m.addAction(icon("lock"), tr("安全仪表盘"), self._open_security_dashboard)
        m.addAction(icon("source"), tr("查看源代码 (Ctrl+U)"), self._open_view_source)
        m.addAction(tr("命令面板 (Ctrl+Shift+P)"), self._open_command_palette)
        m.addAction(tr("站点信息"), self._open_site_info)
        m.addAction(tr("站点权限…"), self._open_site_permissions)
        m.addAction(tr("开发者工具 (Ctrl+Shift+I)"), self._open_devtools)
        m.addAction(tr("强制深色模式"), self._toggle_force_dark)
        m.addSeparator()
        m.addAction(icon("star_outline"), tr("自定义首页拨号…"),
                    self._open_dial_manager)
        m.addAction(tr("视觉问答（AI）"), self._open_vision_panel)
        m.addAction(tr("AI 上网代理"), self._open_computer_use)
        m.addAction(tr("AI 助手（本地）"), self._open_translate)
        m.addAction(tr("保存到 IMA 笔记"), self._open_ima_notes)
        m.addAction(tr("IMA 知识库"), self._open_ima_kb)
        m.addSeparator()
        m.addAction(tr("网页截图 (PNG)"), self._capture_screenshot)
        m.addAction(tr("导入书签…"), self._import_bookmarks)
        m.addAction(tr("导出书签…"), self._export_bookmarks)
        m.addSeparator()
        m.addAction(tr("用户脚本管理…"), self._open_user_scripts)
        m.addSeparator()
        m.addAction(tr("更新恶意站点情报"), self._refresh_threat_feed)
        m.addSeparator()
        m.addAction(tr("导出加密同步备份…"), self._export_sync)
        m.addAction(tr("导入加密同步备份…"), self._import_sync)
        m.addAction(tr("同步到 WebDAV…"), self._sync_webdav_push)
        m.addAction(tr("从 WebDAV 拉取…"), self._sync_webdav_pull)

    def _build_help_menu(self, m):
        m.addAction(tr("检查更新"), self._check_update)
        m.addSeparator()
        m.addAction(tr("关于 Aegis"), self._about)

    def _build_burger_menu(self):
        m = QMenu(self)
        m.addAction(tr("新标签页"), self.new_tab)
        m.addAction(tr("新窗口"), self._new_window)
        m.addSeparator()
        m.addAction(tr("历史记录"), self._open_history)
        m.addAction(tr("下载"), lambda: self.download_bar.setVisible(True))
        m.addAction(tr("密码管理"), self._open_passwords)
        m.addSeparator()
        m.addAction(icon("lock"), tr("安全仪表盘"), self._open_security_dashboard)
        m.addSeparator()
        m.addAction(icon("source"), tr("查看源代码 (Ctrl+U)"), self._open_view_source)
        m.addAction(tr("命令面板 (Ctrl+Shift+P)"), self._open_command_palette)
        m.addAction(tr("站点信息"), self._open_site_info)
        m.addAction(tr("强制深色模式"), self._toggle_force_dark)
        m.addSeparator()
        m.addAction(tr("视觉问答（AI）"), self._open_vision_panel)
        m.addAction(tr("AI 上网代理"), self._open_computer_use)
        m.addAction(tr("AI 助手（本地）"), self._open_translate)
        m.addAction(tr("保存到 IMA 笔记"), self._open_ima_notes)
        m.addAction(tr("IMA 知识库"), self._open_ima_kb)
        m.addAction(tr("密码工具"), self._open_password_tools)
        m.addSeparator()
        m.addAction(tr("设置"), self._open_settings)
        m.addAction(tr("关于"), self._about)
        # U-5：菜单弹出同样走淡入，避免瞬间"啪"地出现
        m.aboutToShow.connect(lambda: self._fade_in_popup(m, 150))
        return m

    def _build_findbar(self):
        self.find_bar = FindBar(self)
        self.find_bar.find_requested.connect(self._do_find)
        self.find_bar.closed.connect(self._clear_find)

    def _build_downloadbar(self):
        """下载栏由中央布局定位（右下角），不再用 move() 绝对定位。

        绝对定位在窗口缩放、DPI 变化或跨显示器移动时容易错位；交给布局后
        位置随窗口自动重算，show/hide 行为与滑入动画保持不变。
        """
        self.download_bar = DownloadBar(self.ctx.downloads, self)
        self._central_layout.addWidget(
            self.download_bar, 0, Qt.AlignRight | Qt.AlignBottom)

    def _build_statusbar(self):
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.progress_label = QLabel("", self)
        self.status.addPermanentWidget(self.progress_label)
        self.status.showMessage("就绪", 3000)

    # ================================================================== #
    # 标签页管理
    # ================================================================== #
    def new_tab(self, url: str | None = None, switch=True,
                  pinned=False, page=None) -> BrowserTab:
        tab = BrowserTab(self.ctx.profile, self.config, self, page=page)
        tab.set_history_store(self.ctx.history)
        tab.pinned = pinned
        tab.muted = False
        self.tabs.addTab(tab, "新标签页")

        # 注意：索引必须在信号触发时动态计算（标签关闭/排序后会变化），
        # 若在连接时捕获 idx 闭包，之后会出现"标题更新到错误标签"的 bug。
        tab.title_changed.connect(
            lambda t, w=tab: self._set_tab_title(self.tabs.indexOf(w), t))
        tab.icon_changed.connect(
            lambda ic, w=tab: self._set_tab_icon(self.tabs.indexOf(w), ic))
        tab.load_progress.connect(self._on_progress)
        tab.load_finished.connect(lambda: self._on_finished(tab))
        tab.open_link_new_tab.connect(self.open_new_tab)
        tab.host_page.connect(self._host_page)
        tab.mute_changed.connect(
            lambda m, w=tab: self._on_mute_changed(self.tabs.indexOf(w), m))
        tab.link_hovered.connect(self._on_link_hovered)
        tab.permission_requested.connect(self._on_permission_requested)
        tab.view_source_requested.connect(self._open_view_source)

        # 注入安全浏览（标准 #11）
        tab.set_safe_browsing(self.ctx.safe_browsing)

        # v1.5：用户脚本注入（Tampermonkey 式轻量扩展）
        self.ctx.user_scripts.apply_to_page(tab.page)

        idx = self.tabs.indexOf(tab)
        if page is None:
            if url:
                tab.load_url(url)
            elif self.config.use_speed_dial_newtab:
                self._load_new_tab_page(tab, idx)
            else:
                tab.load_url("about:blank")

        self._sync_tabbar()
        if switch:
            self.tabs.setCurrentIndex(self.tabs.indexOf(tab))
        return tab

    def _host_page(self, page):
        """把 target=_blank 创建的页面承载到新标签页。"""
        self.new_tab(switch=True, page=page)

    def open_new_tab(self, url: str, switch=True):
        return self.new_tab(url, switch)

    def _load_new_tab_page(self, tab, idx):
        """在标签页中渲染快捷拨号首页（通过 QWebEngine 加载 data URL）。"""
        page = self._new_tab_page_html()
        tab.view.setHtml(page, QUrl("aegis://newtab"))

    def _new_tab_page_html(self) -> str:
        """生成液态玻璃速拨首页 HTML（v2.1.3：Fluent mesh × Apple glass）。

        安全不变式（继承 v1.4 H2）：
        - 历史/书签标题与 URL 全部 html.escape；
        - 拨号 URL 只放行 http/https（safe_url 白名单）；
        - 搜索为原生表单（无内联 JS），页面启用 script-src 'none' 的 CSP，
          form-action 限 https:，彻底封死存储型 XSS。
        """
        import html as html_mod
        from app.system_theme import resolve_dark
        from app.security import safe_url
        dark = resolve_dark(self.config.theme)
        dials = []
        _seen = set()

        def _add(title, url):
            # v2.1.4 修复：按 URL 去重（历史与书签可能重叠同一站点），
            # 与 Qt 版 _collect_dials 行为对齐
            if url in _seen:
                return
            _seen.add(url)
            dials.append((title, url))

        for rec in self.ctx.history.most_visited(4):
            _add(rec["title"] or rec["url"], rec["url"])
        for b in self.ctx.bookmarks.all()[:6]:
            _add(b["title"] or b["url"], b["url"])
        from .new_tab_page import DEFAULT_DIALS
        from .icons_dial import dial_icon_svg

        # v2.1.5：自定义首页拨号优先——用户已自定义则只用自定义列表，
        # 否则回退"历史常用 + 书签 + 内置默认"的自动组合。
        dials_auto = dials
        dials = []
        _seen2 = set()

        def _add2(title, url):
            if url in _seen2:
                return
            _seen2.add(url)
            dials.append((title, url))

        cust = getattr(self.ctx, "dials", None)
        if cust is not None and cust.is_customized():
            for name, url in cust.all():
                _add2(name, url)
        else:
            for title, url in dials_auto:
                _add2(title, url)
        tiles = []
        for uid, (t, u) in enumerate(dials[:15]):
            # scheme 白名单过滤 + 属性级转义，双保险
            su = safe_url(u)
            if not su:
                continue
            # v2.1.4：代码自动生成的 Apple 级 squircle 图标（内联 SVG，
            # CSP img-src 'none' 不受影响；标题首字母经 escape 注入）
            icon_svg = dial_icon_svg(su, str(t), uid)
            tiles.append(
                f'<a class="tile" href="{html_mod.escape(su, quote=True)}">'
                f'<div class="ico">{icon_svg}</div>'
                f'<span>{html_mod.escape(str(t))}</span></a>')
        tiles = "\n".join(tiles)
        # 搜索用原生表单提交（action/参数名来自引擎注册表），页面无任何脚本
        form_action, form_param = self.ctx.search.form_fields()
        # 强调色进入 CSS 前做白名单校验（仅 #RRGGBB，杜绝样式注入）
        import re as _re
        accent_raw = getattr(self.config, "accent_color", "") or ""
        if _re.fullmatch(r"#[0-9a-fA-F]{6}", accent_raw):
            accent = accent_raw
        else:
            accent = "#0071e3"
        # 焦点光环的半透明版本（由已校验的 hex 推导，安全）
        _r = int(accent[1:3], 16); _g = int(accent[3:5], 16)
        _b = int(accent[5:7], 16)
        accent_ring = f"rgba({_r},{_g},{_b},0.28)"
        accent_hover_ring = f"rgba({_r},{_g},{_b},0.45)"

        if dark:
            (bg, fg, fg_sub, glass, glass_hi, glass_edge,
             float_shadow, tile_shadow, tagline_c, search_ico,
             ico_shadow) = (
                "#05060a", "#ffffff", "rgba(255,255,255,0.62)",
                "rgba(255,255,255,0.055)", "rgba(255,255,255,0.16)",
                "rgba(255,255,255,0.12)",
                "0 14px 40px -20px rgba(41,151,255,0.28)",
                "0 8px 24px -16px rgba(0,0,0,0.55)",
                "rgba(255,255,255,0.50)", "rgba(255,255,255,0.70)",
                "0 10px 18px -6px rgba(0,0,0,0.60)")
            mesh = (
                "radial-gradient(900px 520px at 18% 12%, rgba(0,113,227,0.17), transparent 62%),"
                "radial-gradient(760px 460px at 84% 8%, rgba(90,200,250,0.10), transparent 60%),"
                "radial-gradient(820px 560px at 62% 96%, rgba(41,151,255,0.08), transparent 62%),"
                f"linear-gradient(180deg, #05060a 0%, #0a0d13 58%, #0e1219 100%)")
        else:
            (bg, fg, fg_sub, glass, glass_hi, glass_edge,
             float_shadow, tile_shadow, tagline_c, search_ico,
             ico_shadow) = (
                "#f5f5f7", "#1d1d1f", "rgba(0,0,0,0.56)",
                "rgba(255,255,255,0.72)", "rgba(255,255,255,0.95)",
                "rgba(0,0,0,0.10)",
                "0 10px 26px -16px rgba(0,0,0,0.25)",
                "0 6px 18px -12px rgba(0,0,0,0.18)",
                "rgba(0,0,0,0.50)", "rgba(0,0,0,0.60)",
                "0 10px 18px -6px rgba(0,0,0,0.22)")
            mesh = (
                "radial-gradient(900px 520px at 18% 10%, rgba(0,113,227,0.16), transparent 62%),"
                "radial-gradient(760px 460px at 84% 6%, rgba(90,200,250,0.18), transparent 60%),"
                "radial-gradient(820px 560px at 60% 98%, rgba(29,125,255,0.12), transparent 62%),"
                f"linear-gradient(180deg, #f7f8fa 0%, #f5f5f7 60%, #eff1f5 100%)")

        # ---- v2.1.5：NTP 壁纸（随包资产，aegisasset:// 白名单加载） ----
        # 壁纸 URL 仅由白名单文件名经 asset_scheme.wallpaper_url() 生成，
        # 配置层已校验；无壁纸则维持 mesh 渐变。CSP 的 img-src 只放行
        # aegisasset: 这一个自定义 scheme（不放 data:/http:，保持最小面）。
        bg_final = mesh
        csp_img = "img-src 'none'"
        title_shadow = "none"
        try:
            from app.asset_scheme import wallpaper_url as _wp_url
            wp_name = getattr(self.config, "ntp_wallpaper", "") or ""
            wurl = _wp_url(wp_name) if wp_name else ""
        except Exception:
            wurl = ""
        if wurl:
            scrim = ("rgba(5,6,10,0.40)" if dark
                     else "rgba(255,255,255,0.46)")
            bg_final = (f"linear-gradient({scrim},{scrim}),"
                        f"url({wurl}) center/cover no-repeat fixed")
            csp_img = "img-src aegisasset:"
            # 壁纸上主标题加柔和阴影保证可读（深底白字更明显）
            title_shadow = ("0 2px 18px rgba(0,0,0,0.45)" if dark
                            else "0 1px 12px rgba(255,255,255,0.6)")

        return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; {csp_img}; form-action https:;">
<style>
  body{{margin:0;font-family:{font_family_css()};height:100vh;background:{bg_final};
       background-color:{bg};-webkit-font-smoothing:antialiased;}}
  .wrap{{max-width:980px;margin:0 auto;padding-top:11vh;}}
  h1{{color:{fg};text-align:center;font-weight:600;font-size:56px;
     letter-spacing:-0.28px;line-height:1.07;margin:0 0 12px;
     text-shadow:{title_shadow};}}
  .tagline{{text-align:center;color:{tagline_c};font-size:15px;font-weight:500;
     letter-spacing:0.4px;margin:0 0 36px;}}
  .search{{display:block;margin:0 auto 52px;max-width:620px;}}
  .searchbox{{display:flex;background:{glass};border-radius:980px;
     border:1px solid {glass_edge};padding:13px 24px;
     box-shadow:0 1px 0 0 {glass_hi} inset, {float_shadow};
     transition:box-shadow .25s cubic-bezier(.32,.72,0,1),
                border-color .25s cubic-bezier(.32,.72,0,1);}}
  .searchbox:focus-within{{border-color:{accent};
     box-shadow:0 0 0 3px {accent_ring}, 0 1px 0 0 {glass_hi} inset;}}
  .searchbox input{{flex:1;background:transparent;border:none;color:{fg};
     font-size:17px;letter-spacing:-0.374px;outline:none;
     font-family:inherit;}}
  .searchbox input::placeholder{{color:{fg_sub};}}
  .searchbox button{{background:transparent;border:none;color:{search_ico};
     cursor:pointer;font-size:18px;font-family:inherit;}}
  .grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:16px;}}
  .tile{{text-decoration:none;color:{fg_sub};display:flex;flex-direction:column;
     align-items:center;gap:10px;padding:20px 8px 16px;border-radius:12px;
     background:{glass};border:1px solid {glass_edge};
     box-shadow:0 1px 0 0 {glass_hi} inset, {tile_shadow};
     transition:background .25s cubic-bezier(.32,.72,0,1),
                border-color .25s cubic-bezier(.32,.72,0,1),
                transform .25s cubic-bezier(.32,.72,0,1);}}
  .tile:hover{{background:{glass_hi};transform:translateY(-3px);
     border-color:{accent_hover_ring};}}
  .ico{{width:56px;height:56px;display:flex;align-items:center;justify-content:center;
     filter:drop-shadow({ico_shadow});
     transition:transform .25s cubic-bezier(.32,.72,0,1);}}
  .tile:hover .ico{{transform:scale(1.045);}}
  .tile span{{font-size:14px;letter-spacing:-0.224px;color:{fg};
     opacity:.82;max-width:120px;overflow:hidden;text-overflow:ellipsis;
     white-space:nowrap;}}
</style></head><body><div class="wrap">
<h1>Aegis</h1>
<p class="tagline">安全 · 极速 · 如玻璃般通透</p>
<form class="search" action="{html_mod.escape(form_action, quote=True)}" method="get">
  <div class="searchbox">
    <input type="text" name="{html_mod.escape(form_param, quote=True)}"
           placeholder="搜索或输入网址" autocomplete="off">
    <button type="submit">⌕</button>
  </div>
</form>
<div class="grid">{tiles}</div>
</div></body></html>"""

    def _set_tab_title(self, index, title):
        if index < 0:
            return
        if title.strip():
            self.tabs.setTabText(index, title.strip())
            if index == self.tabs.currentIndex():
                self.setWindowTitle(f"{title.strip()} - Aegis")

    def _set_tab_icon(self, index, icon):
        if index < 0:
            return
        if not icon.isNull():
            self.tabs.setTabIcon(index, icon)

    def _close_tab(self, index):
        w = self.tabs.widget(index)
        # v1.5：记录被关标签供 Ctrl+Shift+T 恢复（仅 http/https）
        if w is not None:
            from app.security import safe_url
            u = safe_url(w.url(), allow_internal=False)
            if u:
                self._closed_stack.append((u, w.title()))
                if len(self._closed_stack) > 50:
                    self._closed_stack.pop(0)
        self.tabs.removeTab(index)
        w.deleteLater()
        self._sync_tabbar()
        if self.tabs.count() == 0:
            self.new_tab()

    def _close_current(self):
        self._close_tab(self.tabs.currentIndex())

    def current_tab(self):
        return self.tabs.currentWidget()

    def _on_tab_changed(self, index):
        self._sync_address()
        self._refresh_nav()
        # B2：切换标签时更新缩略图缓存（当前标签可见，抓图可靠）
        try:
            self.tabs.capture_current_thumb()
        except Exception:
            pass
        t = self.tabs.currentWidget()
        if t is not None:
            import time
            t.last_active = time.time()
            # 激活被休眠的标签时自动唤醒（标准 #6）
            if getattr(t, "discarded", False):
                t.wake()

    # ---- 自定义标签栏状态同步 ----
    def _sync_tabbar(self):
        """从各标签对象刷新标签栏的固定/静音/加载/分组状态。"""
        pinned, muted, loading, groups = {}, {}, {}, {}
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if tab:
                pinned[i] = getattr(tab, "pinned", False)
                muted[i] = getattr(tab, "muted", False)
                loading[i] = getattr(tab, "is_loading", False)
                groups[i] = self._group_color(getattr(tab, "group", ""))
        bar = self.tabbar
        for i in range(self.tabs.count()):
            bar.set_pinned(i, pinned.get(i, False))
            bar.set_muted(i, muted.get(i, False))
            bar.set_loading(i, loading.get(i, False))
            bar.set_group(i, groups.get(i))

    def _toggle_pin(self, index, pinned):
        tab = self.tabs.widget(index)
        if tab:
            tab.pinned = pinned
            self._sync_tabbar()
            self._rebuild_bookmark_bar()

    def _toggle_mute(self, index, muted):
        tab = self.tabs.widget(index)
        if tab:
            tab.set_muted(muted)
            self._sync_tabbar()

    def _on_mute_changed(self, index, muted):
        # 注意参数顺序：(index, muted)。此前版本参数错位导致静音状态
        # always 应用到第 0/1 个标签。
        if index < 0:
            return
        tab = self.tabs.widget(index)
        if tab:
            tab.muted = bool(muted)
            self._sync_tabbar()

    def _refresh_tab_at(self, index):
        tab = self.tabs.widget(index)
        if tab:
            tab.reload_page()

    def _close_others(self, keep_index):
        for i in range(self.tabs.count() - 1, -1, -1):
            if i != keep_index:
                self._close_tab(i)

    # ================================================================== #
    # v1.5 生产力功能
    # ================================================================== #
    def _reopen_closed_tab(self):
        """Ctrl+Shift+T：恢复最近关闭的标签。"""
        while self._closed_stack:
            url, _title = self._closed_stack.pop()
            from app.security import safe_url
            if safe_url(url, allow_internal=False):
                self.open_new_tab(url)
                return

    def _tab_search(self):
        from .productivity import TabSearchDialog
        TabSearchDialog(self, self).exec()

    def _open_reading_list(self):
        from .productivity import ReadingListDialog
        ReadingListDialog(self, self).exec()

    def _open_user_scripts(self):
        from .productivity import UserScriptsDialog
        UserScriptsDialog(self, self).exec()

    def reinject_user_scripts(self):
        """用户脚本变更后对所有标签重新注入。"""
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if tab is not None:
                try:
                    tab.page.scripts().clear()
                    self.ctx.user_scripts.apply_to_page(tab.page)
                except Exception:
                    pass

    def _save_screenshot(self):
        """当前视口截图保存为 PNG（Ctrl+Shift+S）。"""
        t = self.current_tab()
        if not t:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存页面截图", "screenshot.png", "PNG (*.png)")
        if path:
            pix = t.view.grab()
            if pix.isNull():
                QMessageBox.warning(self, "截图失败", "页面尚未渲染完成，请稍后重试。")
                return
            pix.save(path, "PNG")
            self.status.showMessage(f"截图已保存：{path}", 5000)

    def _refresh_threat_feed(self):
        """手动刷新恶意站点情报订阅源。"""
        cfg_url = getattr(self.config, "threat_feed_url", "")
        if not cfg_url:
            QMessageBox.information(
                self, "威胁情报",
                "未配置订阅源。\n在 config.json 中设置 threat_feed_url "
                "（纯文本域名列表，支持 ||host^ 语法）后启用。")
            return
        self.status.showMessage("正在更新恶意站点情报…")

        def _done(count):
            self.ctx.safe_browsing.reload()
            self.ctx.logger.info(f"威胁情报已更新：{count} 条")
            self.status.showMessage(
                f"恶意站点情报已更新（{count} 条）", 6000)

        def _err(msg):
            self.status.showMessage(msg, 6000)

        # v2.1.2 修复：ThreatFeedUpdater 在自起的 daemon 线程里回调，
        # 在无线程事件循环的后台线程调用 QTimer.singleShot 会**静默丢失**
        # （qt_bridge.py 文档记录的同型缺陷）——改用 MainBridge：
        # 桥在主线程创建，任何线程 emit 都经 QueuedConnection 落回主线程。
        from app.qt_bridge import MainBridge
        bridge = MainBridge(self)

        def _on_payload(payload):
            kind, value = payload
            if kind == "done":
                _done(value)
            else:
                _err(value)

        bridge.payload.connect(_on_payload)
        self.ctx.threat_feed.refresh(
            cfg_url,
            lambda count: bridge.payload.emit(("done", count)),
            lambda msg: bridge.payload.emit(("err", msg)))

    # ================================================================== #
    # v1.5 加密同步备份
    # ================================================================== #
    def _export_sync(self):
        from PySide6.QtWidgets import QInputDialog
        from app.sync import SyncCollector, encrypt_bundle, LocalFileTransport, SyncError
        pwd, ok = QInputDialog.getText(
            self, "导出同步备份", "设置同步口令（导入时需要）：",
            QLineEdit.Password)
        if not ok or not pwd:
            return
        try:
            payload = SyncCollector(self.ctx).collect()
            blob = encrypt_bundle(payload, pwd)
        except SyncError as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存同步备份", "aegis-sync.absync",
            "Aegis 同步包 (*.absync)")
        if path:
            LocalFileTransport().save(blob, path)
            QMessageBox.information(self, "已导出", f"加密备份已导出：\n{path}")

    def _import_sync(self):
        from PySide6.QtWidgets import QInputDialog
        from app.sync import SyncCollector, decrypt_bundle, LocalFileTransport, SyncError
        path, _ = QFileDialog.getOpenFileName(
            self, "选择同步备份", "", "Aegis 同步包 (*.absync)")
        if not path:
            return
        pwd, ok = QInputDialog.getText(
            self, "导入同步备份", "输入同步口令：", QLineEdit.Password)
        if not ok:
            return
        try:
            blob = LocalFileTransport().load(path)
            payload = decrypt_bundle(blob, pwd)
        except SyncError as e:
            QMessageBox.critical(self, "导入失败", str(e))
            return
        stats = SyncCollector(self.ctx).restore(payload)
        self._rebuild_bookmark_bar()
        QMessageBox.information(
            self, "导入完成",
            f"新增书签 {stats['bookmarks']} 条、阅读清单 {stats['reading']} 条。")

    # ------------------------------------------------------------------ #
    # WebDAV 云同步（B1：把文件导入导出升级为可直接推送到 WebDAV）
    # ------------------------------------------------------------------ #
    def _sync_webdav_push(self):
        """把加密同步包上传到 WebDAV（后台线程，不阻塞 UI）。"""
        from PySide6.QtWidgets import QInputDialog
        from app.sync import (SyncCollector, encrypt_bundle, WebDAVTransport,
                              SyncError, load_webdav_auth)
        url = self.config.sync_webdav_url
        if not url:
            QMessageBox.information(self, "同步",
                                    "未配置 WebDAV 地址（设置 → 同步）。")
            return
        token, password = load_webdav_auth()
        if not token and not password:
            QMessageBox.information(
                self, "同步",
                "未找到 WebDAV 凭证。请设置环境变量 AEGIS_WEBDAV_TOKEN / "
                "AEGIS_WEBDAV_PASSWORD，或写入 ~/.config/aegis/sync.key。")
            return
        pwd, ok = QInputDialog.getText(
            self, "同步备份", "设置同步口令（拉取时需要）：", QLineEdit.Password)
        if not ok or not pwd:
            return
        self.status.showMessage("正在同步到 WebDAV…")
        user = self.config.sync_webdav_user

        def _worker():
            try:
                payload = SyncCollector(self.ctx).collect()
                blob = encrypt_bundle(payload, pwd)
                WebDAVTransport(url, user, password, token).save(blob)
                _bridge(True, "同步成功（书签/阅读清单/设置已加密上传）")
            except SyncError as e:
                _bridge(False, str(e))
            except Exception as e:
                _bridge(False, f"同步失败：{e}")

        def _bridge(ok, msg):
            bridge.payload.emit((ok, msg))

        # v2.1.2 修复：同 _refresh_threat_feed——worker 线程里调
        # QTimer.singleShot 会静默丢失，统一走 MainBridge 回主线程。
        from app.qt_bridge import MainBridge
        bridge = MainBridge(self)
        bridge.payload.connect(
            lambda p: self._on_sync_done(p[0], p[1], False))

        import threading
        threading.Thread(target=_worker, daemon=True).start()

    def _sync_webdav_pull(self):
        """从 WebDAV 拉取并合并加密同步包（后台线程）。"""
        from PySide6.QtWidgets import QInputDialog
        from app.sync import (SyncCollector, decrypt_bundle, WebDAVTransport,
                              SyncError, load_webdav_auth)
        url = self.config.sync_webdav_url
        if not url:
            QMessageBox.information(self, "同步",
                                    "未配置 WebDAV 地址（设置 → 同步）。")
            return
        token, password = load_webdav_auth()
        pwd, ok = QInputDialog.getText(
            self, "同步备份", "输入同步口令：", QLineEdit.Password)
        if not ok:
            return
        self.status.showMessage("正在从 WebDAV 拉取…")
        user = self.config.sync_webdav_user

        def _worker():
            try:
                blob = WebDAVTransport(url, user, password, token).load()
                payload = decrypt_bundle(blob, pwd)
                stats = SyncCollector(self.ctx).restore(payload)
                _bridge(True, f"拉取成功：新增书签 {stats['bookmarks']} 条、"
                              f"阅读清单 {stats['reading']} 条")
            except SyncError as e:
                _bridge(False, str(e))
            except Exception as e:
                _bridge(False, f"拉取失败：{e}")

        def _bridge(ok, msg):
            bridge.payload.emit((ok, msg))

        # v2.1.2 修复：同上，worker 线程回调经 MainBridge 回主线程。
        from app.qt_bridge import MainBridge
        bridge = MainBridge(self)
        bridge.payload.connect(
            lambda p: self._on_sync_done(p[0], p[1], True))

        import threading
        threading.Thread(target=_worker, daemon=True).start()

    def _on_sync_done(self, ok, msg, refresh):
        if ok:
            self.status.showMessage(msg, 6000)
            QMessageBox.information(self, "同步", msg)
            if refresh:
                self._rebuild_bookmark_bar()
        else:
            self.status.showMessage(msg, 6000)
            QMessageBox.warning(self, "同步", msg)

    # ================================================================== #
    # 内存优化：后台标签休眠（标准 #6）
    # ================================================================== #
    _GROUP_COLORS = ("#ff453a", "#ff9f0a", "#ffd60a", "#30d158",
                     "#64d2ff", "#0a84ff", "#bf5af2", "#ff375f")

    def _check_hibernation(self):
        """每分钟扫描：后台空闲超阈值的标签置为 Discarded 回收内存。"""
        import time
        mins = self.config.hibernate_background_mins
        if mins <= 0:
            return
        now = time.time()
        threshold = mins * 60
        current = self.tabs.currentWidget()
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if tab is None or tab is current:
                continue
            if now - getattr(tab, "last_active", now) < threshold:
                continue
            if tab.can_hibernate() and tab.hibernate():
                self.tabbar.set_loading(i, False)

    def _group_color(self, name: str):
        """分组名 → 稳定颜色；空名返回 None（无分组）。"""
        if not name:
            return None
        from PySide6.QtGui import QColor
        idx = sum(ord(c) for c in name) % len(self._GROUP_COLORS)
        return QColor(self._GROUP_COLORS[idx])

    def _edit_group(self, index):
        """设置/清除标签分组（标准 #25 高级标签管理）。"""
        from PySide6.QtWidgets import QInputDialog
        tab = self.tabs.widget(index)
        if not tab:
            return
        name, ok = QInputDialog.getText(
            self, "标签分组", "分组名称（留空=移除分组）：",
            text=getattr(tab, "group", ""))
        if ok:
            tab.group = name.strip()
            self._sync_tabbar()

    # ================================================================== #
    # 站点权限（标准 #14：摄像头/麦克风/位置/通知）
    # ================================================================== #
    def _on_permission_requested(self, url, feature):
        from PySide6.QtWebEngineCore import QWebEnginePage
        host = self.ctx.permissions.host_of(url.toString()
                                            if hasattr(url, "toString") else url)
        decision = self.ctx.permissions.decision(host, feature)
        if decision == "allow":
            self._apply_permission(url, feature, QWebEnginePage.PermissionGrantedByUser)
            return
        if decision == "deny":
            self._apply_permission(url, feature, QWebEnginePage.PermissionDeniedByUser)
            return
        # S-5：本次会话内的临时许可（不落盘，退出即失效）
        session = getattr(self, "_session_permissions", None)
        if session is None:
            session = self._session_permissions = set()
        skey = (host, self.ctx.permissions._feat_key(feature))
        if skey in session:
            self._apply_permission(url, feature, QWebEnginePage.PermissionGrantedByUser)
            return
        # ask：弹窗询问
        name = self.ctx.permissions.feat_name(feature)
        box = QMessageBox(QMessageBox.Question, "权限请求",
                          f"网站 {host} 请求使用：{name}")
        once = box.addButton("允许此次", QMessageBox.AcceptRole)
        allow = box.addButton("始终允许", QMessageBox.AcceptRole)
        deny = box.addButton("拒绝", QMessageBox.RejectRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked in (once, allow):
            self._apply_permission(url, feature, QWebEnginePage.PermissionGrantedByUser)
        else:
            self._apply_permission(url, feature, QWebEnginePage.PermissionDeniedByUser)
        # 记住选择：仅"始终允许"/"拒绝"落盘；"允许此次"只在本会话内记忆
        if clicked == once:
            if host:
                session.add(skey)
        elif clicked in (allow, deny):
            self.ctx.permissions.set_decision(
                host, feature, "allow" if clicked == allow else "deny")

    def _apply_permission(self, url, feature, policy):
        tab = self.current_tab()
        page = getattr(tab, "page", None) if tab else None
        if page is not None:
            page.setFeaturePermission(url, feature, policy)

    # ================================================================== #
    # 自动更新（标准 #13）
    # ================================================================== #
    def _wire_updater(self):
        self.ctx.updater.update_available.connect(self._on_update_available)
        self.ctx.updater.check_failed.connect(
            lambda msg: self.status.showMessage(msg, 6000))
        self.ctx.updater.download_finished.connect(self._on_update_downloaded)

    def _check_update(self):
        if not self.ctx.updater.enabled():
            QMessageBox.information(
                self, "检查更新",
                "尚未配置更新源。\n在 config.json 中设置 update_url "
                "（manifest.json 地址）后启用自动更新。")
            return
        self.status.showMessage("正在检查更新…")
        self.ctx.updater.check()

    def _on_update_available(self, manifest):
        ver = manifest.get("version", "")
        notes = manifest.get("notes", "")
        box = QMessageBox(QMessageBox.Information, "发现新版本",
                          f"Aegis {ver} 可用（当前 "
                          f"{__import__('app.version', fromlist=['APP_VERSION']).APP_VERSION}）\n\n"
                          f"{notes}\n\n是否立即下载安装包？")
        dl = box.addButton("下载", QMessageBox.AcceptRole)
        box.addButton("稍后", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == dl:
            self.status.showMessage("正在下载更新包…")
            self.ctx.updater.download(manifest)

    def _on_update_downloaded(self, path):
        QMessageBox.information(
            self, "下载完成",
            f"更新包已下载并校验通过：\n{path}\n\n关闭浏览器后运行该安装包即可完成更新。")

    # ================================================================== #
    # 导航
    # ================================================================== #
    def _navigate(self, url: str):
        # HSTS 预加载：对名单内主机，http:// 自动升级为 https://
        url = maybe_upgrade(url, self.ctx.data_dir)
        tab = self.current_tab()
        if tab:
            tab.load_url(url)

    def _back(self):
        t = self.current_tab()
        if t:
            t.back()

    def _forward(self):
        t = self.current_tab()
        if t:
            t.forward()

    def _reload(self):
        t = self.current_tab()
        if t:
            if t.is_loading:
                t.stop()
            else:
                t.reload_page()

    def _refresh_nav(self):
        t = self.current_tab()
        if t:
            self.btn_back.setEnabled(t.can_back())
            self.btn_forward.setEnabled(t.can_forward())
        self._sync_address()

    def _sync_address(self):
        t = self.current_tab()
        if not t:
            return
        url = t.url()
        if url and not url.startswith(("about:", "aegis://", "reader:")):
            self.address.setText(url)
        else:
            # 伪页面（新标签页/阅读模式等）清空地址栏，避免显示陈旧地址
            self.address.setText("")
        # 站点安全指示
        self._update_security(url)
        # 收藏状态
        self.btn_star.setIcon(
            icon("star" if self.ctx.bookmarks.contains(url) else "star_outline"))

    def _update_security(self, url: str):
        url = url or ""
        if url.startswith("https://"):
            self.sec_label.setPixmap(icon("lock").pixmap(16, 16))
            self.sec_label.setToolTip("已通过 HTTPS 加密连接")
        elif url.startswith("http://"):
            self.sec_label.setPixmap(icon("warning").pixmap(16, 16))
            self.sec_label.setToolTip("连接未加密（HTTP），存在被窃听风险")
            self.sec_label.setStyleSheet("")
        else:
            self.sec_label.clear()
            self.sec_label.setToolTip("站点连接安全性")

    def _on_progress(self, p):
        # 仅更新标签栏加载动画 + 状态栏进度；不在每个进度点做 DB 查询
        tab = self.sender()
        index = self.tabs.indexOf(tab) if tab else -1
        if index >= 0:
            self.tabbar.set_loading(index, 0 < p < 100)
        if index == self.tabs.currentIndex():
            if 0 < p < 100:
                self.progress_label.setText(f"加载 {p}%")
        if p >= 100:
            self.progress_label.clear()
            self._refresh_nav()

    def _on_link_hovered(self, url):
        """鼠标悬停链接时状态栏提示（类 Chrome 行为）。"""
        if url:
            self.status.showMessage(url)
        else:
            self.status.clearMessage()

    def _on_finished(self, tab):
        self._refresh_nav()
        self._sync_address()
        # B2：页面加载完成时更新当前标签缩略图缓存
        try:
            self.tabs.capture_current_thumb()
        except Exception:
            pass
        # 应用该站点的缩放记忆
        if self.config.zoom_map:
            from urllib.parse import urlparse
            host = urlparse(tab.url()).netloc
            z = self.config.zoom_map.get(host)
            if z:
                tab.view.setZoomFactor(z)

    def _zoom(self, step):
        t = self.current_tab()
        if t:
            if step > 0:
                t.zoom_in()
            elif step < 0:
                t.zoom_out()
            else:
                t.zoom_reset()
            # 记录该站点缩放（站点级记忆）
            from urllib.parse import urlparse
            host = urlparse(t.url()).netloc
            if host:
                self.config.zoom_map[host] = round(t.zoom_factor(), 2)

    def _copy(self):
        # v2.1.2 修复：无当前标签时不再抛 AttributeError。
        t = self.current_tab()
        if t is None:
            return
        t.view.page().triggerAction(t.view.page().Copy)

    def _paste(self):
        t = self.current_tab()
        if t is None:
            return
        t.view.page().triggerAction(t.view.page().Paste)

    def _on_download_requested(self, download):
        """下载请求：危险类型二次确认，按设置询问保存位置或直接保存。"""
        # v1.4 M7 修复：可执行/脚本类下载必须显式确认
        from app.security import is_dangerous_download
        from app.download_manager import _dl_suggested
        suggested = _dl_suggested(download) or \
            download.url().toString().split("/")[-1] or "download"
        if is_dangerous_download(suggested):
            box = QMessageBox(QMessageBox.Warning, "安全警告",
                              f"即将下载的文件「{suggested}」属于可执行/脚本类型，"
                              "运行后可能损害你的计算机或数据。\n\n确定要下载吗？")
            keep = box.addButton("仍然下载", QMessageBox.RejectRole)
            cancel = box.addButton("取消下载", QMessageBox.AcceptRole)
            box.setDefaultButton(cancel)
            box.exec()
            if box.clickedButton() != keep:
                try:
                    download.cancel()
                except Exception:
                    pass
                return
        explicit = ""
        if self.config.ask_download_location:
            default_dir = (self.config.download_dir
                           or os.path.join(os.path.expanduser("~"), "Downloads"))
            os.makedirs(default_dir, exist_ok=True)
            path, _ = QFileDialog.getSaveFileName(
                self, "保存下载", os.path.join(default_dir, suggested))
            if not path:
                # 用户取消：取消下载
                try:
                    download.cancel()
                except Exception:
                    pass
                return
            explicit = path
        self.ctx.downloads.on_download(download, explicit)

    # ================================================================== #
    # 查找
    # ================================================================== #
    def _show_find(self):
        self._position_findbar()
        self.find_bar.show_bar()
        # 丝滑滑入（OutCubic）
        target = self.find_bar.geometry()
        anim = QPropertyAnimation(self.find_bar, b"pos", self)
        anim.setDuration(260)
        anim.setStartValue(QPoint(target.x(), target.y() - target.height() - 12))
        anim.setEndValue(target.topLeft())
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QAbstractAnimation.DeleteWhenStopped)

    def _position_findbar(self):
        # 放在工具栏下方
        if hasattr(self, "find_bar"):
            self.find_bar.setGeometry(0, 40, self.width(),
                                      self.find_bar.sizeHint().height())
            self.find_bar.raise_()

    def _do_find(self, text, flags):
        t = self.current_tab()
        if t:
            t.view.findText(text, flags)

    def _clear_find(self):
        t = self.current_tab()
        if t:
            t.view.findText("")
        bar = self.find_bar
        if not bar.isVisible():
            return
        geo = bar.geometry()
        anim = QPropertyAnimation(bar, b"pos", self)
        anim.setDuration(220)
        anim.setStartValue(geo.topLeft())
        anim.setEndValue(QPoint(geo.x(), -geo.height() - 12))
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.finished.connect(lambda: bar.setVisible(False))
        anim.start(QAbstractAnimation.DeleteWhenStopped)

    # ================================================================== #
    # 书签
    # ================================================================== #
    def _toggle_bookmark(self):
        t = self.current_tab()
        if not t:
            return
        url = t.url()
        if not url or url.startswith(("about:", "aegis://")):
            return
        if self.ctx.bookmarks.contains(url):
            self.ctx.bookmarks.remove(url)
        else:
            self.ctx.bookmarks.add(t.title() or url, url)
        self._sync_address()
        self._rebuild_bookmark_bar()

    def _rebuild_bookmark_bar(self):
        """书签变更（收藏/删除/导入）后刷新书签栏。"""
        self.bookmark_bar.refresh()
        self._bm_toolbar.setVisible(self.config.show_bookmark_bar)
        if hasattr(self, "_bookmarks_menu_rebuild"):
            self._bookmarks_menu_rebuild()

    # v2.1.2 修复：此处原有两个与文件后部完全重复的方法定义
    # （_export_bookmarks / _import_bookmarks，Python 只保留后定义者）。
    # 死代码已移除，避免读者误判生效实现；真正入口见文件后部同名方法。

    # ================================================================== #
    # 窗口 / 数据管理
    # ================================================================== #
    def _new_window(self):
        from main import create_window
        create_window(incognito=False, profile_name="default")

    def _new_incognito(self):
        from main import create_window
        create_window(incognito=True, profile_name="incognito")

    def _show_download_bar(self):
        """显示下载面板（Ctrl+J）。"""
        if hasattr(self, "download_bar"):
            self.download_bar.setVisible(True)

    def _open_bookmark_manager(self):
        """打开书签管理器（书签菜单 → 书签管理…）。"""
        dlg = BookmarkManagerDialog(self, self)
        self._fade_in_popup(dlg)
        dlg.exec()

    def _open_history(self):
        dlg = HistoryDialog(self, self)
        self._fade_in_popup(dlg)
        dlg.exec()

    def _open_passwords(self):
        dlg = PasswordDialog(self, self)
        self._fade_in_popup(dlg)
        dlg.exec()

    def _open_dial_manager(self):
        """v2.1.5：自定义首页拨号（新标签页快捷图标）。"""
        dlg = DialsDialog(self, self)
        self._fade_in_popup(dlg)
        dlg.exec()

    def _open_task_manager(self):
        from .task_manager import TaskManagerDialog
        TaskManagerDialog(self, self).exec()

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self,
                             perm_store=self.ctx.permissions)
        if dlg.exec():
            self.apply_theme()
            # 设置项"真正生效"（此前版本这些开关保存后并不接线）
            self.ctx.adblock.set_enabled(self.config.adblock)
            self.ctx.safe_browsing.enabled = self.config.safe_browsing
            self.ctx.apply_network()
            self._rebuild_bookmark_bar()
            # v2.1.5：标签栏位置 / NTP 壁纸即时生效
            self._apply_tab_placement()
            # 休眠策略即时调整
            if self.config.hibernate_background_mins > 0:
                self._hib_timer.start()
            else:
                self._hib_timer.stop()
            self.ctx.save_config()
            QMessageBox.information(
                self, "已保存", "设置已保存并生效")

    # v2.1.2 修复：此处原有 _clear_data 的第一份定义（仅弹两次简单确认、
    # 且文案声称一并清密码与实际流程不符）。Python 仅保留后定义者，
    # 属死代码且易误导阅读，已移除；真正入口见文件后部 ClearBrowsingData 版。


    def _print_pdf(self):
        t = self.current_tab()
        if not t:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "打印为 PDF", "page.pdf", "PDF (*.pdf)")
        if path:
            t.print_pdf(path)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _reader_mode(self):
        """阅读模式：提取正文并新标签展示。"""
        t = self.current_tab()
        if not t:
            return
        from .reader import extract_reader_js, build_reader_html
        # 提前捕获标题/URL，避免 JS 回调时标签已被关闭
        fallback_title = t.title() or ""
        fallback_url = t.url() or ""
        accent = self.config.accent_color

        def on_extracted(json_str):
            try:
                import json
                data = json.loads(json_str or "null") or {}
                if not isinstance(data, dict):
                    raise ValueError
            except Exception:
                data = {"title": fallback_title, "url": fallback_url,
                        "body": ""}
            html = build_reader_html(data, accent)
            # 直接开空白标签承载，避免先导航再 setHtml 的竞态
            new_tab = self.new_tab(switch=True)
            new_tab.view.setHtml(html, QUrl("reader://" + data.get("url", "")))
            self.tabs.setTabText(self.tabs.indexOf(new_tab),
                                 "阅读：" + (data.get("title") or "")[:20])

        t.run_js(extract_reader_js(), on_extracted)

    def _open_security_dashboard(self):
        """打开安全态势仪表盘（超越项：让用户看见真实的防护状态）。"""
        SecurityDashboard(self.ctx, self).exec()

    def _open_view_source(self):
        """查看源代码（Ctrl+U / 右键菜单）。

        对标商业浏览器：展示当前标签渲染后 DOM 的序列化 HTML。
        通过 QWebEnginePage.toHtml 异步获取，对话框非模态弹出。
        """
        t = self.current_tab()
        if not t or not getattr(t, "page", None):
            return
        dlg = ViewSource(self, self)
        dlg.set_source_url(t.url())
        dlg.show()
        # 异步获取 DOM HTML；完成回调填入对话框（PySide 会持有 bound 方法
        # 引用直到回调执行，对话框不会被提前回收）
        try:
            t.page.toHtml(dlg.set_html)
        except Exception:
            dlg.set_html("")

    # ------------------------------------------------------------------ #
    # 命令面板 / 站点信息 / 强制深色 / 清除数据（对标 + 超标）
    # ------------------------------------------------------------------ #
    def _fade_in_popup(self, widget, duration: int = 170):
        """U-5：为弹层/对话框加入柔和淡入（Apple 风 OutCubic，不做弹跳）。

        在 show/exec 之前调用：先把窗口不透明度归零，动画随事件循环推进，
        避免弹层"啪"地瞬间出现。动画随弹层一同析构，重复调用安全。
        """
        widget.setWindowOpacity(0.0)
        anim = QPropertyAnimation(widget, b"windowOpacity", widget)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QAbstractAnimation.DeleteWhenStopped)

    def _open_command_palette(self):
        """命令面板（Ctrl+Shift+P）：键盘可达的高频操作入口（超标对标）。"""
        dlg = CommandPalette(self, self)
        self._fade_in_popup(dlg)
        dlg.exec()

    def _open_site_info(self):
        """站点信息 / 证书查看器：对标商业浏览器的锁形详情。"""
        t = self.current_tab()
        if not t:
            return
        SiteInfo(self.ctx, t, self).exec()

    def _open_site_permissions(self):
        """站点权限清单（S-5 配套）：查看并撤销各站点的权限记忆。

        对标 Chrome「站点信息 → 撤销权限」：撤销即调用
        PermissionStore.forget，站点下次请求时重新询问。
        """
        dlg = PermissionsDialog(self.ctx.permissions, self)
        self._fade_in_popup(dlg)
        dlg.exec()

    def _open_devtools(self):
        """打开当前标签的内置开发者工具（QtWebEngine 原生 DevTools UI）。

        本地 UI、不暴露端口——比 devtools_port 远程调试（无鉴权、可读写
        本页 Cookie/DOM）安全得多，日常排障请优先使用本入口。
        """
        t = self.current_tab()
        if not t or not getattr(t, "page", None):
            return
        from PySide6.QtWebEngineWidgets import QWebEngineView
        try:
            dev_page = t.page.devtoolsPage()
        except Exception:
            dev_page = None
        if dev_page is None:
            QMessageBox.information(
                self, "开发者工具",
                "当前环境不支持打开内置开发者工具。")
            return
        win = QWebEngineView()
        win.setPage(dev_page)
        win.setWindowTitle(f"开发者工具 — {t.title() or 'Aegis'}")
        win.resize(900, 620)
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        win.show()
        # 无父对象的 QWebEngineView 需手动持有引用，防止被 GC
        if not hasattr(self, "_devtools_windows"):
            self._devtools_windows = []
        self._devtools_windows.append(win)

    def _open_vision_panel(self):
        """打开 AI 视觉问答面板（截图 → 视觉模型看图回答，设计文档 §6）。"""
        if not getattr(self.config, "vision_enabled", False):
            QMessageBox.information(
                self, "视觉问答",
                "AI 视觉能力未启用。请在 设置 → AI 中开启并配置模型。")
            return
        from .vision_panel import VisionPanel
        dlg = VisionPanel(self, self)
        self._fade_in_popup(dlg)
        dlg.exec()

    def _open_computer_use(self):
        """打开 AI 上网代理面板（模式 B：截图→决策→执行闭环，设计文档 §7）。"""
        if not getattr(self.config, "vision_enabled", False):
            QMessageBox.information(
                self, "AI 上网代理",
                "AI 视觉能力未启用。请在 设置 → AI 中开启并配置模型。")
            return
        from .computer_use_panel import ComputerUsePanel
        dlg = ComputerUsePanel(self, self)
        dlg.exec()

    def _toggle_force_dark(self):
        """强制深色模式开/关（超标：类 Dark Reader 的全局反色）。"""
        self.config.force_dark = not self.config.force_dark
        self.ctx.apply_force_dark()
        self.ctx.save_config()
        t = self.current_tab()
        if t:
            t.reload_page()  # 现有页面需重载以套用/移除滤镜
        state = "已开启" if self.config.force_dark else "已关闭"
        QMessageBox.information(
            self, "强制深色模式",
            f"强制深色模式{state}。新开页面立即生效"
            + ("；当前页面已刷新。" if t else "。"))

    def _clear_data(self):
        """清除浏览数据（细粒度对话框，对标商业浏览器隐私清理）。"""
        dlg = ClearBrowsingData(self.ctx, self)
        if dlg.exec() == QDialog.Accepted:
            summary = dlg.apply()
            QMessageBox.information(self, "完成", summary)

    def _stop(self):
        """停止当前页面加载。"""
        t = self.current_tab()
        if t:
            t.stop()

    def _copy_url(self):
        """复制当前标签网址到剪贴板。"""
        t = self.current_tab()
        if t:
            QApplication.clipboard().setText(t.url())

    def _open_translate(self):
        """打开本地 AI 助手面板（翻译 / 双语对照 / 总结 / 提问 / 唤起千问·Kimi）。

        全部走本地 AI（Ollama / LM Studio 等 OpenAI 兼容端点）：
        免费、本地运行、无需 API Key；也兼容云端兼容端点。
        """
        AegisAIPanel(self, self).exec()

    def _open_password_tools(self):
        """打开密码工具（生成强密码 + 本地泄露检测）。"""
        PasswordToolsDialog(self, self).exec()

    def _open_ima_notes(self):
        """打开"保存到 IMA 知识库"对话框（边看网页边存笔记，走 IMA OpenAPI）。"""
        ImaNotesDialog(self, self).exec()

    def _open_ima_kb(self):
        """打开 IMA 知识库浏览器（读取昆仑山等知识库的内容）。"""
        ImaKnowledgeDialog(self, self).exec()

    def _toggle_bookmark_bar(self):
        """书签栏显示/隐藏，并持久化。"""
        self.config.show_bookmark_bar = not self.config.show_bookmark_bar
        self._rebuild_bookmark_bar()
        self.ctx.save_config()

    # ------------------------------------------------------------------ #
    # 网页截图 / 书签导入导出（对标商业浏览器）
    # ------------------------------------------------------------------ #
    def _capture_screenshot(self):
        """网页截图（视口 PNG）。对标商业浏览器的截图功能。"""
        t = self.current_tab()
        if not t or not getattr(t, "view", None):
            return
        pix = t.view.grab()
        if pix.isNull():
            QMessageBox.warning(self, "截图失败", "无法捕获当前页面。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存截图", "screenshot.png", "PNG 图片 (*.png)")
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            if pix.save(path, "PNG"):
                QMessageBox.information(self, "已保存", f"截图已保存：{path}")
            else:
                QMessageBox.warning(self, "保存失败", "截图保存失败。")

    def _import_bookmarks(self):
        """导入 Netscape 书签 HTML（兼容 Chrome/Firefox/Edge 导出格式）。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入书签", "", "HTML 书签 (*.html *.htm)")
        if not path:
            return
        n = self.ctx.bookmarks.import_html(path)
        self._rebuild_bookmark_bar()
        QMessageBox.information(self, "导入完成", f"已导入 {n} 条书签。")

    def _export_bookmarks(self):
        """导出书签为标准 Netscape HTML（可被 Chrome/Firefox/Edge 导入）。"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出书签", "bookmarks.html", "HTML 书签 (*.html)")
        if not path:
            return
        ok = self.ctx.bookmarks.export_html(path)
        QMessageBox.information(
            self, "导出完成",
            "书签已导出为 HTML。" if ok else "导出失败，请检查路径权限。")

    def _about(self):
        from app.version import APP_VERSION, engine_version, pyside_version
        QMessageBox.about(
            self, "关于 Aegis",
            f"<b>Aegis</b> v{APP_VERSION}<br>"
            f"基于 {engine_version()}；运行时 PySide6 {pyside_version()}。<br><br>"
            "多标签 · 书签 · 历史 · 广告拦截 · 安全浏览 · 密码加密 · Apple 玻璃态主题<br>"
            "安全更新采用离线 Ed25519 签名验签 + HTTPS + 可选证书锁定；"
            "HSTS 预加载强升级；WebRTC IP 防泄漏。<br>"
            "<span style='color:#888;'>引擎具体版本由 QtWebEngine 运行时如实报告，"
            "不臆造 Chromium 大版本号。</span>")

    # ================================================================== #
    # 液态玻璃（Windows DWM 毛玻璃）
    # ================================================================== #
    def _enable_glass(self):
        """启用 Windows 原生毛玻璃：窗口透明区域透出系统级模糊。

        仅 Windows 且 PySide6 带 QtWin 时生效；失败则静默降级为普通半透明。
        网页区（QWebEngineView）保持不透明，仅外框（工具栏/标签栏等）呈玻璃。
        """
        try:
            from PySide6.QtWin import QtWin
        except Exception:
            return
        try:
            self.setAttribute(Qt.WA_TranslucentBackground)
            QtWin.enableBlurBehindWindow(self)
        except Exception:
            # 某些环境（无 DWM / 远程桌面）不支持，降级不透明即可
            pass

    # ================================================================== #
    # 主题
    # ================================================================== #
    def apply_theme(self):
        from app.system_theme import resolve_dark
        dark = resolve_dark(self.config.theme)
        # 单一字体家族：QSS 与 QPainter 自绘同源（首次调用时载入随包字体）
        load_app_font()
        # 图标描边跟随明暗，重建已创建的工具栏图标
        set_icon_theme(dark)
        for b, name in getattr(self, "_nav_buttons", []):
            b.setIcon(icon(name))
        self._sync_address()   # 星标/安全图标按新描边色回填
        self.setStyleSheet(style_for(dark, self.config.accent_color,
                                     self.config.font_size))
        self.tabbar.set_theme(dark, self.config.accent_color)
        # 让标签内容区透明以显示背景
        self.tabs.setAttribute(Qt.WA_StyledBackground, True)

    # ================================================================== #
    # 启动
    # ================================================================== #
    def _initial_startup(self):
        mode = self.config.startup_pages

        # 恢复会话逻辑（resume 模式或用户选择）
        if mode in ("resume",) or self.config.resume_session:
            tabs, active = self.ctx.session.load()
            if tabs:
                for i, item in enumerate(tabs):
                    url = item[0]
                    pinned = bool(item[2]) if len(item) > 2 else False
                    group = item[3] if len(item) > 3 else ""
                    t = self.new_tab(url, switch=(i == active),
                                     pinned=pinned)
                    if group:
                        t.group = str(group)
                self._sync_tabbar()
                return
            mode = "homepage"

        # 普通启动，保证至少一个标签页
        if mode == "blank":
            self.new_tab("about:blank")
        elif mode == "speeddial":
            self.new_tab()
        else:
            self.new_tab(self.config.homepage)

    # ================================================================== #
    # 关闭：保存会话
    # ================================================================== #
    def _session_tabs(self) -> list:
        """收集可恢复的标签（过滤 newtab/reader/about 等伪 URL）。"""
        from urllib.parse import urlparse
        tabs = []
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if not tab:
                continue
            u = tab.url()
            if u and not u.startswith(("about:", "aegis:",
                                       "reader:", "data:")):
                tabs.append((u, tab.title(),
                             bool(getattr(tab, "pinned", False)),
                             str(getattr(tab, "group", "") or "")))
        return tabs

    def _autosave_session(self):
        if self.ctx.incognito:
            return
        self.ctx.session.save(self._session_tabs(),
                              self.tabs.currentIndex())

    def closeEvent(self, event):
        if not self.ctx.incognito and self.config.resume_session:
            self.ctx.session.save(self._session_tabs(),
                                  self.tabs.currentIndex())
        self.ctx.save_config()
        super().closeEvent(event)
