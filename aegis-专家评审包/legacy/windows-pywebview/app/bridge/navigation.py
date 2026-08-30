"""NavigationMixin（H-2 拆分自 api_bridge.py——方法体逐字迁移，零行为变更）。

M-1 后续：api_bridge 818 行超 500 行红线，按节拆分为 mixin 组合
（沿用 TabOpsMixin 先例 + 协议声明模式：TYPE_CHECKING 块声明宿主
成员，运行时由 Api 组合提供——无循环、无运行期开销）。
"""
from typing import Any, Callable

from ..url_utils import SEARCH_ENGINES, START_URL, normalize_url  # noqa: F401
from ..validators import host_of, to_int as _to_int, to_nonneg_int as _to_nonneg_int, to_str as _to_str  # noqa: F401



class NavigationMixin:
    # 宿主 Api 成员声明（协议模式——运行时由组合后的 Api 提供）
    _engine: str
    history: Any
    window: Any
    _load: Callable[[str], bool]
    _eval: Callable[[str], bool]
    _update_current: Callable[..., None]
    _is_navigation_safe_url: Callable[[str], bool]
    # ---- 导航 ----
    def navigate(self, text: str) -> None:
        # P1-1 过渡（专家审查）：桥写操作强制来源校验（远程页面拒绝——
        # chrome UI 迁移前——远程内容不能控制浏览器导航）
        if not self._check_trusted_source():
            try:
                from crash_reporter import log_event
                log_event("[bridge] 拒绝远程页面 navigate（来源不受信）")
            except Exception:
                pass
            return
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
            host = host_of(self.current_url() or "")
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
                # host_of（validators 单源）替代逐处 urlparse 提取
                page_host = ""
                try:
                    page_host = host_of(self.current_url())
                except Exception:
                    page_host = ""
                src_host = host_of(source)
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

