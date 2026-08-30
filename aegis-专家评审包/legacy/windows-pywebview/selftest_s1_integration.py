"""selftest_s1_integration.py —— S1 拆分后的集成自检（等效 smoke-test 的代码层）。

背景：真实 --smoke-test 需要 pywebview + WebView2 Runtime（本机未安装，
属于运行环境依赖，非代码问题）。本脚本用假窗口对象模拟 pywebview 的
窗口行为，验证拆分后三个模块（shell_toolbar / nav_queue / api_bridge）
的组合链路与拆分前行为一致：

  1. Api 创建 → 绑定假窗口 → new_tab/navigate 投递到 NavQueue
  2. 假窗口的 loaded 事件 → on_loaded → build_toolbar_js 注入
  3. 标签增删切换 / 导航历史写入 / 状态刷新全链路
"""
from _selftest_support import check, failures  # M-6 共享支撑


import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.api_bridge import START_URL, Api, on_loaded
from app.shell_toolbar import build_toolbar_js


class FakeWindow:
    """模拟 pywebview Window 的最小接口：load_url/evaluate_js/get_current_url。"""

    def __init__(self):
        self.loaded_urls = []
        self.eval_scripts = []
        self._url = START_URL

    def load_url(self, url):
        self.loaded_urls.append(url)
        self._url = url

    def evaluate_js(self, script):
        self.eval_scripts.append(script)

    def get_current_url(self):
        return self._url


# ---------- 场景：完整浏览会话 ----------
win = FakeWindow()
api = Api()
api.window = win  # 绑定（NavQueue.window 同步）

# 1) 初始状态：1 个标签（首页）
snap = api.get_tabs()
check("初始 1 个标签", len(snap["tabs"]) == 1)

# 2) 标签操作全链路（受信壳页状态）。
#    存量修复（原脚本 FAIL）：P1-1 来源校验落地后，远程页面（当前 URL
#    host 非空）的 new_tab/close_tab 一律被拒——这是安全语义而非回归；
#    原场景在 navigate 之后再建标签，与校验冲突。改为先建标签后导航。
# M-2 适配：new_tab 有 500ms 频率限制——连续调用间留间隔
api.new_tab("https://b.cn")
time.sleep(0.6)
api.new_tab("https://c.cn")
time.sleep(0.5)
snap = api.get_tabs()
check("new_tab 后 3 个标签", len(snap["tabs"]) == 3)
check("新标签 URL 正确", snap["tabs"][2]["url"] == "https://c.cn")
check("当前为最后标签", snap["current"] == 2)

api.switch_tab(0)
time.sleep(0.4)
check("switch_tab 回第 0 标签", api.get_tabs()["current"] == 0)
check("switch_tab 触发 load_url", win.loaded_urls[-1] == START_URL)

api.close_tab(2)
time.sleep(0.4)
check("close_tab 后 2 个标签", len(api.get_tabs()["tabs"]) == 2)

# 3) navigate 投递导航并写历史（历史未绑定 → 降级不崩溃）
api.navigate("example.com")
time.sleep(0.7)  # 等导航线程消费
check("navigate 已投递 load_url", "https://example.com" in win.loaded_urls,
      f"loaded_urls={win.loaded_urls}")
check("地址栏输入被记录到当前标签", api.get_tabs()["tabs"][0]["url"] == "https://example.com")

# 4) on_loaded（模拟页面加载完成）→ 注入工具栏
win._url = "https://c.cn"
on_loaded(win, api)
time.sleep(0.5)
check("on_loaded 更新当前标签 URL", api.get_tabs()["tabs"][0]["url"] == "https://c.cn")
check("on_loaded 触发注入", len(win.eval_scripts) >= 1, "无注入脚本")
if win.eval_scripts:
    js = win.eval_scripts[-1]
    check("注入脚本无占位符残留", "__AEGIS_URL__" not in js and "__TABS_JSON__" not in js)
    check("注入脚本含当前 URL", "https://c.cn" in js)

# 5) build_toolbar_js 与 on_loaded 产出一致性（引用同一函数）
direct = build_toolbar_js("https://c.cn", api.get_tabs())
check("build_toolbar_js 可独立调用", "https://c.cn" in direct)

# 6) NavQueue 健康检查
check("NavQueue.healthy", api._nav_healthy())

# 7) 边界：空输入 / 越界标签不崩溃
api.switch_tab(99)
api.close_tab(99)
check("越界标签操作不崩溃", True)

# 汇总
if failures:
    print("FAIL — S1 集成自检")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("OK — S1 集成自检全部通过（导航/标签/注入/健康检查/边界）")
print(f"  加载过 URL: {win.loaded_urls}")
print(f"  注入脚本数: {len(win.eval_scripts)}")
