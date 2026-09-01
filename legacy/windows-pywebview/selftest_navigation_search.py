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

# ============================================================
# 4) 批次三补齐（全量复审 2026-09-01 自测覆盖缺口）
#    new_tab 路径 / 启动恢复链路 / 超长 URL / IP 直连 / 中文域名 / http 明文
# ============================================================


def new_tab_capture(user_input: str, engine: str = "baidu") -> str:
    """走真实 Api.new_tab 代码路径，返回实际加载的 URL（空串=被拒绝）。"""
    api = Api()
    api._engine = engine
    api._last_new_tab = 0.0
    api.window = None
    captured: list[str] = []
    api._load = lambda u: (captured.append(u), True)[1]
    api.new_tab(user_input)
    return captured[0] if captured else ""


def seed_url(tabs: list, current: int = 0) -> str:
    """走真实 Api.seed_session（P1-8 双层校验收口），返回恢复 URL。"""
    api = Api()
    api._load = lambda u: True
    return api.seed_session(tabs, current)


# --- new_tab（含 P2 修复回归：归一化传当前引擎 + 拒绝可见反馈）---
check("N1 new_tab 裸搜索词遵循当前引擎（固定 google）",
      new_tab_capture("rust uniffi", engine="google")
      == "https://www.google.com/search?q=rust%20uniffi")
check("N2 new_tab 完整网址直载",
      new_tab_capture("https://example.com/a") == "https://example.com/a")
check("N3 new_tab 不安全目标拒绝（javascript:）",
      new_tab_capture("javascript:alert(1)") == "")

_api = Api()
_api._engine = "baidu"
_loads: list[str] = []
_api._load = lambda u: _loads.append(u)
_api.new_tab("https://example.com/1")
_api.new_tab("https://example.com/2")
check("N4 new_tab 频控：500ms 内第二次调用被拒",
      _loads == ["https://example.com/1"])

# --- 超长 URL（security.py MAX_URL_LENGTH 静默拒的用户可见出口在 navigate）---
check("N5 超长中文查询（归一化后 >8192）拒绝导航",
      navigate_and_capture(START_URL, "测" * 9000) == "")

# --- IP 直连 / http 明文 / 中文域名 punycode ---
check("N6 IP 直连裸输入 → https 补全",
      navigate_and_capture(REMOTE, "192.168.1.1") == "https://192.168.1.1")
check("N7 http:// 明文 URL 原样保留",
      navigate_and_capture(REMOTE, "http://192.168.1.1/")
      == "http://192.168.1.1/")
check("N8 中文域名可导航（百分号编码宿主）",
      navigate_and_capture(REMOTE, "https://例子.测试/")
      == "https://%E4%BE%8B%E5%AD%90.%E6%B5%8B%E8%AF%95/")

# --- 启动/恢复 URL 链路（P1-8：恢复 URL 必须过双层校验）---
check("N9 恢复链路清洗：javascript: 标签被丢弃",
      seed_url([{"url": "javascript:alert(1)", "title": "x"},
                {"url": "https://example.com/", "title": "ok"}])
      == "https://example.com/")
check("N10 恢复链路清洗：全部非法 → 空串（不导航）",
      seed_url([{"url": "file:///C:/Windows/win.ini", "title": "x"}]) == "")

if failures:
    print("N FAILED: " + str(len(failures)))
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("OK: navigation/search selftest passed")
