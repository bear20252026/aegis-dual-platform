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


def _clamp_idx(value: Any) -> int | None:
    """索引参数校验（非负整数；失败 None）。

    延迟导入 _to_nonneg_int（api_bridge → tab_ops 单向依赖，避免循环导入）。
    """
    try:
        from .api_bridge import _to_nonneg_int
        return _to_nonneg_int(value, None)
    except Exception:
        return None


class TabOpsMixin:
    """标签增强操作（Api 混入；依赖 Api 的 _tabs/_current/_lock/_load）。"""

    if TYPE_CHECKING:
        # 宿主 Api 的属性/方法静态声明（运行时由 Api 提供——仅供 mypy）
        _tabs: list[dict[str, Any]]
        _current: int
        _lock: threading.RLock
        _data_dir: str

        def _remove_tab(self, idx: int) -> str | None: ...
        def _load(self, url: str) -> bool: ...
        def _eval(self, script: str) -> bool: ...
        def _tabs_snapshot(self) -> dict: ...
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
        """
        if not isinstance(tabs, list):
            return ""
        clean: list[dict] = []
        from .session_store import _sanitize_tab
        for raw in tabs[:MAX_TABS]:
            tab = _sanitize_tab(raw)
            if tab is not None:
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
