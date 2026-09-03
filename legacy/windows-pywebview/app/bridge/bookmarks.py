"""BookmarksMixin（H-2 拆分自 api_bridge.py——方法体逐字迁移，零行为变更）。

M-1 后续：api_bridge 818 行超 500 行红线，按节拆分为 mixin 组合
（沿用 TabOpsMixin 先例 + 协议声明模式：TYPE_CHECKING 块声明宿主
成员，运行时由 Api 组合提供——无循环、无运行期开销）。
"""
from typing import Any, Callable

from ..url_utils import SEARCH_ENGINES, START_URL, normalize_url  # noqa: F401
from ..validators import host_of, to_int as _to_int, to_nonneg_int as _to_nonneg_int, to_str as _to_str  # noqa: F401



class BookmarksMixin:
    # 宿主 Api 成员声明（协议模式——运行时由组合后的 Api 提供）
    bookmarks: Any
    _data_dir: str
    _check_trusted_source: Callable[[], bool]
    window: Any  # 批次3-8 toggle_bookmark：服务端取当前页 URL 用
    # ================= 书签 =================
    def get_bookmarks(self) -> list:
        """返回书签列表 [{id,title,url}]（B0-W-01 复审：受信来源校验）。

        仅本地壳页（start.html 书签宫格）可达——远程页面调用返回空
        （原 B0-W-01 整改一刀切移除，导致宫格静默失效——本次恢复读取
        通道但维持「远程页零数据」边界）。"""
        if not self._check_trusted_source():
            try:
                from crash_reporter import log_event
                log_event("[bridge] 拒绝远程页面 get_bookmarks（来源不受信）")
            except Exception:
                pass
            return []
        try:
            if self.bookmarks is None:
                return []
            rows = self.bookmarks.all()
            # 行格式兼容：Database.query 返回 dict 行（r["id"]）——
            # 存量 bug（下标访问 dict → KeyError → 静默 []）：书签宫格
            # 即使有数据也一直显示空。统一 dict/tuple 双格式解析。
            out: list = []
            for r in rows:
                if isinstance(r, dict):
                    out.append({"id": r.get("id"), "title": r.get("title"),
                                "url": r.get("url")})
                else:
                    out.append({"id": r[0], "title": r[1], "url": r[2]})
            return out
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

    def _deny_remote(self, op: str) -> bool:
        """受信来源校验统一入口：远程页面调用 → 留痕并返回 True。

        返回 False = 来源受信（调用方继续执行）。新桥方法统一走此入口
        （存量方法保留各自内联块——本方法只收敛新增代码，不扩散改动）。
        """
        if self._check_trusted_source():
            return False
        try:
            from crash_reporter import log_event
            log_event(f"[bridge] 拒绝远程页面 {op}（来源不受信）")
        except Exception:
            pass
        return True

    def toggle_bookmark(self) -> str:
        """收藏/取消收藏当前页（P1-6 修复，全面审计批次3-8：书签无添加入口）。

        start.html 空书签文案引导用户「点收藏」——但工具栏从来没有收藏
        按钮，add_bookmark 零 UI 调用者（审计实证的「承诺性文案」）。

        威胁等价分析（不走 _check_trusted_source 的依据——与 navigate
        的 P0-1 同款思路）：本方法**零 JS 可控参数**——URL 一律服务端取
        （get_current_url），标题由 URL 派生。远程页面恶意调用的最坏效果
        = 把用户当前正在看的页面加入/移出书签（toast 可见、宫格可见、
        可再点撤销）——与导航按钮同风险级。反之来源校验会把收藏按钮
        锁死在壳页（远程页正是收藏的主场景），功能失去意义。

        仅 http/https 页面可收藏（壳页/内部页返回 unsupported）。
        返回 "added"/"removed"/"unsupported"/"error"（JS toast 依据）。
        """
        w = self.window
        if w is None:
            return "error"
        try:
            url = w.get_current_url() or ""
        except Exception:
            return "error"
        if not url:
            return "error"
        from ..security import scheme_of
        if scheme_of(url) not in ("http", "https"):
            return "unsupported"
        if self.bookmarks is None:
            return "error"
        try:
            if self.bookmarks.contains(url):
                self.bookmarks.remove(url)
                return "removed"
            # 标题由 URL 派生（页面真实 title 未采集——P2-7 关联债；
            # host+path 截断是当前信息面下的诚实选择）
            from ..validators import host_of
            host = host_of(url)
            title = host if host else url
            if len(title) > 48:
                title = title[:45] + "…"
            if self.bookmarks.add(title, url):
                return "added"
            return "error"
        except Exception:
            return "error"
