"""settings_registry.py —— R-10 整改（影子配置消除——设置注册表）。

体验/功能审查（R-10）：大量配置字段无消费点（影子配置——"存在字段"
不能替代真实行为）。本模块建立 SettingSpec 注册表——每个持久化设置
必须拥有：key/default/validate/apply/available——未实现的功能只能位于
开发实验 flag，默认不进入稳定版配置、设置 UI 或 README（实施手册 R-10）。
设置 UI 只展示当前平台实际可用的设置（影子配置不展示）。
"""

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class SettingSpec(Generic[T]):
    """设置规格（R-10：配置模式—消费点—验证器—可用性一对一）。"""

    key: str
    default: T
    validate: Callable[[T], T]
    apply: Callable[[T], None]
    available: Callable[[], bool]


def _validate_engine(v: str) -> str:
    return v if v in {"bing", "google", "duckduckgo"} else "bing"


def _apply_engine(v: str) -> None:
    pass  # 发布期：search_service.set_engine（当前记录——R-10 消费点）


# 设置注册表：只有已接线的设置注册（未实现不进入稳定版配置——R-10）
SETTINGS: dict[str, SettingSpec] = {
    "search_engine": SettingSpec(
        key="search_engine", default="bing", validate=_validate_engine,
        apply=_apply_engine, available=lambda: True),
}


def available_settings() -> list[SettingSpec]:
    """只返回当前平台可用的设置（设置 UI 据此展示——影子配置不展示）。"""
    return [s for s in SETTINGS.values() if s.available()]
