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
from .url_utils import (
    DEFAULT_ENGINE,
    SEARCH_ENGINES,
    START_URL,
    is_navigation_safe,
    normalize_url,
)

# 保持旧私有名兼容（_is_navigation_safe 供 Api._is_navigation_safe_url 使用）
_is_navigation_safe = is_navigation_safe


def _to_int(value: Any, default: Any = None) -> Any:
    """js_api 参数校验助手（方向①-S3）：安全转 int；失败返回 default。

    pywebview 传参可能是字符串/浮点/畸形值，统一在此收敛类型转换，
    避免各方法重复 try/except 且行为不一致。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_nonneg_int(value: Any, default: Any = None) -> Any:
    """转 int 且要求非负；否则返回 default（索引类参数专用）。"""
    n = _to_int(value, None)
    if n is None or n < 0:
        return default
    return n


def _to_str(value: Any, default: Any = None) -> Any:
    """确认是 str；None→default，非 str→default（文本类参数专用）。"""
    if value is None:
        return default
    return value if isinstance(value, str) else default


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

_DEFAULT_WALLPAPER = "aurora-twilight.jpg"


class Api:
    """暴露给 JS 的 Python 桥。JS 侧调用 pywebview.api.navigate(...) 等。"""

    # 暴露给 JS 的方法白名单（其余属性/内部方法一律对 dir() 隐藏）
    # B0-W-01 整改（国防级审查——阶段 0 立即处置）：
    # 从远程页面可达桥移除敏感读取/导入能力（历史/书签/标签 URL 读取 +
    # 本机 Chrome/Edge 导入——恶意页面可读取回传/触发导入）。
    # 依据：微软官方（WebView2 安全——限制 web 内容功能/避免通用代理）+
    # Code2Native（桥白名单只暴露必要方法——Critical）+ 审查必须整改。
    # 保留：导航/标签操作/壁纸/搜索设置（页面 UI 功能——非敏感读取）。
    _JS_EXPOSED = frozenset({
        "get_wallpaper", "set_wallpaper",
        "get_search_engine", "set_search_engine",
        "new_tab", "switch_tab", "close_tab",
        "pin_tab", "unpin_tab",
        "set_tab_group",
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
        # M-2 修复（防御性安全审查）：敏感写操作来源校验——远程页面
        # 调用拒绝（防搜索引擎篡改）
        if not self._check_trusted_source():
            try:
                from crash_reporter import log_event
                log_event("[bridge] 拒绝远程页面 set_search_engine（来源不受信）")
            except Exception:
                pass
            return
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

    def _is_navigation_safe_url(self, url: str) -> bool:
        """H-C1 + A-② 双层校验：URL 协议安全 + 威胁情报黑名单。

        返回 True 表示可导航；任一检查失败返回 False（拒绝导航）。
        黑名单为空（未配置订阅源）时安全浏览检查放行，不影响正常功能。
        """
        if url != "about:blank" and not _is_navigation_safe(url):
            return False
        # A-②：复用 threat_feed 缓存黑名单（精确/子域匹配）
        try:
            from urllib.parse import urlparse

            from .threat_feed import ThreatFeedUpdater, host_is_blocked
            updater = ThreatFeedUpdater(self._data_dir)
            blocked = updater.load_cached()
            if not blocked:
                return True  # 未配置订阅源 → 放行
            host = (urlparse(url).hostname or "").lower()
            if host and host_is_blocked(host, blocked):
                # 观察项 2 优化：威胁拦截命中记录（可观测性，不改变功能）
                try:
                    from app.event_log import log_event
                    log_event(f"[threat] 导航拦截威胁域名: {url}")
                except Exception:
                    pass
                return False  # 命中黑名单 → 拒绝导航
        except Exception:
            # M-5 修复（防御性安全审查）：威胁检查异常不再静默——留痕
            # （缓存读取/解析失败放行但记日志——至少带日志放行）
            try:
                from crash_reporter import log_event
                log_event("[threat] 黑名单检查异常——本次放行（已留痕）")
            except Exception:
                pass
        return True

    def new_tab(self, url: str = "") -> None:
        # M-2 修复（防御性安全审查）：new_tab 频率限制——500ms 最小间隔
        # + 20 标签上限（防 tab-bomb——恶意页面循环调用）
        import time as _t
        _now = _t.time()
        if _now - self._last_new_tab < 0.5 or len(self._tabs) >= 20:
            return
        self._last_new_tab = _now
        # H-C1/A-② 审计修复：用户显式传入的 url 必须过安全+黑名单校验；
        # 空 url（UI 新建标签）仍用受信任的 START_URL，行为不变。
        if url:
            target = normalize_url(url)
            if not self._is_navigation_safe_url(target):
                return
        else:
            target = START_URL
        with self._lock:
            self._tabs.append({"title": "新标签页", "url": target,
                               "pinned": False, "group": "默认"})
            self._current = len(self._tabs) - 1
        self._load(target)

    def switch_tab(self, index: Any) -> None:
        idx = _to_nonneg_int(index, None)
        if idx is None:
            return
        with self._lock:
            if not (0 <= idx < len(self._tabs)):
                return
            self._current = idx
            url = self._tabs[idx]["url"]
        self._load(url)

    def _remove_tab(self, idx: int):
        """移除标签并调整 current（标签管理核心操作，供 close_tab 使用）。

        重构热点：把"移除 + current 调整"集中于此，减少标签管理高频
        变更点（HotspotTriage churn 驱动）。返回新当前标签 url（供导航）
        或 None（无有效标签可移除）。调用方需持锁（本方法不加锁）。
        """
        if len(self._tabs) <= 1 or not (0 <= idx < len(self._tabs)):
            return None
        self._tabs.pop(idx)
        if self._current >= idx and self._current > 0:
            self._current -= 1
        return self._tabs[self._current]["url"]

    def close_tab(self, index: Any) -> None:
        idx = _to_nonneg_int(index, None)
        if idx is None:
            return
        with self._lock:
            url = self._remove_tab(idx)
        if url is not None:
            self._load(url)

    def pin_tab(self, index: Any) -> None:
        """固定标签：置顶（pinned 标签排在最前，顺序稳定）。"""
        idx = _to_nonneg_int(index, None)
        if idx is None:
            return
        with self._lock:
            if not (0 <= idx < len(self._tabs)):
                return
            tab = self._tabs[idx]
            if tab.get("pinned"):
                return
            tab["pinned"] = True
            self._reorder_pinned()
            self._current = self._find_index(tab)

    def unpin_tab(self, index: Any) -> None:
        """取消固定：回到普通标签区（pinned 之后）。"""
        idx = _to_nonneg_int(index, None)
        if idx is None:
            return
        with self._lock:
            if not (0 <= idx < len(self._tabs)):
                return
            tab = self._tabs[idx]
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
        idx = _to_nonneg_int(index, None)
        if idx is None:
            return False
        name = (_to_str(group, "") or "").strip()[:32]
        if not name:
            name = "默认"
        with self._lock:
            # L-1 修复（防御性安全审查）：判断与取值统一用 idx（转换后的
            # 整数）——原始 index 可能为字符串/浮点（TypeError——专家发现）
            if not (0 <= idx < len(self._tabs)):
                return False
            self._tabs[idx]["group"] = name
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
        text = _to_str(text, "") or ""
        url = normalize_url(text, self._engine)
        # H-C1/A-② 审计修复：外部导航入口双层校验（协议安全 + 威胁黑名单）。
        # 只放行 http/https 与显式 about:blank；file:/javascript:/data:/blob:
        # 等一律拒绝；命中 threat_feed 黑名单域名同样拒绝。
        if not self._is_navigation_safe_url(url):
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

    def _check_trusted_source(self) -> bool:
        """M-2 修复（防御性安全审查）：敏感写操作来源校验——当前标签
        URL 的 host 为空（本地壳页/新标签页）即受信；远程页面调用拒绝
        （防书签投毒/搜索引擎篡改——专家建议受信集）。"""
        try:
            from urllib.parse import urlparse
            host = urlparse(self.current_url() or "").hostname or ""
            return host == ""  # 本地壳页（file:///空白）受信；远程拒绝
        except Exception:
            return False

    # ---- JS 错误上报（JS 侧 window.onerror / unhandledrejection → 这里）----
    def js_error(self, message: str, source: str = "", line: Any = None,
                 col: Any = None, stack: str = "") -> None:
        """接收页面 JS 错误，写入崩溃报告 events.log（后台静默）。"""
        try:
            # A2（final-development-checklist）：消息来源验证（CVE-2026-33118
            # spoofing 防御）——source 为空（页面内联错误）或与当前页面 host
            # 同源才记录；跨域来源（伪造上报）丢弃。不改变功能（合法错误照常
            # 记录，仅非法来源被拒）。
            if source:
                from urllib.parse import urlparse
                page_host = ""
                try:
                    page_host = (urlparse(self.current_url()).hostname or "").lower()
                except Exception:
                    page_host = ""
                src_host = (urlparse(source).hostname or "").lower()
                if src_host and page_host and src_host != page_host:
                    return  # 跨域来源 → 丢弃（防伪造来源上报）
            from crash_reporter import log_event
            line = int(line) if line else ""
            col = int(col) if col else ""
            # L-5 修复（防御性安全审查）：message/source/stack 换行过滤
            # （\r\n → 空格——防恶意 message 注入伪造日志条目）
            msg_safe = str(message)[:200].replace("\r", " ").replace("\n", " ")
            src_safe = str(source)[:120].replace("\r", " ").replace("\n", " ")
            stk_safe = str(stack)[:300].replace("\r", " ").replace("\n", " ")
            log_event(
                f"JS错误: {msg_safe} | src={src_safe} "
                f"@{line}:{col} | stack={stk_safe}"
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
        # M-2 修复（防御性安全审查）：敏感写操作来源校验——远程页面
        # 调用拒绝（防书签投毒）
        if not self._check_trusted_source():
            try:
                from crash_reporter import log_event
                log_event("[bridge] 拒绝远程页面 add_bookmark（来源不受信）")
            except Exception:
                pass
            return False
        try:
            if self.bookmarks is not None:
                return self.bookmarks.add(title, url)
        except Exception:
            pass
        return False

    def remove_bookmark(self, url: str) -> None:
        # M-2 修复（防御性安全审查）：敏感写操作来源校验——远程页面
        # 调用拒绝（防书签删除投毒）
        if not self._check_trusted_source():
            try:
                from crash_reporter import log_event
                log_event("[bridge] 拒绝远程页面 remove_bookmark（来源不受信）")
            except Exception:
                pass
            return
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
    def get_history(self, limit: Any = 100,
                    cursor_id: Any = None, cursor_time: Any = None) -> list:
        """返回历史 [{id,url,title,time}]（支持游标分页，方向②-P2）。

        cursor_id/cursor_time 同时提供时返回下一页（上一页末条的
        id+visit_time 作游标），避免深分页全表扫描。
        """
        n = _to_nonneg_int(limit, None) or 100
        cid = _to_nonneg_int(cursor_id, None)
        ctime = _to_int(cursor_time, None)
        try:
            if self.history is None:
                return []
            if cid is not None and ctime is not None:
                rows = self.history.all(n, cursor_id=cid, cursor_time=ctime)
            else:
                rows = self.history.all(n)
            # 重构热点 #2：统一行转换（dict/tuple 兼容收敛到 _row_to_tuple）
            out = []
            for r in rows:
                rid, url, title, visit_time = _row_to_tuple(r)
                out.append({
                    "id": rid, "url": url, "title": title,
                    "time": visit_time,
                })
            return out
        except Exception:
            return []

    def get_most_visited(self, limit: Any = 12) -> list:
        n = _to_nonneg_int(limit, None) or 12
        try:
            if self.history is None:
                return []
            rows = self.history.most_visited(n)
            return [{"id": r[0], "url": r[1], "title": r[2]} for r in rows]
        except Exception:
            return []

    def search_history_fulltext(self, keyword: Any, limit: Any = 50,
                                cursor_id: Any = None,
                                cursor_time: Any = None) -> list:
        """FTS5 全文搜索历史（落地建议③，借鉴 min fullTextSearch）。

        返回 [{id,url,title,visit_time}]；keyword 为空或存储不可用时
        返回空列表（静默，不影响浏览）。cursor_id/cursor_time 同时提供
        时返回更低下页（(visit_time,id) 复合游标，方向②-P2，与
        get_history 语义一致；FTS5 rank 不可作游标——未显式 bm25 时
        所有匹配行 rank 相同）。
        """
        kw = _to_str(keyword, "")
        n = _to_nonneg_int(limit, None) or 50
        cid = _to_nonneg_int(cursor_id, None)
        ctime = _to_int(cursor_time, None)
        try:
            if self.history is None or not kw:
                return []
            if cid is not None and ctime is not None:
                rows = self.history.fulltext_search(
                    kw, n, cursor_id=cid, cursor_time=ctime)
            else:
                rows = self.history.fulltext_search(kw, n)
            # 重构热点 #2：统一行转换（与 get_history 共用 _row_to_tuple）
            out = []
            for r in rows:
                rid, url, title, visit_time = _row_to_tuple(r)
                out.append({
                    "id": rid, "url": url, "title": title,
                    "visit_time": visit_time,
                })
            return out
        except Exception:
            return []


# on_loaded 已随结构审计拆分至 app/bridge_hooks.py（文件顶部 re-export 保持兼容）。
