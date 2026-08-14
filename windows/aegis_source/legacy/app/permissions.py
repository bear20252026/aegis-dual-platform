# -*- coding: utf-8 -*-
"""permissions.py —— 站点权限管理（摄像头/麦克风/位置/通知）。

决策模型与主流浏览器一致：每个 (站点, 权限) 一条决策
（allow / deny / ask），持久化到 permissions.json。
UI 层在页面请求权限时：ask 弹对话框，其余直接应用。
"""

import json
import os

from PySide6.QtWebEngineCore import QWebEnginePage


def _fk(feature) -> int:
    try:
        return int(feature)
    except Exception:
        return int(getattr(feature, "value", feature))


# Qt feature -> 可读名称（int 键，跨版本稳定）
FEATURE_NAMES = {}
for _feat, _label in (
    (QWebEnginePage.Notifications, "通知"),
    (QWebEnginePage.Geolocation, "位置信息"),
    (QWebEnginePage.MediaAudioCapture, "麦克风"),
    (QWebEnginePage.MediaVideoCapture, "摄像头"),
    (QWebEnginePage.MediaAudioVideoCapture, "摄像头和麦克风"),
):
    FEATURE_NAMES[_fk(_feat)] = _label

ALLOW = "allow"
DENY = "deny"
ASK = "ask"


class PermissionStore:
    """站点权限决策存储（JSON 文件）。"""

    def __init__(self, data_dir: str):
        self._file = os.path.join(data_dir, "permissions.json")
        self._data = self._load()

    def _load(self) -> dict:
        try:
            if os.path.exists(self._file):
                with open(self._file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._file)),
                        exist_ok=True)
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    @staticmethod
    def _feat_key(feature) -> int:
        """把 Qt feature 枚举稳定转为 int（Qt6 scoped enum 不支持 int(...)直转）。"""
        try:
            return int(feature)
        except Exception:
            return int(getattr(feature, "value", feature))

    @staticmethod
    def host_of(url) -> str:
        from urllib.parse import urlparse
        try:
            return (urlparse(str(url)).hostname or "").lower()
        except Exception:
            return ""

    @classmethod
    def feat_name(cls, feature) -> str:
        return FEATURE_NAMES.get(cls._feat_key(feature),
                                 f"权限 {cls._feat_key(feature)}")

    def decision(self, host: str, feature) -> str:
        return self._data.get(host, {}).get(str(self._feat_key(feature)), ASK)

    def set_decision(self, host: str, feature, decision: str):
        if not host:
            return
        self._data.setdefault(host, {})[str(self._feat_key(feature))] = decision
        self._save()

    def forget(self, host: str):
        self._data.pop(host, None)
        self._save()

    def clear_all(self):
        self._data = {}
        self._save()

    def all_sites(self) -> list:
        """返回 [(host, [(feature_int, decision)])]。"""
        out = []
        for host, feats in self._data.items():
            out.append((host, [(int(k), v) for k, v in feats.items()]))
        return sorted(out)
