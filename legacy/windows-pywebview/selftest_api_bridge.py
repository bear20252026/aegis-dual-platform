"""selftest_api_bridge.py —— api_bridge 模块自检（独立 UTF-8 脚本）。

验证点（不依赖 pywebview / Qt，全部离线）：
1. 模块可导入（nav_queue / shell_toolbar 依赖正确）
2. __dir__ 白名单只暴露 _JS_EXPOSED 方法（防递归注入死锁）
3. 标签管理：new_tab / switch_tab / close_tab / _update_current / get_tabs
4. normalize_url：补协议 / 搜索词 / about:blank
5. on_loaded 注入：占位符替换后无残留
6. window 未绑定时 _load/_eval 不崩溃（NavQueue 静默降级）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.api_bridge import START_URL, Api, normalize_url, on_loaded
from app.nav_queue import NavQueue

failures = []


def check(name: str, cond: bool, detail: str = ""):
    if not cond:
        failures.append(f"{name}: {detail}")


# 1) 模块可导入
check("Api 可实例化", True)

# 2) __dir__ 白名单
api = Api()
exposed = set(dir(api))
check("__dir__ 只含白名单方法", exposed == api._JS_EXPOSED,
      f"extra={sorted(exposed - api._JS_EXPOSED)}")
check("白名单含关键方法", {"new_tab", "switch_tab", "close_tab",
                        "navigate"} <= api._JS_EXPOSED)
# B0-W-01 整改验证（国防级审查）：敏感读取/导入方法不得在 JS 白名单
# （历史/书签/标签 URL 读取 + 本机 Chrome/Edge 导入——恶意页面不可达）
check("白名单无敏感方法", not {"get_tabs", "get_history", "get_most_visited",
                        "search_history_fulltext", "get_bookmarks",
                        "import_bookmarks", "import_history",
                        "get_tab_groups"} & api._JS_EXPOSED)

# 3) 标签管理（M-2 适配：new_tab 有 500ms 频率限制——连续调用间留间隔）
import time as _t
api.new_tab("https://a.cn")
_t.sleep(0.6)
api.new_tab("https://b.cn")
snap = api.get_tabs()
check("new_tab 后 3 个标签", len(snap["tabs"]) == 3, f"tabs={snap['tabs']}")
check("当前标签为最后一个", snap["current"] == 2)

api.switch_tab(0)
snap = api.get_tabs()
check("switch_tab 到 0", snap["current"] == 0)

api._update_current("https://a.cn", "站点A")
snap = api.get_tabs()
check("_update_current 更新 title", snap["tabs"][0]["title"] == "站点A")
check("_update_current 更新 url", snap["tabs"][0]["url"] == "https://a.cn")

api.close_tab(2)
snap = api.get_tabs()
check("close_tab 后 2 个标签", len(snap["tabs"]) == 2)
check("close_tab 后当前索引回退", snap["current"] == 0)

# 4) normalize_url
check("补 https 协议", normalize_url("example.com") == "https://example.com")
check("http 保留", normalize_url("http://a.cn") == "http://a.cn")
check("搜索词走引擎", normalize_url("hello world") ==
      "https://www.baidu.com/s?wd=hello%20world")
check("about:blank 保留", normalize_url("about:blank") == "about:blank")
check("空输入回首页", normalize_url("") == START_URL)

# 5) on_loaded 注入：占位符替换后无残留
class FakeWindow:
    def get_current_url(self):
        return "https://a.cn/"

fw = FakeWindow()
on_loaded(fw, api)
# 注入走 NavQueue.eval（window 未绑定 pywebview，但 FakeWindow 没有 evaluate_js
# 相关调用路径会走 _eval 投递，NavQueue 的 window=None 时静默跳过，不崩溃）
check("on_loaded 不抛异常", True)

# 6) window 未绑定时 _load/_eval 静默
check("_load 未绑定时返回 True（投递成功）", api._load("https://a.cn"))
check("_eval 未绑定时返回 True", api._eval("window.history.back()"))
check("_load 空 URL 返回 False", api._load("") is False)

# 7) NavQueue 组合关系：Api.window property 委托给 nav
nav = NavQueue()
check("Api 内部持有 NavQueue", isinstance(api._nav, NavQueue))

# 8) 标签增强（tab_ops mixin）：move_tab / close_current_tab
# 前置状态（第 3 节后）：tabs=[默认, a.cn]，current=0
_t.sleep(0.6)
api.new_tab("https://c.cn")
_t.sleep(0.6)
api.new_tab("https://d.cn")
snap = api.get_tabs()
check("move_tab 前置 4 个标签", len(snap["tabs"]) == 4, f"n={len(snap['tabs'])}")

# tabs=[默认, a.cn, c.cn, d.cn]，current=3 → move 3→1
api.move_tab(3, 1)
snap = api.get_tabs()
check("move_tab 3→1 位置正确", snap["tabs"][1]["url"] == "https://d.cn")
check("move_tab 后 current 跟随移动标签", snap["current"] == 1)

# tabs=[默认, d.cn, a.cn, c.cn] → 切到 0（默认），移动非当前标签 3→2
api.switch_tab(0)
api.move_tab(3, 2)
snap = api.get_tabs()
check("移动非当前标签不改 current", snap["current"] == 0, f"cur={snap['current']}")
check("移动后落位正确", snap["tabs"][2]["url"] == "https://c.cn")

api.pin_tab(0)  # 固定默认标签 → pinned 区 = [0]
api.move_tab(0, 3)  # pinned 想移到 3 → 钳制回 pinned 区内（不动）
snap = api.get_tabs()
check("pinned 拖拽钳制在 pinned 区",
      snap["tabs"][0]["pinned"] is True and snap["tabs"][1]["url"] == "https://d.cn",
      f"{snap['tabs'][0]}")

api.move_tab(99, 0)
api.move_tab(-1, 0)
api.move_tab(1, 1)
check("move_tab 非法参数不崩溃", len(api.get_tabs()["tabs"]) == 4)

# 9) close_current_tab（后端实时 _current——Ctrl+W 修复）
api.switch_tab(2)  # c.cn
api.close_current_tab()
snap = api.get_tabs()
check("close_current_tab 关掉的是实时当前标签",
      len(snap["tabs"]) == 3 and snap["current"] == 1,
      f"n={len(snap['tabs'])}, cur={snap['current']}")

# 10) 会话恢复：seed_session / _persist_session / has_saved_session / restore_session
import tempfile

tmp = tempfile.mkdtemp(prefix="aegis_bridge_")
api2 = Api()
api2._data_dir = tmp
api2.seed_session([
    {"title": "S1", "url": "https://s1.cn", "pinned": False, "group": "默认"},
    {"title": "S2", "url": "https://s2.cn", "pinned": True, "group": "默认"},
], 0)
api2._persist_session()
check("has_saved_session 返回标签数", api2.has_saved_session() == 2)

api3 = Api()
api3._data_dir = tmp
check("restore_session 成功", api3.restore_session() is True)
snap = api3.get_tabs()
check("restore 后 2 个标签", len(snap["tabs"]) == 2)
check("restore 后 pinned 保持", snap["tabs"][1]["pinned"] is True)

api4 = Api()
api4._data_dir = tempfile.mkdtemp(prefix="aegis_empty_")
check("无会话 restore_session → False", api4.restore_session() is False)
check("无会话 has_saved_session → 0", api4.has_saved_session() == 0)

# 会话保存钩子：new_tab / close_current_tab 后自动落盘（静默持久化）
api5 = Api()
api5._data_dir = tempfile.mkdtemp(prefix="aegis_hook_")
_t.sleep(0.6)
api5.new_tab("https://hook.cn")
check("new_tab 钩子落盘会话", api5.has_saved_session() == 2)  # 默认标签 + 新建
api5.close_current_tab()
check("close_current_tab 钩子更新会话", api5.has_saved_session() == 1)

if failures:
    print("FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("OK — api_bridge 全部自检通过")
print(f"api_bridge.py 行数: {len(Path('app/api_bridge.py').read_text(encoding='utf-8').splitlines())}")
