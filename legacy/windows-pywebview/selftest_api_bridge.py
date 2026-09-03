"""selftest_api_bridge.py —— api_bridge 模块自检（独立 UTF-8 脚本）。

验证点（不依赖 pywebview / Qt，全部离线）：
1. 模块可导入（nav_queue / shell_toolbar 依赖正确）
2. __dir__ 白名单只暴露 _JS_EXPOSED 方法（防递归注入死锁）
3. 标签管理：new_tab / switch_tab / close_tab / _update_current / get_tabs
4. normalize_url：补协议 / 搜索词 / about:blank
5. on_loaded 注入：占位符替换后无残留
6. window 未绑定时 _load/_eval 不崩溃（NavQueue 静默降级）
"""
from _selftest_support import check, failures  # M-6 共享支撑


import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.api_bridge import START_URL, Api, normalize_url, on_loaded
from app.nav_queue import NavQueue


# 1) 模块可导入
check("Api 可实例化", True)

# 2) __dir__ 白名单
api = Api()
exposed = set(dir(api))
check("__dir__ 只含白名单方法", exposed == api._JS_EXPOSED,
      f"extra={sorted(exposed - api._JS_EXPOSED)}")
check("白名单含关键方法", {"new_tab", "switch_tab", "close_tab",
                        "navigate"} <= api._JS_EXPOSED)
# B0-W-01 整改验证（国防级审查）：敏感读取方法不得在 JS 白名单
# （历史/标签 URL 读取——恶意页面不可达）。
# B0-W-01 复审（PR #7）：get_bookmarks / 导入向导（scan_import_sources /
# import_bookmarks / import_history）以「白名单 + 方法内受信来源校验」
# 回归（start.html 宫格/向导恢复）——历史读取类仅受信壳页可达。
check("白名单无敏感方法", not {"get_tabs", "get_history", "get_most_visited",
                        "search_history_fulltext",
                        "get_tab_groups"} & api._JS_EXPOSED)
check("get_bookmarks 受信回归白名单", "get_bookmarks" in api._JS_EXPOSED)
check("导入向导回归白名单",
      {"scan_import_sources", "import_bookmarks", "import_history"}
      <= api._JS_EXPOSED)

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


class ShellWindow:
    """模拟本地壳页（P2 修复后 _check_trusted_source fail-closed：
    window 未绑定 / 拿不到 URL 一律不受信——恢复会话测试须绑定壳页窗口）。"""

    def get_current_url(self):
        return START_URL  # file:// → host 为空 → 受信


api2 = Api()
api2.window = ShellWindow()
api2._data_dir = tmp
api2.seed_session([
    {"title": "S1", "url": "https://s1.cn", "pinned": False, "group": "默认"},
    {"title": "S2", "url": "https://s2.cn", "pinned": True, "group": "默认"},
], 0)
api2._persist_session()
check("has_saved_session 返回标签数", api2.has_saved_session() == 2)

api3 = Api()
api3.window = ShellWindow()
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

# 11) get_bookmarks 受信来源校验（B0-W-01 复审回归）
# P2 修复后 _check_trusted_source fail-closed：受信需绑定壳页窗口
# （file:// → host 空）；window 未绑定/拿不到 URL 一律不受信
api.window = ShellWindow()
check("受信 get_bookmarks 返回列表", api.get_bookmarks() == [])

class _RemoteWin:
    def get_current_url(self):
        return "https://evil.example/page"

api6 = Api()
api6.window = _RemoteWin()  # 远程页来源
check("远程页 get_bookmarks 返回空", api6.get_bookmarks() == [])

# 12) 导入向导：scan_import_sources / import_bookmarks / import_history
#     （monkeypatch browser_import._SOURCES → 临时目录夹具，不触真实本机）
import json as _json
import os as _os
import sqlite3 as _sq

import app.browser_import as _bi

_fx = tempfile.mkdtemp(prefix="aegis_imp_")
_chrome = _os.path.join(_fx, "chrome_ud")
_edge = _os.path.join(_fx, "edge_ud")
_os.makedirs(_os.path.join(_chrome, "Default"))
_os.makedirs(_os.path.join(_edge, "Default"))
_bm = {"roots": {"bookmark_bar": {"type": "folder", "children": [
        {"type": "url", "name": "站点甲", "url": "https://jia.cn"},
        {"type": "url", "name": "站点乙", "url": "https://yi.cn/x?a=1"},
        {"type": "url", "name": "坏协议", "url": "javascript:x"},
    ]}, "other": None, "synced": None}}
with open(_os.path.join(_chrome, "Default", "Bookmarks"), "w", encoding="utf-8") as f:
    _json.dump(_bm, f, ensure_ascii=False)
_conn = _sq.connect(_os.path.join(_edge, "Default", "History"))
_conn.execute("CREATE TABLE urls(url TEXT, title TEXT, last_visit_time INTEGER)")
_conn.execute("INSERT INTO urls VALUES('https://his.cn','历史页', 100)")
_conn.execute("INSERT INTO urls VALUES('javascript:x','坏', 200)")
_conn.commit()
_conn.close()
_bi._SOURCES = (("chrome", _chrome), ("edge", _edge))

