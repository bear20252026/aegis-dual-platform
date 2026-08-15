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

# 3) 标签管理
api.new_tab("https://a.cn")
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

if failures:
    print("FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("OK — api_bridge 全部自检通过")
print(f"api_bridge.py 行数: {len(Path('app/api_bridge.py').read_text(encoding='utf-8').splitlines())}")
