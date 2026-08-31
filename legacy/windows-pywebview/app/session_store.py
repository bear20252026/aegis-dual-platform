"""session_store.py —— 标签会话持久化（单文件单职责）。

CHANGELOG「Unreleased/Planned：会话恢复」落地：
- save()：标签快照 → session.json（原子写：tmp + os.replace，防半写损坏）；
- load()：读取 + 白名单清洗（防御性：会话文件即使被篡改也不产生危险导航）；
- 清洗规则：URL 仅允许 http/https 与受信壳页 START_URL（file: 只放行
  入口 start.html 本身），title/group 截断，pinned 强制布尔，≤ MAX_TABS。

安全边界：
- 本文件只落盘浏览器自身会话（与 bookmark_store/history_store 同级信任）；
- 绝不保存 about:blank / javascript: / data: 等协议（fail-closed——清洗
  不通过的标签直接丢弃，不做降级改写）。
"""

from __future__ import annotations

import json
import os
from typing import Any

from .url_utils import START_URL

SESSION_FILE = "session.json"
MAX_TABS = 20

_SCHEMA_VERSION = 1


def _url_savable(url: str) -> bool:
    """URL 白名单：http/https 或受信壳页 START_URL 本身。"""
    if not isinstance(url, str) or not url:
        return False
    if url.startswith(("http://", "https://")):
        return True
    return url == START_URL


def _sanitize_tab(tab: Any) -> dict | None:
    """单标签清洗；不合规返回 None（调用方丢弃）。"""
    if not isinstance(tab, dict):
        return None
    url = tab.get("url")
    if not isinstance(url, str) or not _url_savable(url):
        return None
    title = str(tab.get("title") or "新标签页")[:80]
    group = str(tab.get("group") or "默认")[:32]
    return {
        "title": title,
        "url": url,
        "pinned": bool(tab.get("pinned")),
        "group": group,
    }


class SessionStore:
    """标签会话存取（data_dir/session.json）。"""

    def __init__(self, data_dir: str) -> None:
        self._dir = data_dir or ""

    @property
    def path(self) -> str:
        return os.path.join(self._dir, SESSION_FILE)

    def save(self, tabs: list[dict], current: int) -> bool:
        """保存标签快照（清洗 + 原子写）。失败返回 False（静默降级）。"""
        if not self._dir:
            return False
        clean = [t for t in (_sanitize_tab(x) for x in tabs) if t is not None]
        if not clean:
            return False
        cur = current if isinstance(current, int) else 0
        cur = min(max(cur, 0), len(clean) - 1)
        payload = {"version": _SCHEMA_VERSION, "current": cur, "tabs": clean}
        tmp = self.path + ".tmp"
        try:
            os.makedirs(self._dir, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, self.path)  # 原子替换（Windows 同卷支持）
            # M-2 修复（审计 2026-08-31）：session.json 保存完整浏览 URL——
            # 与 database.py/threat_feed.py 同级敏感度，落盘后收紧 ACL
            # （0600 / 仅当前用户），否则同机其他账户可读
            try:
                from .security import harden_perms
                harden_perms(self.path)
            except Exception:
                pass  # 权限收紧失败不阻断保存（静默降级——与全文件口径一致）
            return True
        except OSError:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            return False

    def load(self) -> dict | None:
        """读取会话；不存在/损坏/清洗后为空 → None。"""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("version") != _SCHEMA_VERSION:
            return None
        raw_tabs = data.get("tabs")
        if not isinstance(raw_tabs, list):
            return None
        clean = [t for t in (_sanitize_tab(x) for x in raw_tabs[:MAX_TABS])
                 if t is not None]
        if not clean:
            return None
        cur = data.get("current")
        cur = cur if isinstance(cur, int) else 0
        return {"tabs": clean, "current": min(max(cur, 0), len(clean) - 1)}
