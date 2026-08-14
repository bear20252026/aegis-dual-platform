# -*- coding: utf-8 -*-
"""browser_tab.py —— 标签页页面组件。

封装 QWebEngineView，提供加载状态、证书错误处理、右键菜单
（用默认浏览器打开/新标签打开/复制链接/图片）、打印等。
"""

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWidgets import QWidget, QVBoxLayout, QMenu, QApplication, QFileDialog

import json

# 用默认浏览器打开链接（v1.4 L9 修复：仅放行 http/https）
def _open_external(url: str):
    try:
        from app.security import safe_url
        u = safe_url(url, allow_internal=False)
        if not u:
            return
        import webbrowser
        webbrowser.open(u)
    except Exception:
        pass


class BrowserPage(QWebEnginePage):
    """自定义页面：拦截 target=_blank 新窗口请求并交给宿主承载。"""

    # 携带新创建的页面请求宿主挂载到新标签
    new_window = Signal(object)

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.parent_tab = parent

    def createWindow(self, windowType):
        # target=_blank 等新窗口请求：返回一个新页面，并通知宿主为它开标签页
        new_page = BrowserPage(self.profile(), self.parent_tab)
        # 连锁支持：新页面内部再有新窗口请求时继续向宿主传递
        new_page.new_window.connect(self.new_window)
        self.new_window.emit(new_page)
        return new_page

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        """S-1：主框架导航**发起前**做纯内存安全判定。

        种子/用户黑名单与启发式命中的站点在页面加载之前就被拒绝，
        不再等到 loadFinished 之后才补一张拦截页。此处只查内存，
        绝不发起网络 IO（Google 情报源走后台线程，见 BrowserTab）。
        """
        if is_main_frame:
            tab = self.parent_tab
            sb = getattr(tab, "_safe_browsing", None)
            if sb is not None:
                try:
                    u = url.toString()
                    reason = sb.reason(u)
                except Exception:
                    reason = None
                if reason:
                    sb.note_block(u)
                    # 不在导航回调里直接 setHtml（避免重入），下一轮事件循环再换页
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(
                        0, lambda t=tab, a=u, r=reason: t.show_block_page(a, r))
                    return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def certificateError(self, error):
        # 交互式处理 SSL 证书错误。
        # Qt6 API：acceptCertificate()/rejectCertificate()/description()。
        #   用户选"仍要继续" → acceptCertificate() + return True
        #   用户选"不继续"   → rejectCertificate() + return False
        # S-2：HSTS 预加载名单内的主机**没有例外**，不提供"继续"选项。
        try:
            from app.hsts import is_hsts
            host = error.url().host()
        except Exception:
            host, is_hsts = "", None
        if is_hsts is not None and host and is_hsts(host):
            try:
                error.rejectCertificate()
            except Exception:
                pass
            return False
        try:
            from PySide6.QtWidgets import QMessageBox
            desc = error.description()
            box = QMessageBox(QMessageBox.Warning, "连接不安全",
                              "该站点的安全证书存在问题，无法验证其身份：\n\n"
                              f"网址：{error.url().toString()}\n"
                              f"原因：{desc}\n\n"
                              "是否仍要继续访问？（不建议）")
            box.addButton(QMessageBox.Yes)
            box.addButton(QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
            if box.exec() == QMessageBox.Yes and error.isOverridable():
                try:
                    error.acceptCertificate()
                    return True
                except Exception:
                    return False
            try:
                error.rejectCertificate()
            except Exception:
                pass
            return False
        except Exception:
            # 弹窗失败时按最严格处理：拒绝加载
            return False


# 主题解析（auto 主题跟随系统；导入失败回退 dark）
def resolve_theme_dark(config) -> bool:
    try:
        from app.system_theme import resolve_dark
        return resolve_dark(getattr(config, "theme", "dark"))
    except Exception:
        return getattr(config, "theme", "dark") == "dark"


class BrowserTab(QWidget):
    """单标签页（组合 QWebEngineView）。"""

    # 对外信号（由 MainWindow 连接）
    title_changed = Signal(str)
    icon_changed = Signal(QIcon)
    load_progress = Signal(int)
    load_finished = Signal()
    open_link_new_tab = Signal(str)      # 新标签页打开链接
    mute_changed = Signal(bool)          # 静音状态变化
    host_page = Signal(object)           # 承载一个已创建的 page 到新标签
    link_hovered = Signal(str)           # 鼠标悬停链接（状态栏提示）
    permission_requested = Signal(object, int)  # (url, feature) 权限请求
    view_source_requested = Signal()    # 请求“查看源代码”（由主窗口承接）

    def __init__(self, profile: QWebEngineProfile, config, parent=None,
                 page=None):
        QWidget.__init__(self, parent)
        self.config = config
        self._progress = 0
        self.is_loading = False
        self.pinned = False
        self.muted = False
        self.group = ""            # 标签分组名（空=未分组）
        self.discarded = False     # 休眠(Discarded)状态标记
        import time as _time
        self.last_active = _time.time()   # 最近活动时刻（休眠判定）

        self.view = QWebEngineView(self)
        self.page = page or BrowserPage(profile, self)
        # 承载已创建的 page（target=_blank）时同样把宿主指向本标签，
        # 保证导航前的安全判定拿得到本标签注入的 SafeBrowsing。
        self.page.parent_tab = self
        self.view.setPage(self.page)
        self._safe_browsing = None
        self._sb_checker = None      # Google 情报源后台查询器（可能为 None）
        self._http_fallback_done = ""

        # 信号转发
        self.view.titleChanged.connect(self.title_changed.emit)
        self.view.iconChanged.connect(self.icon_changed.emit)
        self.view.loadProgress.connect(self._on_progress)
        self.view.loadFinished.connect(self._on_finished)

        # 新窗口请求：交给宿主开新标签
        self.page.new_window.connect(self.host_page.emit)

        # 悬停链接转发到状态栏
        self.page.linkHovered.connect(self.link_hovered.emit)

        # 站点权限请求（摄像头/麦克风/位置/通知）转发给主窗口裁决
        self.page.featurePermissionRequested.connect(
            self.permission_requested.emit)

        # 渲染进程崩溃恢复（对标 Chrome"页面崩溃"）：不同 PySide6 构建
        # 的信号名称可能不同，用 try 兼容，缺失时静默跳过。
        try:
            self.page.renderProcessTerminated.connect(
                self._on_render_crashed)
        except (AttributeError, TypeError):
            pass

        # 右键菜单
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._context_menu)

        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.view)
        self.setLayout(layout)

    # ------------------------------------------------------------------ #
    def _on_render_crashed(self, status, exit_code):
        """渲染进程崩溃 → 展示崩溃恢复页（对标 Chrome"页面崩溃"）。

        恢复按钮用普通 <a href> 指向崩溃前的真实 URL：走 QtWebEngine
        正常导航流程重启渲染进程，无任何内联 JS 注入面。
        """
        try:
            name = getattr(status, "name", None) or str(status)
        except Exception:
            name = str(status)
        if name not in ("CrashedTerminationStatus", "KilledTerminationStatus",
                        "AbnormalTerminationStatus"):
            return
        try:
            import html as html_mod
            dark = resolve_theme_dark(self.config)
            # 崩溃前的真实 URL（用于恢复按钮；伪页面无恢复价值）
            try:
                reload_url = self.view.url().toString()
            except Exception:
                reload_url = ""
            if not reload_url or reload_url.startswith(
                    ("about:", "aegis:", "data:")):
                reload_url = ""
            bg = "#000000" if dark else "#f5f5f7"
            fg = "#ffffff" if dark else "#1d1d1f"
            sub = "rgba(255,255,255,0.6)" if dark else "rgba(0,0,0,0.6)"
            btn = ""
            if reload_url:
                href = html_mod.escape(reload_url, quote=True)
                btn = f'<a class="btn" href="{href}">重新加载</a>'
            html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
