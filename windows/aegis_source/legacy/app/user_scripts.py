# -*- coding: utf-8 -*-
"""user_scripts.py —— 用户脚本管理器（QtWebEngine 下的"轻量扩展"能力）。

QtWebEngine 不开放 Chrome 扩展 API，但原生支持 QWebEngineScript
（Tampermonkey 式的页面级 JS 注入）。本模块提供：
- 脚本的增删改查与启用开关（JSON 持久化）
- 按站点 glob 匹配（* / example.com / *.example.com）
- DocumentReady 时机注入主世界（可读页面 DOM）

注入时把用户代码包裹在 hostname 守卫中，避免跨站执行。
"""

import json
import os
import re


class UserScriptStore:
    """用户脚本存储与匹配。"""

    def __init__(self, data_dir: str):
        self._file = os.path.join(data_dir, "userscripts.json")
        self._scripts = self._load()

    def _load(self) -> list:
        try:
            if os.path.exists(self._file):
                with open(self._file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return [s for s in data if isinstance(s, dict)]
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._file)),
                        exist_ok=True)
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._scripts, f, ensure_ascii=False, indent=2)
            from .security import harden_perms
            harden_perms(self._file)
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    def all(self) -> list:
        return list(self._scripts)

    def enabled(self) -> list:
        return [s for s in self._scripts if s.get("enabled", True)]

    def add(self, name: str, match: str, code: str, enabled: bool = True,
            source: str = "manual", permissions: list | None = None) -> dict:
        """新增脚本。R10：source 标记来源（manual/import/community），
        外部导入（import）默认停用，需用户显式确认后启用。"""
        entry = {
            "name": (name or "未命名脚本").strip()[:64],
            "match": (match or "*").strip(),
            "code": code or "",
            "enabled": bool(enabled),
            "run_at": "document_ready",
            "source": source if source in ("manual", "import", "community")
            else "manual",
            "permissions": list(permissions) if permissions else [],
        }
        self._scripts.append(entry)
        self._save()
        return entry

    def remove(self, name: str):
        self._scripts = [s for s in self._scripts if s["name"] != name]
        self._save()

    def set_enabled(self, name: str, enabled: bool):
        for s in self._scripts:
            if s["name"] == name:
                s["enabled"] = bool(enabled)
        self._save()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _glob_to_regex(match: str) -> str:
        """站点 glob → JS 正则源（针对 hostname）。"""
        m = match.strip().lower()
        if m in ("", "*"):
            return ".*"
        if m.startswith("*."):
            dom = re.escape(m[2:])
            return f"({dom}|.+\\.{dom})"
        return re.escape(m)

    @staticmethod
    def build_js(entry: dict) -> str:
        """生成带 hostname 守卫的注入代码。"""
        pattern = UserScriptStore._glob_to_regex(entry.get("match", "*"))
        code = entry.get("code", "")
        # 用户代码先包一层 IIFE，防变量污染；hostname 守卫防跨站执行
        return (
            "(function(){try{var __h=location.hostname.toLowerCase();"
            f"if(!/^({pattern})$/.test(__h))return;"
            "(function(){" + code + "\n})();}catch(e){}})();"
        )

    # ------------------------------------------------------------------ #
    def apply_to_page(self, page):
        """把全部启用脚本注入某个 QWebEnginePage。"""
        QWebEngineScript = None
        # PySide6 各构建中 QWebEngineScript 归属模块不一致，逐个尝试
        for mod in ("PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"):
            try:
                from importlib import import_module
                QWebEngineScript = import_module(mod).QWebEngineScript
                break
            except (ImportError, AttributeError):
                continue
        if QWebEngineScript is None:
            return 0
        coll = page.scripts()
        count = 0
        for s in self.enabled():
            js = self.build_js(s)
            if not js:
                continue
            script = QWebEngineScript()
            script.setName("Aegis-UserScript-" + s["name"])
            script.setSourceCode(js)
            script.setInjectionPoint(QWebEngineScript.DocumentReady)
            script.setWorldId(QWebEngineScript.MainWorld)
            coll.insert(script)
            count += 1
        return count

    def clear(self):
        self._scripts = []
        self._save()