api7 = Api()
api7.window = ShellWindow()
api7._data_dir = tempfile.mkdtemp(prefix="aegis_impdata_")
from app.bookmark_store import BookmarkStore
from app.history_store import HistoryStore
api7.bookmarks = BookmarkStore(api7._data_dir)
api7.history = HistoryStore(api7._data_dir)

scan = api7.scan_import_sources()
check("scan 探测到两个来源", [s["browser"] for s in scan] == ["chrome", "edge"],
      f"{scan}")
check("scan 内容标志正确", scan[0]["bookmarks"] is True and scan[0]["history"] is False
      and scan[1]["history"] is True and scan[1]["bookmarks"] is False)

rb = api7.import_bookmarks("chrome")
check("import_bookmarks 仅 chrome（2 条，坏协议被滤）",
      rb["imported"] == 2 and rb["total"] == 2 and
      rb["results"][0]["browser"] == "chrome", f"{rb}")
check("书签已入库", api7.bookmarks.contains("https://jia.cn"))
rb2 = api7.import_bookmarks("chrome")
check("import_bookmarks 去重（二导 0 新增）", rb2["imported"] == 0)

rh = api7.import_history(10, "edge")
check("import_history 仅 edge（坏协议被滤）",
      rh["imported"] == 1 and rh["results"][0]["browser"] == "edge", f"{rh}")

check("非法来源参数回退全部", api7.import_bookmarks("firefox")["total"] == 2)

# 远程页不可达（W-03/B0-W-01 复审口径）
api8 = Api()
api8.window = _RemoteWin()
check("远程页 scan 返回空", api8.scan_import_sources() == [])
check("远程页 import_bookmarks 拒绝",
      api8.import_bookmarks() == {"imported": 0, "total": 0, "results": []})

# 13) 预置书签种子（「几何画板」外挂入口——空库注入、幂等）
api9 = Api()
api9.window = ShellWindow()
api9._data_dir = tempfile.mkdtemp(prefix="aegis_seed_")
api9.bookmarks = BookmarkStore(api9._data_dir)
check("空库注入种子 1 条", api9.bookmarks.seed_defaults() == 1)
check("种子为几何画板(GeoGebra)",
      api9.bookmarks.contains("https://www.geogebra.org/geometry"))
check("非空库不再注入（幂等）", api9.bookmarks.seed_defaults() == 0)
check("种子随 get_bookmarks 可读（受信）",
      len(api9.get_bookmarks()) == 1)

# 14) 离线几何画板桥：open_geogebra（源码树已解压 bundle → True；
#     monkeypatch frozen 基路径模拟未随包 → False）
check("open_geogebra 源码树加载成功", api.open_geogebra() is True)
import sys as _sys

_real_frozen = getattr(_sys, "frozen", None)
_sys.frozen = True  # 模拟打包环境且无 _MEIPASS 属性 → 资源缺失
try:
    api10 = Api()
    check("未随包 open_geogebra → False", api10.open_geogebra() is False)
finally:
    if _real_frozen is None:
        del _sys.frozen
    else:
        _sys.frozen = _real_frozen

# 14) P0-4 回归（全面审计 2026-09-04）：current_url 移出白名单 +
#     js_error 受信来源门禁（远程页不可探针/伪造上报）
check("current_url 已移出 _JS_EXPOSED", "current_url" not in api._JS_EXPOSED)
check("__dir__ 不再暴露 current_url", "current_url" not in dir(api))


class _LogCapture:
    """捕获 crash_reporter.log_event 调用（js_error 在调用点动态 import）。"""

    def __init__(self):
        self.lines: list = []
        self._orig = None

    def __enter__(self):
        import crash_reporter
        self._orig = crash_reporter.log_event
        crash_reporter.log_event = lambda msg, *a, **k: self.lines.append(str(msg))
        return self

    def __exit__(self, *exc):
        import crash_reporter
        crash_reporter.log_event = self._orig
        return False


# 受信壳页（start.html / 工具栏壳层——host 为空）上报照常记录
api_trusted = Api()
api_trusted.window = ShellWindow()
with _LogCapture() as cap:
    api_trusted.js_error("TypeError: x is undefined", "", 1, 1, "stack")
check("壳页 js_error 照常记录", len(cap.lines) == 1, f"{cap.lines}")

# 远程页面：source 为空（旧 A2 绕过口）也必须丢弃
api_remote = Api()
api_remote.window = _RemoteWin()
with _LogCapture() as cap:
    api_remote.js_error("probe", "", 0, 0, "")
    api_remote.js_error("spoof", "https://evil.example/x.js", 1, 1, "")
check("远程页 js_error 一律丢弃（含空 source 绕过）", cap.lines == [],
      f"{cap.lines}")

if failures:
    print("FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("OK — api_bridge 全部自检通过")
print(f"api_bridge.py 行数: {len(Path('app/api_bridge.py').read_text(encoding='utf-8').splitlines())}")
