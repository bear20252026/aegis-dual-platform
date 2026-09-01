"""WallpaperMixin（H-2 拆分自 api_bridge.py——方法体逐字迁移，零行为变更）。

M-1 后续：api_bridge 818 行超 500 行红线，按节拆分为 mixin 组合
（沿用 TabOpsMixin 先例 + 协议声明模式：TYPE_CHECKING 块声明宿主
成员，运行时由 Api 组合提供——无循环、无运行期开销）。
"""
from typing import Any, Callable

_DEFAULT_WALLPAPER = "aurora-twilight.jpg"



class WallpaperMixin:
    # 宿主 Api 成员声明（协议模式——运行时由组合后的 Api 提供）
    _data_dir: str
    _notify: Callable[[str], bool]
    config: Any
    # ================= 壁纸 =================
    def get_wallpaper(self) -> str:
        """返回当前新标签页壁纸文件名（配置持久化）。"""
        try:
            if self.config is not None:
                name = getattr(self.config, "ntp_wallpaper", "") or ""
                if name:
                    return name
        except Exception:
            pass
        return _DEFAULT_WALLPAPER

    def set_wallpaper(self, name: str) -> None:
        """切换壁纸并持久化（白名单校验）。"""
        try:
            from ..asset_scheme import WALLPAPERS
            if not name or name not in WALLPAPERS:
                # P2 修复（全量复审 2026-09-01）：静默拒绝 → 可见反馈
                self._notify("壁纸设置失败：名称不在内置壁纸列表")
                return
            if self.config is None:
                from ..config import AppConfig
                self.config = AppConfig()
            self.config.ntp_wallpaper = name
            if self._data_dir:
                self.config.save(self._data_dir)
        except Exception:
            # P2 修复：静默失败 → 可见反馈（配置失败不影响浏览的语义保留）
            try:
                self._notify("壁纸设置失败：配置写入异常")
            except Exception:
                pass  # 壁纸配置失败不影响浏览
