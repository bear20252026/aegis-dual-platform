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

# 导入向导来源表（key → 用户数据目录；顺序即 UI 展示优先级）
_SOURCES = (("chrome", _CHROME_DIR), ("edge", _EDGE_DIR))

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


# W-03 整改（国防级审查）：本机 Chrome/Edge 导入仅允许原生受信 UI 明示
# 授权的最小读取（JS 桥入口已断——B0-W-01 从 _JS_EXPOSED 移除
# import_bookmarks/import_history——恶意页面不可触发导入）
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


def find_import_sources() -> list:
    """探测本机可导入来源（仅探测文件存在——不读取内容）。

    返回 [{"browser": "chrome"|"edge", "bookmarks": bool, "history": bool}]；
    供导入向导第一步展示（扫描不产生任何读取/写入副作用）。
    """
    out: list = []
    for key, base in _SOURCES:
        if not base:
            continue
        bm = os.path.isfile(os.path.join(base, "Default", "Bookmarks"))
        hi = os.path.isfile(os.path.join(base, "Default", "History"))
        if bm or hi:
            out.append({"browser": key, "bookmarks": bm, "history": hi})
    return out


def _iter_source_files(filename: str, source: str = ""):
    """按来源过滤迭代本机存在的浏览器数据文件（yield (来源key, 路径)）。

    source 为空 = 全部来源（chrome 优先）；非空仅匹配该来源。
    来源 key 显式随路径返回（不从路径猜浏览器——防目录布局变化误判）。
    """
    for key, base in _SOURCES:
        if source and key != source:
            continue
        if not base:
            continue
        path = os.path.join(base, "Default", filename)
        if os.path.isfile(path):
            yield key, path


def find_bookmarks_files(source: str = "") -> Iterable:
    """返回本机存在的 Chrome / Edge Bookmarks（yield (来源key, 路径)）。

    Chrome 优先，其次 Edge；均缺失时为空迭代。source 可选
    （"chrome"/"edge"——导入向导按来源导入；空=全部）。
    """
    yield from _iter_source_files("Bookmarks", source)


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


def find_history_files(source: str = "") -> Iterable:
    """返回本机存在的 Chrome / Edge History（yield (来源key, 路径)）。

    source 可选（"chrome"/"edge"；空=全部）。
    """
    yield from _iter_source_files("History", source)
