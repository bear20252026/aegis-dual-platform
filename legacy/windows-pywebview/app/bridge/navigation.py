"""NavigationMixin（H-2 拆分自 api_bridge.py——方法体逐字迁移，零行为变更）。

M-1 后续：api_bridge 818 行超 500 行红线，按节拆分为 mixin 组合
（沿用 TabOpsMixin 先例 + 协议声明模式：TYPE_CHECKING 块声明宿主
成员，运行时由 Api 组合提供——无循环、无运行期开销）。
"""
from typing import Any, Callable

from ..url_utils import SEARCH_ENGINES, START_URL, normalize_url  # noqa: F401
from ..security import MAX_URL_LENGTH
from ..validators import host_of, to_int as _to_int, to_nonneg_int as _to_nonneg_int, to_str as _to_str  # noqa: F401



class NavigationMixin:
    # 宿主 Api 成员声明（协议模式——运行时由组合后的 Api 提供）
    _engine: str
    history: Any
    window: Any
    _load: Callable[[str], bool]
    _eval: Callable[[str], bool]
    _notify: Callable[[str], bool]
    _update_current: Callable[..., None]
    _is_navigation_safe_url: Callable[[str], bool]
    # ---- 导航 ----
    def navigate(self, text: str) -> None:
        """导航到用户输入——地址栏 / 首页搜索框 / 右键"搜索选中文本"共用入口。

        P0-1 修复（搜索功能审计 2026-09-01）：移除入口的
        `_check_trusted_source()` 门槛。地址栏是注入到**每一个页面**顶部的
        浏览器 Chrome UI（`shell_toolbar.py` 的 `aegis-chrome`）——一旦离开
        首页，`current_url()` 返回远程 host，来源校验即把用户主动发起的
        地址栏导航 / 右键搜索 100% 静默拒绝（实测 7 场景仅 2 个可用，
        浏览器基本功能不可用）。

        安全取舍（威胁等价分析——不是放宽，是边界归位）：
          远程页面调用 `navigate()` 所能获得的权限，等价于它自身的
          `location.href` 赋值——浏览器里远程内容本就能导航自己；而
          `navigate()` 不写任何持久化状态（无书签/偏好/会话写入），
          因此"来源校验"对导航操作**没有增量安全收益**，只有功能代价。
          真正有效的边界是**导航目标**，故安全判断全部由
          `_is_navigation_safe_url()` 承担：协议白名单（http/https +
          about:blank）、userinfo/控制字符/无 host/非法端口/超长拒绝、
          威胁情报黑名单、Agent 域白名单。

        `_check_trusted_source()` 仍保留并用于**写操作**（书签增删改、
        搜索引擎偏好修改、会话恢复）——那里才是 M-2 的原始目标。
        """
        text = _to_str(text, "") or ""
        url = normalize_url(text, self._engine)
        # H-C1/A-② 审计修复：外部导航入口双层校验（协议安全 + 威胁黑名单）。
        # 只放行 http/https 与显式 about:blank；file:/javascript:/data:/blob:
        # 等一律拒绝；命中 threat_feed 黑名单域名同样拒绝。
        if not url:
            # P2 修复（全量复审 2026-09-01）：超长查询（中文 >8192 归一化为
            # 搜索 URL 后超 MAX_URL_LENGTH）/不可识别 scheme 此前静默拒——
            # 用户侧"点了没反应"。给出可见反馈（security.py 静默拒的出口）。
            self._notify("无法打开：地址无效或内容过长")
            try:
                from crash_reporter import log_event
                log_event(f"[bridge] 拒绝 navigate（归一化为空）: {text[:200]}")
            except Exception:
                pass
            return
        if not self._is_navigation_safe_url(url):
            # 可观测性 + P2 修复：旧实现静默 return，用户侧"点了没反应"。
            # 超长内容（中文长查询归一化为搜索 URL 后超 MAX_URL_LENGTH）给专用文案。
            if len(url) > MAX_URL_LENGTH:
                self._notify(f"无法打开：内容过长（上限 {MAX_URL_LENGTH} 字符）")
            else:
                self._notify("无法打开：地址未通过安全检查")
            try:
                from crash_reporter import log_event
                log_event(f"[bridge] 拒绝 navigate（目标不安全）: {url[:200]}")
            except Exception:
                pass
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
        """M-2 修复（防御性安全审查）：敏感**写操作**来源校验——当前标签
        URL 的 host 为空（本地壳页/新标签页）即受信；远程页面调用拒绝
        （防书签投毒/搜索引擎篡改——专家建议受信集）。

        适用范围：书签增删改、`set_engine` 偏好修改、会话恢复等**改变
        持久化状态**的操作。P0-1（2026-09-01）起**不再用于 navigate**——
        导航操作无持久化副作用，来源校验会误伤注入式地址栏 Chrome UI，
        详见 `navigate()` docstring 的威胁等价分析。"""
        w = self.window
        if w is None:
            return False
        # P2 修复（全量复审 2026-09-01）：不再经由吞异常的 current_url()——
        # 该路径下 get_current_url() 异常/为空都会得到 ""，host_of("")==""
        # 被误判为"本地壳页受信"。来源校验必须 fail-closed：拿不到 URL
        # 或 URL 为空 ≠ 本地壳页——一律拒绝。
        try:
            raw = w.get_current_url() or ""
        except Exception:
            return False
        if not raw:
            return False
        return host_of(raw) == ""

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

