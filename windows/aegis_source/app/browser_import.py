"""browser_import.py —— 解析 Chrome / Edge 书签（单文件单职责）。

职责：定位并解析 Chrome / Edge 的 Bookmarks 文件（JSON 格式），
输出扁平书签列表 [{title, url}, ...] 供导入向导使用。

设计原则（与项目 P0 一致）：
- **只做解析**：本模块不写任何存储（写入由 BookmarkStore 承担），
  返回纯数据，便于单测与复用；
- **防御式解析**：文件缺失 / JSON 损坏 / 字段缺失一律静默跳过，
  绝不抛异常（导入是可选功能，失败不影响浏览）；
- **只提取 url 节点**：递归遍历 folder，跳过空标题 / 无效 URL；
  去重保证同一 URL 只导入一次。

Chrome/Edge Bookmarks 文件结构（两者一致）：
    { "roots": { "bookmark_bar": <node>, "other": <node>, "synced": <node> } }
    node = { "type": "url"|"folder", "name": str,
             "url": str（url 节点）, "children": [node...]（folder 节点） }
"""

import json
import os
import sqlite3
from collections.abc import Iterable

# 合法 URL scheme（导入时仅接受这些，避免 data:/javascript: 等注入）
_ALLOWED_SCHEMES = {"http", "https"}

# Chrome / Edge 用户数据目录（Windows）
_CHROME_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
_EDGE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data")

# roots 中按序检查的顶层节点（bar 优先，其次 other/synced）
_ROOT_KEYS = ("bookmark_bar", "other", "synced")


def _scheme_ok(url: str) -> bool:
    """仅接受 http/https（防 data:/javascript: 等）。"""
    try:
        scheme = url.split(":", 1)[0].lower()
    except Exception:
        return False
    return scheme in _ALLOWED_SCHEMES


def _walk(node, out: list, seen: set) -> None:
    """递归遍历书签节点；url 节点去重后加入 out。"""
    if not isinstance(node, dict):
        return
    ntype = node.get("type")
    if ntype == "url":
        url = node.get("url") or ""
        if not _scheme_ok(url):
            return
        if url in seen:
            return
        seen.add(url)
        title = (node.get("name") or "").strip() or url
        out.append({"title": title, "url": url})
    elif ntype == "folder":
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                _walk(child, out, seen)


def parse_bookmarks_json(path: str) -> list:
    """解析指定 Bookmarks JSON 文件，返回 [{title, url}, ...]。

    文件缺失 / JSON 损坏 / 无 roots 时返回空列表（不抛异常）。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    roots = data.get("roots") if isinstance(data, dict) else None
    if not isinstance(roots, dict):
        return []
    out: list = []
    seen: set = set()
    for key in _ROOT_KEYS:
        _walk(roots.get(key), out, seen)
    return out


def find_bookmarks_files() -> Iterable[str]:
    """返回本机存在的 Chrome / Edge Bookmarks 文件路径（按序）。

    Chrome 优先，其次 Edge；均缺失时为空迭代。
    """
    for base in (_CHROME_DIR, _EDGE_DIR):
        # 默认用户目录（Default）；忽略其他 Profile 目录，保持简单可预期
        path = os.path.join(base, "Default", "Bookmarks")
        if os.path.isfile(path):
            yield path


def parse_history_db(path: str, limit: int = 500) -> list:
    """解析 Chrome / Edge 的 History SQLite，返回 [{title, url}, ...]。

    只读打开（uri mode=ro，避免锁定浏览器的实时数据库）；按
    last_visit_time 倒序取最近 limit 条；字段缺失/损坏静默跳过。
    """
    if not os.path.isfile(path):
        return []
    out: list = []
    seen: set = set()
    try:
        # mode=ro + immutable 提示：只读访问，绝不写浏览器的数据库
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3.0)
        try:
            cur = conn.execute(
                "SELECT url, title FROM urls "
                "WHERE title IS NOT NULL AND title != '' "
                "ORDER BY last_visit_time DESC LIMIT ?", (int(limit),))
            for url, title in cur.fetchall():
                if not _scheme_ok(url or "") or url in seen:
                    continue
                seen.add(url)
                out.append({"title": (title or "").strip() or url, "url": url})
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return []
    return out


def find_history_files() -> Iterable[str]:
    """返回本机存在的 Chrome / Edge History 文件路径（按序）。"""
    for base in (_CHROME_DIR, _EDGE_DIR):
        path = os.path.join(base, "Default", "History")
        if os.path.isfile(path):
            yield path
