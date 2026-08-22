"""tab_state.py —— R-04 整改（真实多标签会话状态模型——迁移步骤 1）。

体验/功能审查（R-04）：当前标签仅存 URL 列表（切换重载——非真实会话）。
本模块引入完整会话状态模型（TabState/TabStore）——每个标签独立状态
（URL/标题/favicon/加载阶段/进度/导航栈/固定/分组）——**不改变 UI**
（实施手册迁移步骤 1：先引入状态模型与单元测试，再接入 UI）。
后续（发布期）：每标签独立 BrowserSurface（原生 host——WinUI/WPF）——
本模型是 surface 独立会话的状态基础（pywebview 单窗口无法多 surface——
手册 R-04 承认——原生 host 为发布期架构）。
"""

from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID, uuid4


class LoadPhase(StrEnum):
    """标签加载阶段（R-04：独立加载状态）。"""

    IDLE = "idle"
    LOADING = "loading"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class TabState:
    """单个标签的完整会话状态（R-04——不可变快照）。"""

    id: UUID
    url: str
    title: str = "新标签页"
    favicon_url: str | None = None
    phase: LoadPhase = LoadPhase.IDLE
    progress: int = 0
    can_go_back: bool = False
    can_go_forward: bool = False
    pinned: bool = False
    group_id: str = "default"


class TabStore:
    """标签会话状态存储（R-04：完整会话状态——独立导航/加载状态）。"""

    def __init__(self) -> None:
        self._tabs: dict[UUID, TabState] = {}
        self._active: UUID | None = None

    @property
    def active(self) -> UUID | None:
        """当前激活标签 id；无标签为 None。"""
        return self._active

    def create(self, url: str) -> TabState:
        """新建标签并激活（唯一 id——独立会话）。"""
        tab = TabState(id=uuid4(), url=url)
        self._tabs[tab.id] = tab
        self._active = tab.id
        return tab

    def update(self, tab_id: UUID, **changes) -> TabState:
        """更新标签状态（不可变 replace——返回新快照）。"""
        current = self._tabs[tab_id]
        changed = replace(current, **changes)
        self._tabs[tab_id] = changed
        return changed

    def activate(self, tab_id: UUID) -> None:
        """切换激活标签（不改变状态——R-04 切换不重载）。"""
        if tab_id in self._tabs:
            self._active = tab_id

    def close(self, tab_id: UUID) -> None:
        """关闭标签——仅移除对应状态（R-04：关闭仅销毁对应 surface）。"""
        self._tabs.pop(tab_id, None)
        if self._active == tab_id:
            self._active = next(iter(self._tabs), None)

    def snapshot(self) -> tuple[TabState, ...]:
        """只读快照（UI 订阅——R-04 迁移步骤 3）。"""
        return tuple(self._tabs.values())

    def get(self, tab_id: UUID) -> TabState | None:
        return self._tabs.get(tab_id)
