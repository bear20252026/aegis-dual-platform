"""selftest_navigation_search.py —— 搜索/地址栏导航自检（独立 UTF-8 脚本）。

回归锁死 P0-1（搜索功能审计 2026-09-01）：

    `Api.navigate()` 曾经在入口做 `_check_trusted_source()` 来源校验，而
    地址栏是注入到**每一个页面**顶部的浏览器 Chrome UI——离开首页后
    `current_url()` 返回远程 host，用户主动发起的地址栏搜索/导航被
    100% 静默拒绝（实测 7 场景仅 2 个可用）。

本自检覆盖两类断言：
1. 功能：无论当前页面是本地壳页还是远程页面，地址栏搜索/导航都必须生效
   （搜索词 → 搜索引擎；网址 → https://；about:blank → 空白页）
2. 安全：来源校验下放后，导航**目标**的边界必须仍然紧固
   （javascript:/file:/data:/blob: 等一律拒绝）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _selftest_support import check, failures

from app.api_bridge import Api
from app.url_utils import START_URL

REMOTE = "https://www.baidu.com/"


class FakeWindow:
    """假 window：只提供 navigate 路径用到的 get_current_url/load_url。"""

    def __init__(self, url: str):
        self.url = url
        self.loaded: list[str] = []

    def get_current_url(self) -> str:
        return self.url

    def load_url(self, u: str) -> bool:
        self.loaded.append(u)
        return True


def navigate_and_capture(current_url: str, user_input: str, engine: str = "baidu") -> str:
    """走真实 Api.navigate 代码路径，返回实际加载的 URL（空串=被拒绝）。"""
    api = Api()
    api._engine = engine
    api.window = FakeWindow(current_url)
    api.history = None
    api._update_current = lambda *a, **k: None
    captured: list[str] = []
    api._load = lambda u: (captured.append(u), True)[1]
    api.navigate(user_input)
    return captured[0] if captured else ""


# ============================================================
# 1) 功能：远程页面上地址栏必须可用（P0-1 核心回归）
# ============================================================
# A/B 本地壳页（首页搜索框）——修复前后均可用，锁住不回退
check("A 首页搜索框中文词 → 百度搜索",
      navigate_and_capture(START_URL, "今天天气")
      == "https://www.baidu.com/s?wd=%E4%BB%8A%E5%A4%A9%E5%A4%A9%E6%B0%94")
check("B 首页输入网址 → https 补全",
      navigate_and_capture(START_URL, "example.com") == "https://example.com")

# C/D/F/G 远程页面（地址栏）——修复前全部静默失效
check("C 远程页地址栏搜索中文词",
      navigate_and_capture(REMOTE, "今天天气")
      == "https://www.baidu.com/s?wd=%E4%BB%8A%E5%A4%A9%E5%A4%A9%E6%B0%94")
check("D 远程页地址栏换网址",
      navigate_and_capture(REMOTE, "example.org") == "https://example.org")
check("F 远程页地址栏搜索遵循当前引擎（google）",
      navigate_and_capture("https://example.com/", "rust uniffi", engine="google")
      == "https://www.google.com/search?q=rust%20uniffi")
check("G 远程页地址栏 about:blank",
      navigate_and_capture("https://example.com/", "about:blank") == "about:blank")
check("H 远程页粘贴完整 https 网址",
      navigate_and_capture(REMOTE, "https://example.net/a") == "https://example.net/a")

# ============================================================
# 2) 安全：目标边界必须仍然紧固（来源校验下放后不得失守）
# ============================================================
# P0-1 补丁：非导航 scheme 的输入既不能当搜索词也不能拼 https://，
# 必须 fail-closed（file: 曾被拼成 https://file:///... —— urlparse 把
# `file:` 解析成合法 host 名放行）
for scheme_url, tag in (("javascript:alert(1)", "javascript"),
                        ("file:///C:/Windows/win.ini", "file"),
                        ("data:text/html,<b>x</b>", "data"),
                        ("vbscript:msgbox(1)", "vbscript"),
                        ("chrome://settings", "chrome")):
    check(f"非导航 scheme 拒绝导航: {tag}",
          navigate_and_capture(REMOTE, scheme_url) == "",
          detail=f"输入 {scheme_url!r} 不应产生导航")

# D-1：完整 URL 内的空格按浏览器惯例编码为 %20 后放行
check("URL 空格编码 %20 后放行",
      navigate_and_capture(REMOTE, "https://example.net/a b")
      == "https://example.net/a%20b")

# 空输入 → 回首页（START_URL 壳页白名单——P0-1 补丁）
check("空输入 → 首页 START_URL",
      navigate_and_capture(REMOTE, "") == START_URL)

# ============================================================
# 3) 契约：_check_trusted_source 仍守护写操作（不得被本修复牵连移除）
# ============================================================
check("_check_trusted_source 仍存在（写操作入口）",
      callable(getattr(Api, "_check_trusted_source", None)))

if failures:
    print("N FAILED: " + str(len(failures)))
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("OK: navigation/search selftest passed")
