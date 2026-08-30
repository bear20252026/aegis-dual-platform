"""HistoryMixin（H-2 拆分自 api_bridge.py——方法体逐字迁移，零行为变更）。

M-1 后续：api_bridge 818 行超 500 行红线，按节拆分为 mixin 组合
（沿用 TabOpsMixin 先例 + 协议声明模式：TYPE_CHECKING 块声明宿主
成员，运行时由 Api 组合提供——无循环、无运行期开销）。
"""
from typing import Any

from ..url_utils import SEARCH_ENGINES, START_URL, normalize_url  # noqa: F401
from ..validators import host_of, to_int as _to_int, to_nonneg_int as _to_nonneg_int, to_str as _to_str  # noqa: F401



class HistoryMixin:
    # 宿主 Api 成员声明（协议模式——运行时由组合后的 Api 提供）
    history: Any

    # ================= 历史 =================
    @staticmethod
    def _row_to_tuple(r):
        """历史行统一为 (id,url,title,visit_time) 元组（dict/tuple 双格式）。"""
        if isinstance(r, dict):
            return (r.get("id"), r.get("url"), r.get("title"), r.get("visit_time"))
        return (r[0], r[1], r[2], r[3])

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
                rid, url, title, visit_time = self._row_to_tuple(r)
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
                rid, url, title, visit_time = self._row_to_tuple(r)
                out.append({
                    "id": rid, "url": url, "title": title,
                    "visit_time": visit_time,
                })
            return out
        except Exception:
            return []

