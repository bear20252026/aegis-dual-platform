"""profile.py —— 用户配置文件管理。

支持多个配置文件，每个配置拥有独立的书签/历史/密码/缓存，互不干扰。
"""

import json
import os

from .paths import ensure_dir, profile_dir, sanitize_profile_name


class ProfileManager:
    """管理一组命名的用户配置文件。"""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self._index_file = os.path.join(base_dir, "profiles.json")
        self._profiles = self._load_index()

    def _load_index(self) -> dict:
        """加载 {name: {"display": ..., "last_used": ts}}。"""
        if os.path.exists(self._index_file):
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_index(self):
        ensure_dir(self.base_dir)
        try:
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump(self._profiles, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def list_profiles(self):
        """返回 [(name, display)]。"""
        return [(n, p.get("display", n))
                for n, p in self._profiles.items()]

    def ensure(self, name: str, display: str | None = None) -> str:
        """确保配置文件存在，返回其数据目录路径。"""
        name = sanitize_profile_name(name)
        profile_dir(self.base_dir, name)
        if name not in self._profiles:
            self._profiles[name] = {
                "display": display or name,
                "created": 0,
            }
            self._save_index()
        return profile_dir(self.base_dir, name)

    def rename(self, old: str, new: str):
        old = sanitize_profile_name(old)
        new = sanitize_profile_name(new)
        if old in self._profiles and new not in self._profiles and old != new:
            meta = self._profiles.pop(old)
            self._profiles[new] = meta
            # 重命名目录
            old_dir = os.path.join(self.base_dir, "profiles", old)
            new_dir = os.path.join(self.base_dir, "profiles", new)
            if os.path.exists(old_dir):
                os.rename(old_dir, new_dir)
            self._save_index()

    def delete(self, name: str):
        name = sanitize_profile_name(name)
        if name == "default":
            return
        if name in self._profiles:
            del self._profiles[name]
            import shutil
            shutil.rmtree(os.path.join(self.base_dir, "profiles", name),
                          ignore_errors=True)
            self._save_index()
