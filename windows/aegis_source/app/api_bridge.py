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
import urllib.parse
from pathlib import Path
from typing import Any

from .nav_queue import NavQueue
from .shell_toolbar import build_toolbar_js

# 应用根目录（aegis_source/），用于定位 shell/start.html
ROOT = Path(__file__).resolve().parent.parent
START_URL = (ROOT / "shell" / "start.html").as_uri()
_DEFAULT_WALLPAPER = "aurora-twilight.jpg"

# 搜索引擎表：key -> (名称, 搜索 URL 模板)
SEARCH_ENGINES: dict[str, tuple[str, str]] = {
    "baidu":  ("百度", "https://www.baidu.com/s?wd={}"),
    "bing":   ("必应", "https://www.bing.com/search?q={}"),
    "google": ("谷歌", "https://www.google.com/search?q={}"),
    "sogou":  ("搜狗", "https://www.sogou.com/web?query={}"),
}
DEFAULT_ENGINE = "baidu"


def normalize_url(text: str | None, engine: str = DEFAULT_ENGINE) -> str:
    """把用户输入变成可导航 URL：无协议补 https://，非网址当搜索词。"""
    text = (text or "").strip()
    if not text:
        return START_URL
    if text == "about:blank":
        return "about:blank"
    lowered = text.lower()
    if lowered.startswith(("http://", "https://", "file://")):
        return text
    # 含空格或没有点号 → 视为搜索
    if " " in text or "." not in text:
        template = SEARCH_ENGINES.get(engine, SEARCH_ENGINES[DEFAULT_ENGINE])[1]
        return template.format(urllib.parse.quote(text))
    return "https://" + text


def _is_navigation_safe(url: str) -> bool:
    """H-C1 审计修复：外部导航目标安全校验。

    只放行 http/https 与显式 about:blank；file:/javascript:/vbscript:/
    data:/blob: 等一律拒绝（复用 security.safe_url 白名单，
    allow_internal=False 确保 data:/blob: 等内部伪协议不被外部输入放行）。
    """
    if not url:
        return False
    if url == "about:blank":
        return True
    from .security import safe_url
    return bool(safe_url(url, allow_internal=False))


