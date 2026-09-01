"""GeoMixin（H-2 拆分自 api_bridge.py——方法体逐字迁移，零行为变更）。

M-1 后续：api_bridge 818 行超 500 行红线，按节拆分为 mixin 组合
（沿用 TabOpsMixin 先例 + 协议声明模式：TYPE_CHECKING 块声明宿主
成员，运行时由 Api 组合提供——无循环、无运行期开销）。
"""
from typing import Callable

from ..url_utils import SEARCH_ENGINES, START_URL, normalize_url  # noqa: F401
from ..validators import host_of, to_int as _to_int, to_nonneg_int as _to_nonneg_int, to_str as _to_str  # noqa: F401



class GeoMixin:
    # 宿主 Api 成员声明（协议模式——运行时由组合后的 Api 提供）
    _load: Callable[[str], bool]
    _notify: Callable[[str], bool]
    _deny_remote: Callable[[str], bool]

    # ================= 离线几何画板（GeoGebra Math Apps Bundle） =================
    def open_geogebra(self) -> bool:
        """打开离线几何画板（安装包内置资源——file:// 内部受信加载）。

        资源路径为编译期常量（PyInstaller _MEIPASS/_internal 或源码树
        geogebra/），与 START_URL 同级的内部壳页语义——不经 safe_url
        （内部资源白名单：路径由代码固定，非用户输入，无注入面）。
        资源未随包（常规打包/开发树未拉取 bundle）→ False（静默降级）。
        """
        if self._deny_remote("open_geogebra"):
            return False
        import sys
        from pathlib import Path

        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", "")
            if not meipass:
                return False  # 打包环境缺资源元数据 → 未随包（fail-closed）
            base = Path(meipass)
        else:
            base = Path(__file__).resolve().parents[2]
        entry = base / "geogebra" / "GeoGebra" / "HTML5" / "5.0" / "GeoGebra.html"
        if not entry.is_file():
            try:
                from crash_reporter import log_event
                log_event("[bridge] 几何画板资源缺失（构建未随包）")
            except Exception:
                pass
            # P2 修复（全量复审 2026-09-01）：静默降级 → 可见反馈
            # （start.html openGeo onFail 置灰是页面侧；此处覆盖直接调用）
            try:
                self._notify("几何画板未随当前安装包提供")
            except Exception:
                pass
            return False
        self._load(entry.as_uri())
        return True

