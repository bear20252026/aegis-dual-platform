# -*- coding: utf-8 -*-
"""session.py —— 会话管理。

记录当前打开的标签页（URL / 标题 / 激活状态），支持崩溃后或主动恢复。
数据以 JSON 保存在用户数据目录下，供启动时"恢复上次会话"使用。
"""

import json
import os


class SessionManager:
    def __init__(self, data_dir: str, enabled: bool = True):
        self._enabled = enabled
        self._file = os.path.join(data_dir, "session.json")

    def save(self, tabs, active_index: int):
        """tabs: [(url, title)] 或 [(url, title, pinned, group)]。

        pinned/group 用于重启后恢复固定标签与分组（旧格式缺失时默认 False/""）。
        """
        if not self._enabled:
            return
        out = []
        for t in tabs:
            u = t[0] if t else ""
            if not u or u.startswith("about:"):
                continue
            title = t[1] if len(t) > 1 else ""
            pinned = bool(t[2]) if len(t) > 2 else False
            group = t[3] if len(t) > 3 else ""
            out.append({"url": u, "title": title,
                        "pinned": pinned, "group": group})
        data = {"active": active_index, "tabs": out}
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._file)),
                        exist_ok=True)
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # POSIX 权限收紧（v1.4 L10）
            from .security import harden_perms
            harden_perms(self._file)
        except OSError:
            pass

    def load(self):
        """返回 (tabs, active_index)，无会话则 ([] , 0)。

        tabs 元素为 (url, title, pinned, group)，兼容旧版无该两字段的会话文件。
        """
        if not os.path.exists(self._file):
            return [], 0
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)
            tabs = []
            for t in data.get("tabs", []):
                if not isinstance(t, dict):
                    continue
                tabs.append((t.get("url", ""), t.get("title", ""),
                             bool(t.get("pinned", False)),
                             str(t.get("group", "") or "")))
            return tabs, data.get("active", 0)
        except (json.JSONDecodeError, OSError):
            return [], 0

    def clear(self):
        try:
            os.remove(self._file)
        except OSError:
            pass