class Api:
    """暴露给 JS 的 Python 桥。JS 侧调用 pywebview.api.navigate(...) 等。"""

    # 暴露给 JS 的方法白名单（其余属性/内部方法一律对 dir() 隐藏）
    _JS_EXPOSED = frozenset({
        "get_wallpaper", "set_wallpaper",
        "get_search_engine", "set_search_engine",
        "get_tabs", "new_tab", "switch_tab", "close_tab",
        "pin_tab", "unpin_tab",
        "set_tab_group", "get_tab_groups",
        "navigate", "go_back", "go_forward", "reload_page", "go_home",
        "current_url", "js_error",
        "get_bookmarks", "add_bookmark", "remove_bookmark",
        "import_bookmarks", "import_history",
        "get_history", "get_most_visited",
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
        self._tabs: list[dict[str, Any]] = [{
            "title": "新标签页", "url": START_URL, "pinned": False,
            "group": "默认",
        }]
        self._current: int = 0
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

    # ================= 壁纸 =================
    def get_wallpaper(self) -> str:
        """返回当前新标签页壁纸文件名（配置持久化）。"""
        try:
            if self.config is not None:
                name = getattr(self.config, "ntp_wallpaper", "") or ""
                if name:
                    return name
        except Exception:
            pass
        return _DEFAULT_WALLPAPER

    def set_wallpaper(self, name: str) -> None:
        """切换壁纸并持久化（白名单校验）。"""
        try:
            from .asset_scheme import WALLPAPERS
            if not name or name not in WALLPAPERS:
                return
            if self.config is None:
                from .config import AppConfig
                self.config = AppConfig()
            self.config.ntp_wallpaper = name
            if self._data_dir:
                self.config.save(self._data_dir)
        except Exception:
            pass  # 壁纸配置失败不影响浏览

    # ================= 搜索引擎 =================
    def get_search_engine(self) -> dict:
        """返回 {engine, engines:[{key,name}]}。"""
        return {
            "engine": self._engine,
            "engines": [{"key": k, "name": v[0]} for k, v in SEARCH_ENGINES.items()],
        }

    def set_search_engine(self, key: str) -> None:
        """切换搜索引擎并持久化（白名单校验）。"""
        try:
            if key not in SEARCH_ENGINES:
                return
            self._engine = key
            if self.config is None:
                from .config import AppConfig
                self.config = AppConfig()
            self.config.engine = key
            if self._data_dir:
                self.config.save(self._data_dir)
        except Exception:
            pass  # 配置失败不影响本次切换

    # ================= 标签页 =================
    def get_tabs(self) -> dict:
        """返回 {tabs:[{title,url}], current:int}（快照）。"""
        return self._tabs_snapshot()

    def new_tab(self, url: str = "") -> None:
        # H-C1 审计修复：用户显式传入的 url 必须过安全校验；
        # 空 url（UI 新建标签）仍用受信任的 START_URL，行为不变。
        if url:
            target = normalize_url(url)
            if target != "about:blank" and not _is_navigation_safe(target):
                return
        else:
            target = START_URL
        with self._lock:
            self._tabs.append({"title": "新标签页", "url": target,
                               "pinned": False, "group": "默认"})
            self._current = len(self._tabs) - 1
        self._load(target)

    def switch_tab(self, index: Any) -> None:
        try:
            index = int(index)
        except (TypeError, ValueError):
            return
        with self._lock:
            if not (0 <= index < len(self._tabs)):
                return
            self._current = index
            url = self._tabs[index]["url"]
        self._load(url)

    def close_tab(self, index: Any) -> None:
        try:
            index = int(index)
        except (TypeError, ValueError):
            return
        with self._lock:
            if len(self._tabs) <= 1 or not (0 <= index < len(self._tabs)):
                return
            self._tabs.pop(index)
            if self._current >= index and self._current > 0:
                self._current -= 1
            url = self._tabs[self._current]["url"]
        self._load(url)

    def pin_tab(self, index: Any) -> None:
        """固定标签：置顶（pinned 标签排在最前，顺序稳定）。"""
        try:
            index = int(index)
        except (TypeError, ValueError):
            return
        with self._lock:
            if not (0 <= index < len(self._tabs)):
                return
            tab = self._tabs[index]
            if tab.get("pinned"):
                return
            tab["pinned"] = True
            self._reorder_pinned()
            self._current = self._find_index(tab)

    def unpin_tab(self, index: Any) -> None:
        """取消固定：回到普通标签区（pinned 之后）。"""
        try:
            index = int(index)
        except (TypeError, ValueError):
            return
        with self._lock:
            if not (0 <= index < len(self._tabs)):
                return
            tab = self._tabs[index]
            if not tab.get("pinned"):
                return
            tab["pinned"] = False
            self._reorder_pinned()
            self._current = self._find_index(tab)

    def _reorder_pinned(self) -> None:
        """置顶重排：pinned 在前（保持各自相对顺序），普通标签在后。"""
        pinned = [t for t in self._tabs if t.get("pinned")]
        normal = [t for t in self._tabs if not t.get("pinned")]
        self._tabs[:] = pinned + normal

    def _find_index(self, tab: dict) -> int:
        """按对象身份查找标签索引（重排后定位当前标签）。"""
        for i, t in enumerate(self._tabs):
            if t is tab:
                return i
        return self._current

    def set_tab_group(self, index: Any, group: Any) -> bool:
        """把标签归入分组（R4 task 层；组名为字符串，空串=默认组）。

        借鉴 min 的 tabState 分层：tab（单标签状态）/ task（标签分组）。
        返回是否成功；越界或组名非法返回 False。
        """
        try:
            index = int(index)
        except (TypeError, ValueError):
            return False
        name = str(group or "").strip()[:32]
        if not name:
            name = "默认"
        with self._lock:
            if not (0 <= index < len(self._tabs)):
                return False
            self._tabs[index]["group"] = name
        return True

    def get_tab_groups(self) -> list:
        """返回全部分组名（有序去重，供分组栏/标签着色使用）。"""
        with self._lock:
            names = [t.get("group") or "默认" for t in self._tabs]
        # 保持首次出现顺序去重
        seen: set = set()
        out: list = []
        for n in names:
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def _tabs_snapshot(self) -> dict:
        """线程安全地返回标签快照（副本，避免调用方拿到活引用）。"""
        with self._lock:
            tabs = [dict(t) for t in self._tabs]
            current = self._current
        return {"tabs": tabs, "current": current}

    def _update_current(self, url: str, title: str = "") -> None:
        """页面加载后刷新当前标签的 url/title（线程安全）。"""
        if not url and not title:
            return
        with self._lock:
            if 0 <= self._current < len(self._tabs):
                if url:
                    self._tabs[self._current]["url"] = url
                if title:
                    self._tabs[self._current]["title"] = title[:80]

    # ================= 导航 =================
    def navigate(self, text: str) -> None:
        url = normalize_url(text, self._engine)
        # H-C1 审计修复：外部导航入口强制过安全关口。
        # 只放行 http/https 与显式 about:blank；file:/javascript:/data:/blob:
        # 等一律拒绝（normalize_url 对 file:// 前缀原样返回，此前可被地址栏
        # 输入 file:///C:/... 加载本地文件 —— 与 README 安全声明脱节）。
        if url != "about:blank" and not _is_navigation_safe(url):
            return
        try:
            if self.history is not None:
                self.history.add(url, text)
        except Exception:
            pass  # 历史写入失败不影响导航
        self._update_current(url, text)
        self._load(url)

    def go_back(self) -> None:
        self._eval("history.back()")

    def go_forward(self) -> None:
        self._eval("history.forward()")

    def reload_page(self) -> None:
        self._eval("location.reload()")

    def go_home(self) -> None:
        self._load(START_URL)

    # ---- 状态 ----
    def current_url(self) -> str:
        w = self.window
        if w is None:
            return ""
        try:
            return w.get_current_url() or ""
        except Exception:
            return ""

    # ---- JS 错误上报（JS 侧 window.onerror / unhandledrejection → 这里）----
    def js_error(self, message: str, source: str = "", line: Any = None,
                 col: Any = None, stack: str = "") -> None:
        """接收页面 JS 错误，写入崩溃报告 events.log（后台静默）。"""
        try:
            from crash_reporter import log_event
            line = int(line) if line else ""
            col = int(col) if col else ""
            log_event(
                f"JS错误: {str(message)[:200]} | src={str(source)[:120]} "
                f"@{line}:{col} | stack={str(stack)[:300]}"
            )
        except Exception:
            pass  # 日志失败绝不影响页面

    # ================= 书签 =================
    def get_bookmarks(self) -> list:
        """返回书签列表 [{id,title,url}]。"""
        try:
            if self.bookmarks is None:
                return []
            rows = self.bookmarks.all()
            return [{"id": r[0], "title": r[1], "url": r[2]} for r in rows]
        except Exception:
            return []

    def add_bookmark(self, title: str, url: str) -> bool:
        try:
            if self.bookmarks is not None:
                return self.bookmarks.add(title, url)
        except Exception:
            pass
        return False

    def remove_bookmark(self, url: str) -> None:
        try:
            if self.bookmarks is not None:
                self.bookmarks.remove(url)
        except Exception:
            pass

    def import_bookmarks(self) -> dict:
        """从 Chrome/Edge 导入书签（自动探测本机文件）。

        返回 {"imported": 新增数, "total": 解析总数, "source": 来源文件}。
        解析失败或存储不可用时静默返回 0（导入是可选功能，不影响浏览）。
        """
        try:
            from .browser_import import find_bookmarks_files, parse_bookmarks_json
            for path in find_bookmarks_files():
                items = parse_bookmarks_json(path)
                if not items:
                    continue
                imported = 0
                for item in items:
                    if (self.bookmarks is not None
                            and self.bookmarks.add(item["title"], item["url"])):
                        imported += 1
                return {"imported": imported, "total": len(items), "source": path}
        except Exception:
            pass
        return {"imported": 0, "total": 0, "source": ""}

    def import_history(self, limit: int = 500) -> dict:
        """从 Chrome/Edge 导入最近历史（自动探测本机文件）。

        返回 {"imported": 新增数, "total": 解析总数, "source": 来源文件}。
        """
        try:
            from .browser_import import find_history_files, parse_history_db
            for path in find_history_files():
                items = parse_history_db(path, limit)
                if not items:
                    continue
                imported = 0
                for item in items:
                    if (self.history is not None
                            and self.history.add(item["url"], item["title"])):
                        imported += 1
                return {"imported": imported, "total": len(items), "source": path}
        except Exception:
            pass
        return {"imported": 0, "total": 0, "source": ""}

    # ================= 历史 =================
    def get_history(self, limit: Any = 100) -> list:
        """返回历史 [{id,url,title,time}]。"""
        try:
            if self.history is None:
                return []
            n = int(limit) if limit else 100
            rows = self.history.all(n)
            return [
                {"id": r[0], "url": r[1], "title": r[2], "time": r[3]}
                for r in rows
            ]
        except Exception:
            return []

    def get_most_visited(self, limit: Any = 12) -> list:
        try:
            if self.history is None:
                return []
            n = int(limit) if limit else 12
            rows = self.history.most_visited(n)
            return [{"id": r[0], "url": r[1], "title": r[2]} for r in rows]
        except Exception:
            return []


def on_loaded(window: Any, api: Api) -> None:
    """每页加载完成后：刷新当前标签 url/title，并注入工具栏（含新标签页）。

    注意：该回调在 pywebview 的后台线程中执行；本函数自身绝不抛异常。
    get_current_url 属于只读查询（winforms 后端线程安全），可直接调用；
    注入（evaluate_js）统一走 api._eval 投递到导航线程执行。
    """
    if window is None or api is None:
        return
    try:
        url = window.get_current_url() or ""
    except Exception:
        url = ""
    api._update_current(url)
    try:
        # 内嵌标签数据 → 单次注入，零 HTTP 往返。
        kb = None  # None = 默认表 DEFAULT_KEYBINDINGS
        try:
            cfg = getattr(api, "config", None)
            raw = getattr(cfg, "keybindings_json", "") if cfg else ""
            if raw:
                import json as _json
                parsed = _json.loads(raw)
                if isinstance(parsed, dict):
                    kb = {k: str(v)[:1] for k, v in parsed.items()
                          if isinstance(v, str) and v}
        except Exception:
            kb = None  # 用户配置解析失败时静默回退默认表
        js = build_toolbar_js(url, api.get_tabs(), keybindings=kb)
        api._eval(js)
    except Exception:
        pass  # 页面不允许注入（CSP 严格站点 / 空白页）时静默降级