body{{margin:0;height:100vh;display:flex;align-items:center;
justify-content:center;font-family:'SF Pro Display','Helvetica Neue',
'Segoe UI','Microsoft YaHei',sans-serif;background:{bg};color:{fg};
text-align:center;}}
.card{{max-width:460px;padding:40px;}}
h1{{font-size:26px;font-weight:600;line-height:1.14;margin:0 0 10px;}}
p{{color:{sub};font-size:15px;line-height:1.55;}}
.btn{{display:inline-block;margin-top:22px;padding:9px 24px;
border-radius:980px;background:#0071e3;color:#fff;text-decoration:none;
font-size:15px;}}
</style></head><body><div class="card">
<h1>页面崩溃了</h1>
<p>渲染进程意外退出，页面已停止响应。</p>
{btn}
</div></body></html>"""
            self.view.setHtml(html, QUrl("aegis://crash"))
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def _on_progress(self, p):
        self._progress = p
        self.is_loading = 0 < p < 100
        self.load_progress.emit(p)

    def _on_finished(self, ok):
        self._progress = 100
        self.is_loading = False
        import time as _time
        self.last_active = _time.time()
        self.load_finished.emit()
        url = self.view.url().toString()
        # 安全浏览：内存判定已在导航前完成；这里只兜底（如页内跳转）
        # 并触发需要网络的情报源的**后台**查询（标准 #11）
        sb = getattr(self, "_safe_browsing", None)
        if sb and url and sb.is_blocked(url):
            self.show_block_page(url)
            return
        if url and not url.startswith(("about:", "aegis:", "data:")):
            checker = getattr(self, "_sb_checker", None)
            if checker is not None:
                checker.check(url)      # 立即返回，结果经信号异步回来
        # 加载失败：先尝试一次 http 回退（仅限地址栏自动升级的裸域名）
        if not ok and url and not url.startswith(("about:", "aegis:", "data:")):
            if self._try_http_fallback(url):
                return
        # 加载失败：展示友好错误页
        if not ok and url and not url.startswith(("about:", "aegis:", "data:")):
            try:
                from .error_pages import build_error_html
                dark = resolve_theme_dark(self.config)
                self.view.setHtml(build_error_html(url, dark=dark), QUrl(url))
            except Exception:
                pass
            return
        # 记录历史
        if url and not url.startswith(("about:", "aegis:", "data:")):
            self._record_history(url, self.view.title())

    def _record_history(self, url, title):
        # 由 MainWindow 注入的 history 存储（避免循环依赖）
        h = getattr(self, "_history_store", None)
        if h is not None:
            h.add(url, title)

    def set_history_store(self, store):
        self._history_store = store

    def set_safe_browsing(self, sb):
        """注入安全浏览判定器（由 MainWindow 在创建后调用）。"""
        self._safe_browsing = sb
        old = getattr(self, "_sb_checker", None)
        if old is not None:
            old.stop()
        self._sb_checker = None
        if sb is not None and hasattr(sb, "make_async_checker"):
            try:
                checker = sb.make_async_checker(self)
            except Exception:
                checker = None
            if checker is not None:
                checker.checked.connect(self._on_async_sb_result)
                self._sb_checker = checker

    def _on_async_sb_result(self, url: str, reason: str):
        """后台情报源（Google）判定结果回主线程后再决定是否拦截。"""
        if not reason:
            return
        sb = getattr(self, "_safe_browsing", None)
        if sb is None:
            return
        sb.note_block(url)
        if self.view.url().toString() != url:
            return      # 用户已离开该页，不再打断
        self.show_block_page(url, reason)

    def show_block_page(self, url: str, reason: str = ""):
        """把当前页替换为安全拦截页。"""
        sb = getattr(self, "_safe_browsing", None)
        if sb is None:
            return
        try:
            # R7：安全拦截事件审计（记录域名，不记完整 URL）
            from urllib.parse import urlparse
            from app.security_audit import audit
            audit(getattr(sb, "data_dir", ""), "sb_blocked",
                  urlparse(url).hostname or "", "blocked")
        except Exception:
            pass
        try:
            dark = resolve_theme_dark(self.config)
            self.view.setHtml(sb.block_page_html(url, dark=dark, reason=reason),
                              QUrl("aegis://blocked"))
        except Exception:
            pass

    def _try_http_fallback(self, url: str) -> bool:
        """S-6/R4：地址栏自动补全的裸域名 https 失败时，回退一次 http。

        仅对本进程内由 parse_input 自动升级过的地址生效，且 HSTS 主机
        永不降级；用户手动输入的 https:// 也不会被降级。
        https_first_mode=strict（R4）时禁止任何回退，仅保留警示。
        """
        if getattr(self, "_http_fallback_done", "") == url:
            return False
        if getattr(self.config, "https_first_mode", "balanced") == "strict":
            return False
        try:
            from app.search_engines import http_fallback
            fb = http_fallback(url)
        except Exception:
            return False
        if not fb:
            return False
        self._http_fallback_done = url
        self.view.setUrl(QUrl(fb))
        return True

    # ------------------------------------------------------------------ #
    # 后台标签休眠（标准 #6 内存优化；Qt 5.15 Page Lifecycle API）
    # ------------------------------------------------------------------ #
    def can_hibernate(self) -> bool:
        """可休眠条件：非当前标签、非固定、无音频、有真实 URL。"""
        try:
            if self.pinned or self.is_loading or self.discarded:
                return False
            # 音频检测（部分 PyQtWebEngine 版本无 recentlyAudited，降级为不检测）
            audited = getattr(self.page, "recentlyAudited", None)
            if callable(audited):
                try:
                    if audited():
                        return False
                except Exception:
                    pass
            u = self.view.url().toString()
            return bool(u) and not u.startswith(("about:", "aegis:",
                                                 "reader:"))
        except Exception:
            return False

    def hibernate(self) -> bool:
        """把渲染进程置为 Discarded 以回收内存。成功返回 True。

        Qt 生命周期要求：可见页不能 Active→Discarded 直跳，
        需先 Active→Frozen→Discarded 逐级迁移。
        """
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage
            lc = QWebEnginePage.LifecycleState
            if not hasattr(self.page, "setLifecycleState"):
                return False
            try:
                self.page.setLifecycleState(lc.Discarded)
            except Exception:
                self.page.setLifecycleState(lc.Frozen)
                self.page.setLifecycleState(lc.Discarded)
            self.discarded = True
            return True
        except Exception:
            return False

    def wake(self) -> bool:
        """恢复被休眠的标签（重新加载原 URL）。"""
        if not self.discarded:
            return False
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage
            lc = QWebEnginePage.LifecycleState
            if hasattr(self.page, "setLifecycleState"):
                self.page.setLifecycleState(lc.Active)
            u = self.view.url().toString()
            if u and not u.startswith("aegis:"):
                self.view.setUrl(QUrl(u))
            self.discarded = False
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # 对外接口
    # ------------------------------------------------------------------ #
    def load_url(self, url: str):
        # v1.4 M3 修复：统一导航关口，scheme 白名单过滤
        # （拒绝 file:/javascript:/vbscript:/chrome: 等）
        from app.security import safe_url
        u = safe_url(url)
        if not u:
            return
        self.view.setUrl(QUrl(u))

    def url(self) -> str:
        return self.view.url().toString()

    def title(self) -> str:
        return self.view.title()

    def back(self):
        self.view.back()

    def forward(self):
        self.view.forward()

    def reload_page(self):
        self.view.reload()

    def stop(self):
        self.view.stop()

    def can_back(self) -> bool:
        return self.view.history().canGoBack()

    def can_forward(self) -> bool:
        return self.view.history().canGoForward()

    def zoom_in(self):
        self.view.setZoomFactor(self.view.zoomFactor() + 0.2)

    def zoom_out(self):
        self.view.setZoomFactor(max(0.3, self.view.zoomFactor() - 0.2))

    def zoom_reset(self):
        self.view.setZoomFactor(self.config.default_zoom)

    def set_muted(self, muted: bool):
        self.muted = muted
        try:
            self.page.setAudioMuted(muted)
        except Exception:
            pass
        self.mute_changed.emit(muted)

    def is_muted(self) -> bool:
        return self.muted

    def zoom_factor(self):
        return self.view.zoomFactor()

    def find(self, text: str, backward=False):
        self.view.findText(text, backward=backward)

    def find_clear(self):
        self.view.findText("")

    def print_pdf(self, path: str):
        self.page.printToPdf(path)

    def to_plain_text(self):
        self.page.toPlainText()

    def run_js(self, script: str, callback=None):
        if callback is not None:
            self.page.runJavaScript(script, callback)
        else:
            self.page.runJavaScript(script)

    # ------------------------------------------------------------------ #
    # 右键菜单。Qt6 移除了 hitTestContent()，改用 JS elementFromPoint 探测
    # 光标下的链接/图片/选区（异步回调后构建菜单）。
    _HITTEST_JS = r"""
    (function(){
      try {
        var el = document.elementFromPoint(%(x)d, %(y)d);
        var link = "", image = "", selected = "";
        if (el) {
          var a = el.closest ? el.closest('a') : null;
          if (a) link = a.href || "";
          var img = (el.tagName === 'IMG') ? el
                    : (el.closest ? el.closest('img') : null);
          if (img) image = img.src || "";
        }
        try { selected = window.getSelection().toString(); } catch (e) {}
        return JSON.stringify({link: link, image: image, selected: selected});
      } catch (e) {
        return JSON.stringify({link: "", image: "", selected: ""});
      }
    })();
    """

    def _context_menu(self, pos):
        """页面右键菜单（异步探测后构建）。"""
        script = self._HITTEST_JS % {"x": pos.x(), "y": pos.y()}

        def _on_result(raw):
            info = {}
            try:
                info = json.loads(raw) if raw else {}
            except Exception:
                info = {}
            link = info.get("link", "")
            image = info.get("image", "")
            selected = info.get("selected", "")
            self._build_context_menu(link, image, selected, pos)

        self.run_js(script, _on_result)

    def _build_context_menu(self, link_url, image_url, selected, pos):
        menu = QMenu(self)

        if link_url:
            menu.addAction("在新标签页打开",
                           lambda: self.open_link_new_tab.emit(link_url))
            menu.addAction("复制链接地址", lambda: self._copy(link_url))
            menu.addAction("用默认浏览器打开",
                           lambda: _open_external(link_url))
            menu.addSeparator()
        if image_url:
            menu.addAction("复制图片地址", lambda: self._copy(image_url))
            menu.addSeparator()
        if selected:
            menu.addAction("复制", lambda: self._copy(selected))
            menu.addSeparator()
        menu.addAction("后退", self.back).setEnabled(self.can_back())
        menu.addAction("前进", self.forward).setEnabled(self.can_forward())
        menu.addAction("刷新", self.reload_page)
        menu.addAction("打印为 PDF", self._print_as_pdf)
        menu.addSeparator()
        menu.addAction("查看源代码", self.view_source_requested.emit)
        menu.exec(self.view.mapToGlobal(pos))

    def _copy(self, text):
        QApplication.clipboard().setText(text)

    def _print_as_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "打印为 PDF", "page.pdf", "PDF (*.pdf)")
        if path:
            self.print_pdf(path)
