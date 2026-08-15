"""selftest_tab_state.py —— R-04 整改单元测试（TabState/TabStore 会话状态）。

覆盖：创建/激活/状态更新（不可变）/切换不重载/快照独立/关闭仅销毁。
"""

import sys
from uuid import UUID

sys.path.insert(0, ".")
from app.tab_state import LoadPhase, TabStore


def check(name: str, cond: bool) -> bool:
    print(("✅ " if cond else "❌ ") + name)
    return cond


ok = True
s = TabStore()

# 1) 创建标签（独立 id/URL）+ 自动激活
t1 = s.create("https://a.gov.cn/1")
ok &= check("创建标签（唯一 id/URL）", isinstance(t1.id, UUID) and t1.url == "https://a.gov.cn/1")
ok &= check("新建即激活", s.active == t1.id)

# 2) 第二标签——独立会话状态
t2 = s.create("https://a.gov.cn/2")
ok &= check("第二标签独立激活", s.active == t2.id and t1.url != t2.url)

# 3) 状态更新（不可变 replace——R-04 完整会话状态）
u = s.update(t1.id, phase=LoadPhase.COMPLETE, title="A页", can_go_back=True, progress=100)
ok &= check("状态更新（加载阶段/标题/导航栈）",
            u.phase == LoadPhase.COMPLETE and u.title == "A页" and u.can_go_back and u.progress == 100)
ok &= check("更新返回新快照（不可变）", s.get(t1.id) == u and s.get(t1.id) is not None)

# 4) 切换激活不重载（R-04 核心：切换仅改 active——状态不变）
s.activate(t1.id)
ok &= check("切换激活（不重载——状态保留）", s.active == t1.id and s.get(t1.id) == u)

# 5) 快照独立（两标签状态互不影响）
ok &= check("快照独立（2 标签互不影响）", len(s.snapshot()) == 2)

# 6) 关闭仅销毁对应状态（R-04：关闭仅销毁对应 surface）
s.close(t2.id)
ok &= check("关闭仅销毁对应状态", len(s.snapshot()) == 1 and s.get(t2.id) is None)

print("ALL OK — R-04 会话状态模型验证通过" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
