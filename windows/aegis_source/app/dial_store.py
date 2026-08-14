# -*- coding: utf-8 -*-
"""dial_store.py —— 新标签页自定义拨号（首页图标）持久化（v2.1.5）。

用户可自定义新标签页显示的快捷拨号（首页图标）：增删、改名、排序，
持久化在配置文件目录 `dials.json`。NTP（HTML 版与 Qt 版）优先读取该
自定义列表；列表为空时回退到"历史常用 + 书签 + 内置默认"的自动组合。

安全（P0）：
- URL 仅在**展示与点击导航**时使用，点击后仍经主窗口 safe_url 关口过滤；
- 存储结构做逐字段类型校验（name 截断、url 白名单 scheme），拒绝畸形注入。
"""

import json
import os

_MAX_DIALS = 24
_NAME_MAX = 40

# 只允许进入拨号的 scheme（与导航关口一致的最小集）
_ALLOWED_SCHEMES = ("http://", "https://")


class DialStore:
    """自定义拨号存储。条目：{"name": str, "url": str}，顺序即展示顺序。"""

    def __init__(self, data_dir: str):
        self._file = os.path.join(data_dir, "dials.json")
        self._items = self._load()

    # ------------------------------------------------------------------ #
    def _load(self) -> list:
        try:
            if os.path.exists(self._file):
                with open(self._file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    out = []
                    for it in data:
                        if not isinstance(it, dict):
                            continue
                        name = str(it.get("name", "")).strip()[:_NAME_MAX]
                        url = str(it.get("url", "")).strip()
                        if url.lower().startswith(_ALLOWED_SCHEMES):
                            out.append({"name": name or url, "url": url})
                    return out[:_MAX_DIALS]
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._file)),
                        exist_ok=True)
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._items, f, ensure_ascii=False, indent=2)
            from .security import harden_perms
            harden_perms(self._file)
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    def all(self) -> list:
        """返回 [(name, url)]，顺序即展示顺序。"""
        return [(it["name"], it["url"]) for it in self._items]

    def is_customized(self) -> bool:
        """用户是否已自定义（列表非空即视为启用自定义）。"""
        return bool(self._items)

    def contains(self, url: str) -> bool:
        return any(it["url"] == url for it in self._items)

    def add(self, name: str, url: str) -> bool:
        """新增一条拨号（去重 + scheme 白名单 + 上限）。"""
        name = (name or "").strip()[:_NAME_MAX]
        url = (url or "").strip()
        if not url.lower().startswith(_ALLOWED_SCHEMES):
            return False
        if len(self._items) >= _MAX_DIALS:
            return False
        if not name:
            from urllib.parse import urlparse
            try:
                name = (urlparse(url).hostname or url)[:_NAME_MAX]
            except Exception:
                name = url[:_NAME_MAX]
        if self.contains(url):
            return False
        self._items.append({"name": name, "url": url})
        self._save()
        return True

    def remove(self, url: str):
        self._items = [it for it in self._items if it["url"] != url]
        self._save()

    def rename(self, url: str, name: str):
        name = (name or "").strip()[:_NAME_MAX]
        for it in self._items:
            if it["url"] == url and name:
                it["name"] = name
        self._save()

    def move(self, index: int, delta: int):
        """把第 index 条上移(delta<0)/下移(delta>0)。"""
        j = index + delta
        if 0 <= index < len(self._items) and 0 <= j < len(self._items):
            self._items[index], self._items[j] = \
                self._items[j], self._items[index]
            self._save()

    def clear(self):
        self._items = []
        try:
            os.remove(self._file)
        except OSError:
            pass
