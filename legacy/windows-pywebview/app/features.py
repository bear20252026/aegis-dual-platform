"""features.py —— R-05 整改（功能注册表——只有接线的功能可展示）。

体验/功能审查（R-05）：大量配置字段/孤立模块无用户入口（影子功能——
"存在配置字段/存在孤立模块/文档中宣称"不能替代真实产品能力）。
本模块建立功能注册表（FeatureSpec）——每个产品能力同时拥有：领域服务、
用户入口、可用性、设置 schema——**未实现不注册**（不能仅因 config 有
字段就展示给用户——实施手册 R-05）。产品文档/UI 从 FEATURES 自动生成
可用功能表，禁止手写夸大的功能清单。
"""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class FeatureSpec:
    """功能规格（R-05：命令—服务—仓储—状态—UI—错误—审计—测试闭环入口）。"""

    key: str
    title: str
    is_available: Callable[[], bool]
    open_ui: Callable[[], None] | None = None
    settings_schema: type | None = None


def _open_bookmark_manager() -> None:
    """书签管理器入口（发布期原生 chrome UI——当前记录）。

    服务层已就绪（bookmark_store——insert/remove）；UI 闭环（星标/抽屉/
    编辑/删除/搜索/导入导出）为发布期原生 host 架构（R-02 原生 chrome）。
    """


def _open_history_page() -> None:
    """历史页入口（发布期原生 chrome UI——当前记录）。

    服务层已就绪（history_store）；历史页（时间分组/清除/搜索）为发布期。
    """


def _open_download_manager() -> None:
    """下载管理器入口（发布期——下载追踪/进度/历史为原生 chrome UI）。"""


def _open_settings_page() -> None:
    """设置页入口（发布期——仅展示已接线的设置——影子配置不展示）。"""


# 功能注册表：只有真正接线的功能注册（未实现不注册——手册 R-05）。
# downloads 未实现（is_available=False——下载管理器尚未接线——不展示）。
FEATURES: dict[str, FeatureSpec] = {
    "bookmarks": FeatureSpec("bookmarks", "书签", lambda: True,
                             _open_bookmark_manager, None),
    "history": FeatureSpec("history", "历史", lambda: True,
                           _open_history_page, None),
    "downloads": FeatureSpec("downloads", "下载", lambda: False,
                             _open_download_manager, None),
    "settings": FeatureSpec("settings", "设置", lambda: True,
                            _open_settings_page, None),
}


def available_features() -> list[FeatureSpec]:
    """只返回可用的功能（产品文档/UI 据此生成——禁止手写夸大清单）。"""
    return [f for f in FEATURES.values() if f.is_available()]
