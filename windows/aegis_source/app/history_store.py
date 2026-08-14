# -*- coding: utf-8 -*-
"""history_store.py —— 基于 SQLite 的历史记录存储。

采用与主流浏览器一致的访问日志模型：一个 URL 可对应多条访问记录，
并按访问时间倒序展示。搜索走 LIKE，附带时间戳聚合的"今日/本周"分组。
"""

import os
import time
from datetime import datetime, timedelta

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

    def clear(self):
        db = self._check()
        if db:
            db.execute("DELETE FROM visits")

    def stats(self) -> dict:
        db = self._check()
        if db is None:
            return {"total": 0, "today": 0}
        today_start = int(datetime.now().replace(
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
