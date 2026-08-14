# -*- coding: utf-8 -*-
"""reading_list.py —— 阅读清单（稍后读的轻量实现）。"""

import time

from .database import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS reading_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    added INTEGER NOT NULL,
    read INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_rl_url ON reading_list(url);
"""


class ReadingList:
    def __init__(self, data_dir: str):
        import os
        self._db = Database(os.path.join(data_dir, "reading.db"), SCHEMA)

    def add(self, url: str, title: str = "") -> bool:
        if not url:
            return False
        if self.contains(url):
            return False
        self._db.execute(
            "INSERT INTO reading_list(url,title,added) VALUES(?,?,?)",
            (url, title or url, int(time.time())))
        return True

    def contains(self, url: str) -> bool:
        return self._db.query_one(
            "SELECT id FROM reading_list WHERE url=?", (url,)) is not None

    def all(self):
        return self._db.query(
            "SELECT id,url,title,added,read FROM reading_list "
            "ORDER BY added DESC")

    def mark_read(self, url: str, read: bool = True):
        self._db.execute("UPDATE reading_list SET read=? WHERE url=?",
                         (1 if read else 0, url))

    def remove(self, url: str):
        self._db.execute("DELETE FROM reading_list WHERE url=?", (url,))

    def clear_read(self):
        self._db.execute("DELETE FROM reading_list WHERE read=1")
