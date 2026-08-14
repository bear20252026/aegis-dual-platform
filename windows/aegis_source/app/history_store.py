"""history_store.py —— 基于 SQLite 的历史记录存储。

采用与主流浏览器一致的访问日志模型：一个 URL 可对应多条访问记录，
并按访问时间倒序展示。搜索走 LIKE，附带时间戳聚合的"今日/本周"分组。
"""

import os
import time
from datetime import datetime, timezone

from .database import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    visit_time INTEGER NOT NULL,      -- unix 秒
    visit_count INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_visits_time ON visits(visit_time DESC);
CREATE INDEX IF NOT EXISTS idx_visits_url ON visits(url);
-- 落地建议③（借鉴 min fullTextSearch）：FTS5 全文索引（url+title），
-- 通过触发器与 visits 保持同步；新库自动生效，旧库在首次查询时重建。
CREATE VIRTUAL TABLE IF NOT EXISTS visits_fts USING fts5(
    url, title, content='visits', content_rowid='id', tokenize='unicode61');
CREATE TRIGGER IF NOT EXISTS visits_fts_ai AFTER INSERT ON visits BEGIN
    INSERT INTO visits_fts(rowid, url, title)
    VALUES (new.id, new.url, new.title);
END;
CREATE TRIGGER IF NOT EXISTS visits_fts_ad AFTER DELETE ON visits BEGIN
    INSERT INTO visits_fts(visits_fts, rowid, url, title)
    VALUES ('delete', old.id, old.url, old.title);
END;
CREATE TRIGGER IF NOT EXISTS visits_fts_au AFTER UPDATE ON visits BEGIN
    INSERT INTO visits_fts(visits_fts, rowid, url, title)
    VALUES ('delete', old.id, old.url, old.title);
    INSERT INTO visits_fts(rowid, url, title)
    VALUES (new.id, new.url, new.title);
END;
"""


class HistoryStore:
    """历史记录存储。enabled=False（无痕）时不读写数据库。"""

    def __init__(self, data_dir: str, enabled: bool = True):
        self._enabled = enabled
        self._db = None
        if enabled:
            self._db = Database(os.path.join(data_dir, "history.db"), SCHEMA)

    # ------------------------------------------------------------------ #
    def _check(self):
        """无痕模式使用内存库以彻底不落盘。"""
        if self._enabled and self._db is None:
            self._db = Database(":memory:", SCHEMA)
        return self._db

    def add(self, url: str, title: str = ""):
        db = self._check()
        if db is None or not url or url.startswith("about:"):
            return
        db.execute(
            "INSERT INTO visits(url,title,visit_time) VALUES(?,?,?)",
            (url, title or url, int(time.time())))

    def all(self, limit=500):
        db = self._check()
        if db is None:
            return []
        return db.query(
            "SELECT id,url,title,visit_time FROM visits "
            "ORDER BY visit_time DESC LIMIT ?", (limit,))

    def search(self, keyword: str, limit=50):
        db = self._check()
        if db is None:
            return []
        kw = f"%{keyword}%"
        return db.query(
            "SELECT id,url,title,visit_time,MAX(visit_time) "
            "FROM visits WHERE url LIKE ? OR title LIKE ? "
            "GROUP BY url ORDER BY MAX(visit_time) DESC LIMIT ?",
            (kw, kw, limit))

    def suggest(self, keyword: str, limit=12):
        """地址栏联想：返回 (url, title, score)。"""
        rows = self.search(keyword, limit * 4)
        results = []
        for r in rows:
            url = r["url"]
            title = r["title"]
            # 前缀命中优先
            score = 0
            if url.lower().startswith(keyword.lower()):
                score += 100
            elif keyword.lower() in url.lower():
                score += 50
            if keyword.lower() in title.lower():
                score += 20
            results.append((url, title, score))
        results.sort(key=lambda x: -x[2])
        return results[:limit]

    def delete_url(self, url: str):
        db = self._check()
        if db:
            db.execute("DELETE FROM visits WHERE url=?", (url,))

    def fulltext_search(self, keyword: str, limit=50):
        """FTS5 全文搜索历史（落地建议③，借鉴 min fullTextSearch）。

        对 url+title 做全文索引查询；旧库首次查询时重建索引。
        FTS5 不可用时回退 LIKE 搜索（功能不失效）。
        """
        db = self._check()
        if db is None or not keyword:
            return []
        kw = keyword.strip()
        if not kw:
            return []
        # 尝试 FTS5（含旧库索引重建）；失败静默回退 LIKE
        try:
            self._ensure_fts_rebuilt(db)
            # FTS5 MATCH 语法：用户输入做短语化，防语法注入
            quoted = '"' + kw.replace('"', '""') + '"'
            rows = db.query(
                "SELECT id,url,title,visit_time FROM visits_fts "
                "WHERE visits_fts MATCH ? ORDER BY rank LIMIT ?",
                (quoted, limit))
            if rows:
                return rows
        except Exception:
            pass  # FTS5 不可用/损坏 → 回退 LIKE
        # 回退：LIKE 子串匹配
        kw2 = f"%{kw}%"
        return db.query(
            "SELECT id,url,title,visit_time FROM visits "
            "WHERE url LIKE ? OR title LIKE ? "
            "ORDER BY visit_time DESC LIMIT ?", (kw2, kw2, limit))

    @staticmethod
    def _ensure_fts_rebuilt(db):
        """旧库（无 FTS 索引内容）时重建，保证新库/旧库行为一致。"""
        try:
            # 'rebuild' 对 content= 外部内容表安全且幂等
            db.execute("INSERT INTO visits_fts(visits_fts) VALUES('rebuild')")
        except Exception:
            pass  # 空表 rebuild 也可能报错，忽略

    def clear(self):
        db = self._check()
        if db:
            db.execute("DELETE FROM visits")

    def stats(self) -> dict:
        db = self._check()
        if db is None:
            return {"total": 0, "today": 0}
        # DTZ005 修复：now() 显式传 UTC 再转本地时区，保持"本地今日"语义
        now_local = datetime.now(timezone.utc).astimezone()
        today_start = int(now_local.replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp())
        return {
            "total": db.query_one("SELECT COUNT(*) n FROM visits")["n"],
            "today": db.query_one(
                "SELECT COUNT(*) n FROM visits WHERE visit_time>=?",
                (today_start,))["n"],
        }

    def most_visited(self, limit=12) -> list:
        """最近 30 天访问最多的 URL，用于快捷拨号首页。"""
        db = self._check()
        if db is None:
            return []
        cutoff = int(time.time()) - 30 * 24 * 3600
        return db.query(
            "SELECT url,title,COUNT(*) c FROM visits "
            "WHERE visit_time>=? GROUP BY url ORDER BY c DESC, "
            "MAX(visit_time) DESC LIMIT ?", (cutoff, limit))
