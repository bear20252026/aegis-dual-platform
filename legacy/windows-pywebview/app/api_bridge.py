"""api_bridge.py —— 暴露给 JS 的 Python 桥（单文件单职责）。

职责：Aegis 浏览器前端（注入式工具栏/新标签页）通过 pywebview js_api
调用的全部后端方法：标签页、壁纸、搜索引擎、导航、书签、历史、JS 错误
上报。本文件**只做桥接与状态管理**，所有窗口操作委托给 NavQueue 执行。

线程约定（关键，原 main_webview.py 逻辑原样迁移）：
- js_api 方法在 pywebview 的 HTTP 服务线程被调用（Thread-N _call）；
- 因此所有窗口操作（load_url / evaluate_js）绝不在此类线程同步执行，
  统一投递到 NavQueue（独立导航线程）串行消费 —— 避免 Invoke 死锁；
- 共享状态（_tabs/_current）用 self._lock（RLock）保护。

递归崩溃修复（crash_reports 线程栈铁证：get_functions 无限递归 834 层）：
pywebview 注入 js_api 时用 dir(obj) 遍历本对象所有属性并递归扫描，
而 self.window 等公开属性指向含循环引用的 pywebview Window 对象树，
导致注入线程无限递归卡死。因此重写 __dir__ 只暴露 js_api 方法白名单。
"""

import threading
from typing import Any

# 结构审计拆分：页面加载完成回调收敛到 bridge_hooks（独立职责）。
from .bridge_hooks import on_loaded  # noqa: F401  # re-export 保持兼容
from .nav_queue import NavQueue

# 结构审计拆分：模块级常量与 URL 纯函数收敛到 url_utils（单文件单职责）。
# re-export 保持兼容 —— selftest/main_webview 仍从 api_bridge 导入。
from .url_utils import (  # noqa: F401  # re-export：selftest/main_webview 兼容导入
    DEFAULT_ENGINE,
    SEARCH_ENGINES,
    START_URL,
    is_navigation_safe,
    normalize_url,
)

# 标签增强（move_tab/close_current_tab/会话恢复）以 mixin 混入——
# 独立职责独立文件（api_bridge 已超 500 行红线，不再增重）。
from .tab_ops import TabOpsMixin

# 类型校验工具单源化（M-1）：实现移 app/validators.py；旧私有名别名
# 保持 api_bridge 内 22 处调用点与潜在外部引用兼容

# 旧私有名兼容（api_bridge 内 3 处使用——语义=url_utils.is_navigation_safe）
_is_navigation_safe = is_navigation_safe


def _row_to_tuple(r: Any):
    """历史行统一为 (id,url,title,visit_time) 元组（重构热点 #2）。

    Database.query 返回 dict 行（按键取值）或 tuple 行（下标取值），
    get_history / search_history_fulltext 共用此辅助消除重复分支；
    键名契约（"time"/"visit_time"）仍由各方法自行组装。
    """
    if isinstance(r, dict):
        return (r.get("id"), r.get("url"), r.get("title"),
                r.get("visit_time"))
    return (r[0], r[1], r[2], r[3])



# ================= H-2 桥方法拆分（mixin 组合——沿用 TabOpsMixin 先例） =================
# 各域方法迁移至 app/bridge/（wallpaper/search_engine/navigation/bookmarks/
# geogebra/imports/history）+ tab_ops.py（标签节并入既有 TabOpsMixin）。
# 本文件只保留：Api 壳（_JS_EXPOSED 白名单/__init__/窗口委托/_deny_remote/
# _check_trusted_source/_row_to_tuple 归属见各 mixin）——368 行 → 143 行壳。
from .bridge.wallpaper import WallpaperMixin
from .bridge.search_engine import SearchEngineMixin
from .bridge.navigation import NavigationMixin
from .bridge.bookmarks import BookmarksMixin
from .bridge.geogebra import GeoMixin
from .bridge.imports import ImportMixin
from .bridge.history import HistoryMixin


