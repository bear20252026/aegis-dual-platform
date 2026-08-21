"""browser.py —— 浏览器运行时上下文。

聚合配置、存储、下载、广告拦截等服务，供 UI 层统一访问，
避免 UI 与 app 层散乱耦合。
"""

import os

from PySide6.QtWebEngineCore import QWebEngineProfile

from .adblock import AdBlocker
from .bookmark_store import BookmarkStore
from .config import AppConfig
from .download_manager import DownloadManager
from .history_store import HistoryStore
from .password_store import PasswordStore
from .paths import cache_dir, profile_dir, webengine_dir
from .permissions import PermissionStore
from .safe_browsing import SafeBrowsing
from .search_engines import SearchEngines
from .session import SessionManager


class _EmptyDials:
    """无痕模式的拨号占位：空列表、不写盘。"""

    def all(self):
        return []

    def is_customized(self):
        return False


class BrowserContext:
    """一次浏览器会话的全部服务。"""

    def __init__(self, base_data_dir: str, profile_name: str = "default",
                 incognito: bool = False):
        self.incognito = incognito
        self.base_data_dir = base_data_dir

        # 配置（无痕仍读默认配置，但数据不落盘）
        self.config = AppConfig.load(base_data_dir)
        self.config.incognito = incognito

        # 配置文件的独立数据目录
        self.data_dir = profile_dir(base_data_dir, profile_name)
        self.search = SearchEngines(self.config)

        # 存储
        self.history = HistoryStore(self.data_dir, enabled=not incognito)
        self.bookmarks = BookmarkStore(self.data_dir, enabled=not incognito)
        # v1.4 M1 修复：无痕模式强制禁用密码保存（与无痕承诺一致）
        self.passwords = PasswordStore(
            self.data_dir,
            enabled=self.config.save_passwords and not incognito)
        self.session = SessionManager(self.data_dir, enabled=not incognito)

        # v2.1.5：自定义首页拨号（无痕模式不落盘）
        from .dial_store import DialStore
        self.dials = DialStore(self.data_dir) if not incognito \
            else _EmptyDials()

        # 下载（data_dir 用于下载历史持久化；无痕模式不落盘）
        self.downloads = DownloadManager(self.config, self.data_dir)

        # 广告拦截（无痕也可用），DNT 头由拦截器附加
        self.adblock = AdBlocker()
        self.adblock.set_enabled(self.config.adblock)
        self.adblock.set_dnt(self.config.do_not_track)

        # 安全浏览：恶意/钓鱼站点防护（真实情报源，覆盖度如实上报）
        self.safe_browsing = SafeBrowsing(
            self.data_dir,
            enabled=self.config.safe_browsing,
            provider=self.config.safe_browsing_provider,
            api_key=self.config.safe_browsing_api_key,
        )

        # 站点权限决策（标准 #14）
        self.permissions = PermissionStore(self.data_dir)

        # v1.5 新增能力
        from .logging_setup import setup_logging
        from .reading_list import ReadingList
        from .threat_feed import ThreatFeedUpdater
        from .user_scripts import UserScriptStore
        self.logger = setup_logging(self.data_dir)
        self.reading = ReadingList(self.data_dir)
        self.user_scripts = UserScriptStore(self.data_dir)
        self.threat_feed = ThreatFeedUpdater(self.data_dir)

        # 网络代理等配置应用
        self.apply_network()

        # QtWebEngine 配置（无痕使用离屏配置，不写盘）
        self.profile = self._setup_profile()

        # 自动更新器（标准 #13；update_url 未配置时静默关闭）
        from .updater import UpdateChecker
        self.updater = UpdateChecker(self.config, data_dir=self.data_dir)

    # ------------------------------------------------------------------ #
    def apply_network(self):
        """把网络相关配置真正应用到运行时（此前版本开关保存后不生效）。"""
        from PySide6.QtNetwork import QNetworkProxy, QNetworkProxyFactory
        if self.config.use_system_proxy:
            QNetworkProxyFactory.setUseSystemConfiguration(True)
        else:
            QNetworkProxyFactory.setUseSystemConfiguration(False)
            QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        # DNT 由请求拦截器附加
        self.adblock.set_dnt(self.config.do_not_track)

    def _setup_profile(self) -> QWebEngineProfile:
        # v1.4 L1 修复：如实声明自身身份，不伪装 Chrome 版本号。
        # v2.1.2 修复：无痕 profile 此前漏设 UA，回落为 Chromium 默认 UA，
        # 与"如实 UA"承诺矛盾——统一应用到常规/无痕两种 profile。
        from .version import APP_NAME, APP_VERSION
        honest_ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"{APP_NAME}/{APP_VERSION} Safari/537.36")
        if self.incognito:
            # Qt5：无存储名称构造的 profile 即离屏（不落盘 Cookie/缓存）
            prof = QWebEngineProfile()
            prof.setHttpUserAgent(honest_ua)
        else:
            prof = QWebEngineProfile.defaultProfile()
            prof.setPersistentStoragePath(webengine_dir(self.data_dir))
            prof.setCachePath(cache_dir(self.data_dir))
            prof.setHttpUserAgent(honest_ua)

        # 引擎设置
        settings = prof.settings()
        from PySide6.QtWebEngineCore import QWebEngineSettings
        s = QWebEngineSettings
        settings.setAttribute(s.JavascriptEnabled, self.config.enable_javascript)
        settings.setAttribute(s.PluginsEnabled, self.config.enable_plugins)
        settings.setAttribute(s.FullScreenSupportEnabled, True)
        settings.setAttribute(s.DnsPrefetchEnabled, True)
        # v1.4 M3 修复：该属性默认 True（实测确认），本地文档可互读 file://，
        # 与 file: scheme 白名单相矛盾 —— 强制关闭。
        settings.setAttribute(s.LocalContentCanAccessFileUrls, False)
        settings.setAttribute(s.LocalContentCanAccessRemoteUrls, False)
        # HTTP 磁盘缓存上限（标准 #6：控制资源占用）
        try:
            prof.setHttpCacheMaximumSize(
                max(0, self.config.http_cache_mb) * 1024 * 1024)
        except Exception:
            pass

        # 广告拦截：安装到 profile
        prof.setUrlRequestInterceptor(self.adblock)

        # v2.1.5：安装随包资产 scheme handler（aegisasset://，只读白名单壁纸），
        # 供新标签页渲染壁纸。持有引用防 GC（Qt 不接管其生命周期）。
        try:
            from .asset_scheme import SCHEME_NAME, AegisAssetHandler
            self._asset_handler = AegisAssetHandler()
            prof.installUrlSchemeHandler(SCHEME_NAME, self._asset_handler)
        except Exception:
            self._asset_handler = None

        # 强制深色模式：注入反色样式表（在 profile 层生效，覆盖全部页面）
        self._apply_force_dark_style(prof)
        return prof

    # ------------------------------------------------------------------ #
    def _apply_force_dark_style(self, prof):
        """写/移除强制深色样式表并应用到给定 profile。

        采用纯反色滤镜（invert + hue-rotate），不硬编码任何颜色，
        对图片/视频再做一次反色校正，避免媒体被洗白。关闭时清空样式表。
        """
        try:
            from PySide6.QtCore import QUrl
            css_path = os.path.join(self.data_dir, "force_dark.css")
            if self.config.force_dark:
                css = (
                    "html{filter:invert(1) hue-rotate(180deg) "
                    "brightness(0.95) contrast(0.95)}\n"
                    "img:not([src^=\"data:\"]),picture,video,canvas,svg"
                    "{filter:invert(1) hue-rotate(180deg)}\n"
                )
                with open(css_path, "w", encoding="utf-8") as f:
                    f.write(css)
                prof.setUserStyleSheetUrl(QUrl.fromLocalFile(css_path))
            else:
                if os.path.exists(css_path):
                    try:
                        os.remove(css_path)
                    except OSError:
                        pass
                prof.setUserStyleSheetUrl(QUrl())
        except Exception:
            pass

    def apply_force_dark(self):
        """公开入口：运行期切换强制深色模式后由 UI 调用。"""
        self._apply_force_dark_style(self.profile)

    # ------------------------------------------------------------------ #
    def save_config(self):
        self.config.save(self.base_data_dir)
