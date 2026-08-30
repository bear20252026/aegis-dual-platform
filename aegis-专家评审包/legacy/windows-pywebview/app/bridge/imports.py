"""ImportMixin（H-2 拆分自 api_bridge.py——方法体逐字迁移，零行为变更）。

M-1 后续：api_bridge 818 行超 500 行红线，按节拆分为 mixin 组合
（沿用 TabOpsMixin 先例 + 协议声明模式：TYPE_CHECKING 块声明宿主
成员，运行时由 Api 组合提供——无循环、无运行期开销）。
"""
from typing import Any, Callable

from ..url_utils import SEARCH_ENGINES, START_URL, normalize_url  # noqa: F401
from ..validators import host_of, to_int as _to_int, to_nonneg_int as _to_nonneg_int, to_str as _to_str  # noqa: F401



class ImportMixin:
    # 宿主 Api 成员声明（协议模式——运行时由组合后的 Api 提供）
    bookmarks: Any
    history: Any
    _deny_remote: Callable[[str], bool]
    # ================= 导入向导（Chrome/Edge 书签与历史） =================
    def scan_import_sources(self) -> list:
        """探测本机可导入来源（仅探测文件存在——不读取任何内容）。

        返回 [{"browser": "chrome"|"edge", "bookmarks": bool,
        "history": bool}]；受信来源校验在方法内（远程页返回空）。
        """
        if self._deny_remote("scan_import_sources"):
            return []
        try:
            from ..browser_import import find_import_sources
            return find_import_sources()
        except Exception:
            return []

    def import_bookmarks(self, source: str = "") -> dict:
        """从 Chrome/Edge 导入书签（导入向导执行步）。

        source 可选（"chrome"/"edge"；空=全部来源）。返回
        {"imported": 总新增, "total": 解析总数,
         "results": [{"browser", "imported", "total"}, ...]}。
        解析失败或存储不可用时静默返回 0（导入是可选功能，不影响浏览）。
        """
        if self._deny_remote("import_bookmarks"):
            return {"imported": 0, "total": 0, "results": []}
        src = _to_str(source, "") or ""
        if src not in ("", "chrome", "edge"):
            src = ""
        out: dict = {"imported": 0, "total": 0, "results": []}
        try:
            from ..browser_import import find_bookmarks_files, parse_bookmarks_json
            for browser, path in find_bookmarks_files(src):
                items = parse_bookmarks_json(path)
                imported = 0
                for item in items:
                    if (self.bookmarks is not None
                            and self.bookmarks.add(item["title"], item["url"])):
                        imported += 1
                out["results"].append(
                    {"browser": browser, "imported": imported,
                     "total": len(items)})
                out["imported"] += imported
                out["total"] += len(items)
        except Exception:
            pass
        return out

    def import_history(self, limit: Any = 500, source: str = "") -> dict:
        """从 Chrome/Edge 导入最近历史（导入向导执行步）。

        limit 为每来源条数上限（1–2000，默认 500）；source 同
        import_bookmarks。返回结构同 import_bookmarks。
        """
        if self._deny_remote("import_history"):
            return {"imported": 0, "total": 0, "results": []}
        n = _to_nonneg_int(limit, 500) or 500
        n = min(n, 2000)
        src = _to_str(source, "") or ""
        if src not in ("", "chrome", "edge"):
            src = ""
        out: dict = {"imported": 0, "total": 0, "results": []}
        try:
            from ..browser_import import find_history_files, parse_history_db
            for browser, path in find_history_files(src):
                items = parse_history_db(path, n)
                imported = 0
                for item in items:
                    if self.history is not None:
                        # HistoryStore.add 为 visit 追加（无返回值/无去重
                        # ——历史是访问流水不是键值表）——计数即解析条数
                        self.history.add(item["url"], item["title"])
                        imported += 1
                out["results"].append(
                    {"browser": browser, "imported": imported,
                     "total": len(items)})
                out["imported"] += imported
                out["total"] += len(items)
        except Exception:
            pass
        return out