class Api(
    TabOpsMixin,
    WallpaperMixin,
    SearchEngineMixin,
    NavigationMixin,
    BookmarksMixin,
    GeoMixin,
    ImportMixin,
    HistoryMixin,
):
    """暴露给 JS 的 Python 桥。JS 侧调用 pywebview.api.navigate(...) 等。"""

    # 暴露给 JS 的方法白名单（其余属性/内部方法一律对 dir() 隐藏）
    # B0-W-01 整改（国防级审查——阶段 0 立即处置）：
    # 从远程页面可达桥移除敏感读取/导入能力（历史/标签 URL 读取 +
    # 本机 Chrome/Edge 导入——恶意页面可读取回传/触发导入）。
    # 依据：微软官方（WebView2 安全——限制 web 内容功能/避免通用代理）+
    # Code2Native（桥白名单只暴露必要方法——Critical）+ 审查必须整改。
    # 保留：导航/标签操作/壁纸/搜索设置（页面 UI 功能——非敏感读取）。
    # B0-W-01 复审（2026-08-30，随 PR #7）：get_bookmarks 以
    # 「白名单恢复 + 方法内受信来源校验」回归——远程页面调用返回空
    # （原整改一刀切移除，导致 start.html 书签宫格静默失效）。
    # 导入向导（scan/import）同样按此口径回归——远程页不可达。
    _JS_EXPOSED = frozenset({
        "get_wallpaper", "set_wallpaper",
        "get_search_engine", "set_search_engine",
        "new_tab", "switch_tab", "close_tab", "close_current_tab",
        "move_tab", "pin_tab", "unpin_tab",
        "set_tab_group",
        # 会话恢复（restore 含 URL——受信校验在方法内；has_saved 仅返回计数）
        "restore_session", "has_saved_session",
        # 书签读取（受信来源校验在方法内——远程页返回空列表）
        "get_bookmarks",
        # 导入向导（扫描/导入均受信来源校验在方法内——远程页不可达）
        "scan_import_sources", "import_bookmarks", "import_history",
        # 离线几何画板（内部资源跳转——受信校验在方法内）
        "open_geogebra",
        "navigate", "go_back", "go_forward", "reload_page", "go_home",
        "current_url", "js_error",
        "add_bookmark", "remove_bookmark",
    })

    def __dir__(self) -> list[str]:
        """只暴露 js_api 方法白名单，阻断 pywebview get_functions 的对象树递归。"""
        return sorted(self._JS_EXPOSED)

    def __init__(self) -> None:
        self.bookmarks: Any = None
        self.history: Any = None
        self.config: Any = None
        self._data_dir: str = ""
        self._lock = threading.RLock()
        # C2 阶段 A（ceLLMate 借鉴）：Agent 会话活跃时间戳（mcp 工具调用
        # 刷新；0=非活跃）。请求管线据此对 Agent 请求应用白名单域策略。
        self._agent_session: float = 0.0
        self._tabs: list[dict[str, Any]] = [{
            "title": "新标签页", "url": START_URL, "pinned": False,
            "group": "默认",
        }]
        self._current: int = 0
        self._last_new_tab: float = 0.0  # M-2：new_tab 频率限制（防 tab-bomb）
        self._engine: str = DEFAULT_ENGINE
        # 导航队列（独立线程执行全部窗口操作）
        self._nav = NavQueue()

    # ------------------------------------------------------------------ #
    # 窗口绑定 / 导航委托（窗口操作一律走 NavQueue）
    # ------------------------------------------------------------------ #
    @property
    def window(self) -> Any:
        return self._nav.window

    @window.setter
    def window(self, w: Any) -> None:
        self._nav.bind_window(w)

    def _load(self, url: str) -> bool:
        return self._nav.load(url)

    def _eval(self, script: str) -> bool:
        return self._nav.eval(script)

    def _nav_healthy(self) -> bool:
        """看门狗委托：导航线程健康度。"""
        return self._nav.healthy()

    def _recover_nav(self) -> None:
        """看门狗委托：导航线程疑似卡死时重启。"""
        self._nav.recover()



# on_loaded 已随结构审计拆分至 app/bridge_hooks.py（文件顶部 re-export 保持兼容）。
