"""SearchEngineMixin（H-2 拆分自 api_bridge.py——方法体逐字迁移，零行为变更）。

M-1 后续：api_bridge 818 行超 500 行红线，按节拆分为 mixin 组合
（沿用 TabOpsMixin 先例 + 协议声明模式：TYPE_CHECKING 块声明宿主
成员，运行时由 Api 组合提供——无循环、无运行期开销）。
"""
from typing import Any, Callable

from ..url_utils import SEARCH_ENGINES, START_URL, normalize_url  # noqa: F401
from ..validators import host_of, to_int as _to_int, to_nonneg_int as _to_nonneg_int, to_str as _to_str  # noqa: F401



class SearchEngineMixin:
    # 宿主 Api 成员声明（协议模式——运行时由组合后的 Api 提供）
    _engine: str
    config: Any
    _data_dir: str
    _check_trusted_source: Callable[[], bool]
    # ================= 搜索引擎 =================
    def get_search_engine(self) -> dict:
        """返回 {engine, engines:[{key,name}]}。"""
        return {
            "engine": self._engine,
            "engines": [{"key": k, "name": v[0]} for k, v in SEARCH_ENGINES.items()],
        }

    def set_search_engine(self, key: str) -> None:
        """切换搜索引擎并持久化（白名单校验）。"""
        # M-2 修复（防御性安全审查）：敏感写操作来源校验——远程页面
        # 调用拒绝（防搜索引擎篡改）
        if not self._check_trusted_source():
            try:
                from crash_reporter import log_event
                log_event("[bridge] 拒绝远程页面 set_search_engine（来源不受信）")
            except Exception:
                pass
            return
        try:
            if key not in SEARCH_ENGINES:
                return
            self._engine = key
            if self.config is None:
                from ..config import AppConfig
                self.config = AppConfig()
            self.config.engine = key
            if self._data_dir:
                self.config.save(self._data_dir)
        except Exception:
            pass  # 配置失败不影响本次切换

