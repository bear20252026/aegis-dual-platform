"""bookmark_store.py —— 基于 SQLite 的书签存储。

支持多级文件夹 + 排序。并提供导出为标准 Netscape bookmark HTML 格式
（可被 Chrome/Firefox/Edge 导入）与从该格式导入的能力。
"""

import os
import time

from .database import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER DEFAULT 0,
    sort INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    folder_id INTEGER DEFAULT 0,
    sort INTEGER DEFAULT 0,
    created INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bm_url ON bookmarks(url);
"""


class BookmarkStore:
    def __init__(self, data_dir: str, enabled: bool = True):
        self._db = None
        if enabled:
            self._db = Database(os.path.join(data_dir, "bookmarks.db"), SCHEMA)

    def _check(self):
        if self._db is None:
            self._db = Database(":memory:", SCHEMA)
        return self._db

    def add(self, title: str, url: str, folder_id=0) -> bool:
        db = self._check()
        if not url:
            return False
        if db.query_one("SELECT id FROM bookmarks WHERE url=?",
                        (url,)) is not None:
            return False
        db.execute(
            "INSERT INTO bookmarks(title,url,folder_id,created) "
            "VALUES(?,?,?,?)", (title or url, url, folder_id, int(time.time())))
        return True

    def remove(self, url: str):
        db = self._check()
        db.execute("DELETE FROM bookmarks WHERE url=?", (url,))

    def remove_by_id(self, bm_id: int):
        db = self._check()
        db.execute("DELETE FROM bookmarks WHERE id=?", (bm_id,))

    def contains(self, url: str) -> bool:
        db = self._check()
        return db.query_one("SELECT id FROM bookmarks WHERE url=?",
                            (url,)) is not None

    def all(self):
        db = self._check()
        return db.query(
            "SELECT id,title,url,folder_id FROM bookmarks "
            "ORDER BY folder_id, sort, id")

    def in_folder(self, folder_id=0):
        db = self._check()
        return db.query(
            "SELECT id,title,url FROM bookmarks WHERE folder_id=? "
            "ORDER BY sort, id", (folder_id,))

    def search(self, keyword, limit=20):
        db = self._check()
        kw = f"%{keyword}%"
        return db.query(
            "SELECT id,title,url FROM bookmarks "
            "WHERE url LIKE ? OR title LIKE ? ORDER BY sort LIMIT ?",
            (kw, kw, limit))

    def suggest(self, keyword, limit=12):
        rows = self.search(keyword, limit * 4)
        out = []
        for r in rows:
            score = 100 if r["url"].lower().startswith(keyword.lower()) else 40
            out.append((r["url"], r["title"], score))
        out.sort(key=lambda x: -x[2])
        return out[:limit]

    def add_folder(self, name: str, parent_id=0) -> int:
        db = self._check()
        cur = db.execute(
            "INSERT INTO folders(name,parent_id) VALUES(?,?)",
            (name, parent_id))
        return cur.lastrowid

    def folders(self):
        db = self._check()
        return db.query("SELECT id,name FROM folders ORDER BY id")

    def clear(self):
        db = self._check()
        db.execute("DELETE FROM bookmarks")
        db.execute("DELETE FROM folders")

    # ------------------------------------------------------------------ #
    # 导入 / 导出（标准 Netscape 书签 HTML 格式）
    # ------------------------------------------------------------------ #
    def export_html(self, path: str):
        db = self._check()
        rows = db.query("SELECT title,url FROM bookmarks ORDER BY sort,id")
        lines = [
            "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
            "<META HTTP-EQUIV=\"Content-Type\" CONTENT=\"text/html; charset=UTF-8\">",
            "<TITLE>Bookmarks</TITLE>",
            "<H1>Bookmarks</H1>",
            "<DL><p>",
        ]
        for r in rows:
            title = (r["title"] or r["url"]).replace("&", "&amp;").replace(
                "<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            lines.append(
                f'    <DT><A HREF="{r["url"]}">{title}</A>')
        lines.append("</DL><p>")
        try:
            # 相对文件名（如 "bookmarks.html"）时 dirname 为空，makedirs 会抛错
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return True
        except OSError:
            return False

    def import_html(self, path: str) -> int:
        """导入 Netscape 书签 HTML，返回新增数量。"""
        import re
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return 0
        count = 0
        # 提取 <A HREF="url">title</A>
        pattern = re.compile(
            r'<A\s+HREF="([^"]+)"[^>]*>(.*?)</A>', re.IGNORECASE | re.DOTALL)
        for url, title in pattern.findall(text):
            title = re.sub(r"<[^>]+>", "", title).strip()
            if self.add(title, url):
                count += 1
        return count
