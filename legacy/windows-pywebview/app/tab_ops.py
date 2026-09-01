"""tab_ops.py —— 标签增强桥方法（单文件单职责）。

CHANGELOG「Unreleased/Planned：Windows 标签增强」落地：
- move_tab(from, to)：拖拽排序（pinned 区边界钳制——固定标签永不沉入普通区）；
- close_current_tab()：Ctrl+W 修复（注入侧 TABS_DATA.current 是注入时刻
  的冻结快照，多标签下会关错标签——改由后端取实时 _current）；
- seed_session()：启动恢复/用户恢复共用的标签装载（含清洗校验）；
- restore_session()：从 SessionStore 恢复（受信来源校验——与 B0-W-01
  口径一致：会话含 URL，属敏感读取，远程页面不可达）；
- has_saved_session()：仅返回标签数（int，无 URL/标题——非敏感）；
- _persist_session()：标签状态变更点统一落盘（SessionStore 原子写，
  失败静默——持久化绝不影响浏览）。

安全红线（与 api_bridge 口径一致）：
- 标签结构操作（move_tab/close_current_tab）放行来源校验——P1-1 复审：
  无数据读取、无新导航面（move 重排已开标签；close 最多关到远程页面
  自己正占据的当前标签）；M-2 频率限制/20 上限/URL 双层校验不变；
- restore_session：远程页面调用拒绝（_check_trusted_source——会话含
  URL，属敏感读取，与 B0-W-01 口径一致）；has_saved_session 仅返回计数；
- 会话文件只经 SessionStore 白名单清洗（http/https + START_URL）。
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from .session_store import MAX_TABS, SessionStore
from .url_utils import (START_URL, is_navigation_safe as _is_navigation_safe,
                        normalize_url)
from .validators import host_of
from .validators import to_nonneg_int as _to_nonneg_int, to_str as _to_str


def _clamp_idx(value: Any) -> int | None:
    """索引参数校验（非负整数；失败 None）。

    延迟导入 _to_nonneg_int（api_bridge → tab_ops 单向依赖，避免循环导入）。
    """
    try:
        from .validators import to_nonneg_int as _to_nonneg_int
        return _to_nonneg_int(value, None)
    except Exception:
        return None


class TabOpsMixin:
    _last_new_tab: float
    """标签增强操作（Api 混入；依赖 Api 的 _tabs/_current/_lock/_load）。"""

    if TYPE_CHECKING:
        # 宿主 Api 的属性/方法静态声明（运行时由 Api 提供——仅供 mypy）
        _tabs: list[dict[str, Any]]
        _current: int
        _lock: threading.RLock
        _data_dir: str

        def _load(self, url: str) -> bool: ...
        def _eval(self, script: str) -> bool: ...
        def _check_trusted_source(self) -> bool: ...

    def move_tab(self, from_idx: Any, to_idx: Any) -> None:
        """拖拽排序：把 from 位置标签移动到 to（pinned 区边界钳制）。"""
        # 口径调整（P1-1 复审，见 api_bridge.new_tab 注释）：
        # 标签结构操作放行来源校验——无数据读取；远程页面本无标签条 UI，
        # 拖拽只能来自注入工具栏。
        f = _clamp_idx(from_idx)
        t = _clamp_idx(to_idx)
        if f is None or t is None:
            return
        with self._lock:
            n = len(self._tabs)
            if not (0 <= f < n) or not (0 <= t < n) or f == t:
                return
            n_pinned = sum(1 for x in self._tabs if x.get("pinned"))
            tab = self._tabs[f]
            # pinned 只能在 [0, n_pinned-1] 内重排；普通标签只能在
            # [n_pinned, n-1] 内重排（固定区永不混序——pin_tab 语义一致）
            if tab.get("pinned"):
                t = min(max(t, 0), max(n_pinned - 1, 0))
            else:
                t = min(max(t, n_pinned), n - 1)
            if f == t:
                return
            self._tabs.insert(t, self._tabs.pop(f))
            # _current 必须始终对应正在显示的页面（移动后同步修正）
            cur = self._current
            if cur == f:
                self._current = t
            elif f < cur <= t:
                self._current = cur - 1
            elif t <= cur < f:
                self._current = cur + 1
        self._persist_session()

    def close_current_tab(self) -> None:
        """关闭当前标签（Ctrl/W 路径——后端实时取 _current，防冻结索引关错）。

        安全例外（见模块 docstring）：不做 _check_trusted_source——
        远程页面最多关到自己；无读取无篡改。
        """
        with self._lock:
            idx = self._current
            url = self._remove_tab(idx)
        if url is not None:
            self._load(url)
            self._persist_session()

    def seed_session(self, tabs: Any, current: Any = 0) -> str:
        """装载标签会话（启动恢复/用户恢复共用）。返回当前标签 URL。

        入口即校验：非 dict / URL 白名单不过的条目一律丢弃（与
        SessionStore._sanitize_tab 同规则——双保险，接受任何来源）。

        P1-8 修复（全量复审 2026-09-01）：恢复链路统一过
        _is_navigation_safe_url 双层校验——_sanitize_tab 只做协议白名单
        （http/https + START_URL），此前 session.json 被篡改注入威胁
        黑名单域时恢复链路照样放行。这里补 A-② 实时黑名单检查
        （启动恢复时 Agent 会话未激活，Agent 门禁自然跳过）。
        启动恢复（main_webview._init_stores_and_session）与用户恢复
        （restore_session）两条链路均经本方法，单点收口。
        """
        if not isinstance(tabs, list):
            return ""
        clean: list[dict] = []
        from .session_store import _sanitize_tab
        for raw in tabs[:MAX_TABS]:
            tab = _sanitize_tab(raw)
            if (tab is not None
                    and self._is_navigation_safe_url(tab["url"])):
                clean.append(tab)
        if not clean:
            return ""
        cur = current if isinstance(current, int) else 0
        cur = min(max(cur, 0), len(clean) - 1)
        with self._lock:
            self._tabs[:] = clean
            self._current = cur
        return clean[cur]["url"]

    def restore_session(self) -> bool:
        """从会话文件恢复标签并加载当前标签（受信来源校验）。"""
        if not self._check_trusted_source():
            try:
                from crash_reporter import log_event
                log_event("[bridge] 拒绝远程页面 restore_session（来源不受信）")
            except Exception:
                pass
            return False
        try:
            if not self._data_dir:
                return False
            data = SessionStore(self._data_dir).load()
            if not data or not data.get("tabs"):
                return False
            url = self.seed_session(data["tabs"], data.get("current", 0))
            if not url:
                return False
            self._load(url)
            return True
        except Exception:
            return False

    def has_saved_session(self) -> int:
        """返回已保存会话的标签数（0=无）。仅计数，无 URL/标题。"""
        try:
            if not self._data_dir:
                return 0
            data = SessionStore(self._data_dir).load()
            return len(data["tabs"]) if data else 0
        except Exception:
            return 0

    def _persist_session(self) -> None:
        """标签状态变更点统一落盘（静默——持久化绝不影响浏览）。"""
        try:
            if not self._data_dir:
                return
            snap = self._tabs_snapshot()
            SessionStore(self._data_dir).save(snap["tabs"], snap["current"])
        except Exception:
            pass
    # ================= 标签页 =================
    def get_tabs(self) -> dict:
        """返回 {tabs:[{title,url}], current:int}（快照）。"""
        return self._tabs_snapshot()

    def _is_navigation_safe_url(self, url: str) -> bool:
        """H-C1 + A-② 双层校验：URL 协议安全 + 威胁情报黑名单。

        返回 True 表示可导航；任一检查失败返回 False（拒绝导航）。
        黑名单为空（未配置订阅源）时安全浏览检查放行，不影响正常功能。

        P0-1 补丁（搜索审计 2026-09-01）：受信本地壳页 START_URL 显式
        白名单（与 about:blank 同待遇）——地址栏空输入/首页按钮会导航到
        START_URL（file:// 壳页），此前被 safe_url 的 file: 拒绝拦截，
        表现为"空输入无法回首页"。START_URL 由本模块 url_utils 单源
        生成（shared/shell 资源），非用户可控路径，放行无风险。
        """
        if url != "about:blank" and url != START_URL and not _is_navigation_safe(url):
            return False
        # P0-03 修复（专家审查）：Agent 会话活跃时——未配置 allowlist 或
        # 非白名单域——导航层真正拒绝（放函数开头——不被威胁检查提前返回跳过）
        # H-3 修复（审计 2026-08-31）：
        # ① 校验移出 try/except——原实现日志故障即跳过拒绝逻辑放行（fail-open）
        # ② 补 60s 过期判断（对齐 main_webview.py 请求层同款语义）——原实现
        #    只判真值，_agent_session 一旦激活永久生效
        import time as _time
        agent_session = getattr(self, "_agent_session", None) or 0.0
        session_active = bool(agent_session) and (
            _time.time() - agent_session) < 60
        if session_active:
            # P1-9 修复（全量复审 2026-09-01）：allowlist 解析/匹配收敛到
            # app/agent_allowlist.py 单源（与请求层 main_webview 同源同语义）
            from .agent_allowlist import host_allowed, load_agent_allowlist
            allow_hosts = load_agent_allowlist()
            if not allow_hosts:
                from crash_reporter import log_event
                log_event("[agent] 拒绝 Agent 导航（未配置 AEGIS_AGENT_ALLOWED_HOSTS——allowlist 为空）")
                return False
            host = host_of(url)
            if not host_allowed(host, allow_hosts):
                from crash_reporter import log_event
                log_event(f"[agent] 拒绝 Agent 导航非白名单域: {url}")
                return False
        # A-②：复用 threat_feed 缓存黑名单（精确/子域匹配）
        try:
            from .threat_feed import ThreatFeedUpdater, host_is_blocked
            updater = ThreatFeedUpdater(self._data_dir)
            blocked = updater.load_cached()
            if not blocked:
                return True  # 未配置订阅源 → 放行
            host = host_of(url)
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
        # 口径调整（P1-1 复审，随「标签增强」落地）：标签结构操作放行
        # 来源校验——用户在远程页面上按 Ctrl+T / 点「+」也必须可用（原
        # 一刀切拒绝导致远程页上无法新建任何标签）。安全性依据：
        # ① 无任何数据读取；② 带 URL 仍过 _is_navigation_safe_url 双层
        # 校验；③ M-2 频率限制 + 20 上限保留（tab-bomb 防护不变）；
        # ④ window.open 等价能力本就存在（NewWindowRequested 同窗重定向）。
        # 敏感操作（navigate/搜索引擎/书签/会话恢复）维持 P1-1 严格校验。
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
        self._persist_session()
        self._load(target)

    def switch_tab(self, index: Any) -> None:
        # 口径调整（P1-1 复审，见 new_tab 注释）：标签结构操作放行来源校验
        # （switch 仅切换已开标签的显示，无读取、无新导航面）。
        idx = _to_nonneg_int(index, None)
        if idx is None:
            return
        with self._lock:
            if not (0 <= idx < len(self._tabs)):
                return
            self._current = idx
            url = self._tabs[idx]["url"]
        self._persist_session()
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
        # 口径调整（P1-1 复审，见 new_tab 注释）：标签结构操作放行来源校验
        idx = _to_nonneg_int(index, None)
        if idx is None:
            return
        with self._lock:
            url = self._remove_tab(idx)
        if url is not None:
            self._load(url)
            self._persist_session()

    def pin_tab(self, index: Any) -> None:
        """固定标签：置顶（pinned 标签排在最前，顺序稳定）。"""
        # 口径调整（P1-1 复审，见 new_tab 注释）：标签结构操作放行来源校验
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
        self._persist_session()

    def unpin_tab(self, index: Any) -> None:
        """取消固定：回到普通标签区（pinned 之后）。"""
        # 口径调整（P1-1 复审，见 new_tab 注释）：标签结构操作放行来源校验
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
        self._persist_session()

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
        # 口径调整（P1-1 复审，见 new_tab 注释）：标签结构操作放行来源校验
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
        self._persist_session()
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
        self._persist_session()

