"""selftest_native_core.py —— 原生内核解析与新窗口门禁自检（独立 UTF-8 脚本）。

回归锁死 P0-1/P0-2（全面审计 2026-09-04）：

    P0-1：shell_adapter.core() 旧实现走 window.gui.webview.CoreWebView2——
    pywebview 6.x 中 window.gui 是平台**模块**（无 webview 属性），每窗口
    控件在 window.native（BrowserView）上 → core() 恒 None，整层原生加固
    （拦截/注入/收紧/ESM/崩溃监听）静默 no-op。

    P0-2：pywebview 自带 NewWindowRequested 处理器对新窗口 URI 零校验，
    window.open('file:///...') 等可绕过 safe_url 门禁。

本自检覆盖三类断言（全部离线、无 GUI）：
1. 解析：resolve_core 在 pywebview 6.2.1 真实布局（gui=模块 + native=BrowserView）
   下必须取到 CoreWebView2；旧布局兜底；各类缺失返回 None
2. 门禁：gate_window_open 类级替换后，安全 URI 窗口内放行、
   file:/javascript:/校验异常 一律拒绝（fail-closed）
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _selftest_support import check, failures

from app.shell_adapter import resolve_core


class _FakeCore:
    """哨兵 CoreWebView2——验证解析链确实到达该对象。"""


class _FakeWebViewCtrl:
    def __init__(self):
        self.CoreWebView2 = _FakeCore()


class _FakeBrowserView:
    """模拟 pywebview 6.x BrowserView：self.webview = 控件实例。"""

    def __init__(self):
        self.webview = _FakeWebViewCtrl()


def _make_window_62_layout() -> types.SimpleNamespace:
    """pywebview 6.2.1 真实布局：window.gui=平台模块，window.native=BrowserView。"""
    fake_platform_mod = types.ModuleType("webview.platforms.winforms")
    assert not hasattr(fake_platform_mod, "webview")  # 模块上没有 webview 属性
    return types.SimpleNamespace(gui=fake_platform_mod, native=_FakeBrowserView())


# ============================================================
# 1) 解析：真实布局 / 旧布局兜底 / 缺失返回 None
# ============================================================
w = _make_window_62_layout()
check("R1 pywebview 6.x 布局（gui=模块+native）解析到 CoreWebView2",
      isinstance(resolve_core(w), _FakeCore),
      detail="旧实现（gui.webview）在该布局恒为 None——P0-1 回归锁")

check("R2 旧布局兜底（gui.webview.CoreWebView2）仍可解析", isinstance(
    resolve_core(types.SimpleNamespace(
        gui=types.SimpleNamespace(webview=_FakeWebViewCtrl()))), _FakeCore))

check("R3 窗口为 None → None", resolve_core(None) is None)
check("R4 native/gui 均缺失 → None",
      resolve_core(types.SimpleNamespace()) is None)
check("R5 控件无 CoreWebView2（初始化中）→ None",
      resolve_core(types.SimpleNamespace(native=types.SimpleNamespace(webview=object())))
      is None)


# ============================================================
# 3) 门禁：类级替换 pywebview NewWindowRequested 处理器（hermetic）
# ============================================================


class _FakeArgs:
    def __init__(self, uri: str):
        self._uri = uri
        self.handled = False

    def set_Handled(self, v: bool) -> None:
        self.handled = v

    def get_Uri(self) -> str:
        if self._uri == "__raise__":
            raise RuntimeError("simulated get_Uri failure")
        return self._uri


class _FakeEdgeChrome:
    """假 EdgeChrome：记录 load_url 调用（模拟 pywebview 原语义）。"""

    def __init__(self):
        self.loaded: list = []

    def load_url(self, url: str) -> None:
        self.loaded.append(url)

    @staticmethod
    def on_new_window_request(self, sender, args):  # 模拟 pywebview 原实现
        args.set_Handled(True)
        self.load_url(str(args.get_Uri()))


# 注入完整假包链（gate_window_open 在函数内 import webview.platforms.
# edgechromium；只预置叶子模块会破坏导入链——须三层齐备才 hermetic）。
# 本进程未导入真实 webview → 注入/还原干净；CI（无 pythonnet）同样可跑。
_saved_modules: dict = {}
_fake_settings = {"OPEN_EXTERNAL_LINKS_IN_BROWSER": False}


def _inject_fake_webview_chain() -> None:
    fake_webview = types.ModuleType("webview")
    fake_webview.__path__ = []  # 标记为 package
    fake_webview.settings = _fake_settings  # type: ignore[attr-defined]
    fake_platforms = types.ModuleType("webview.platforms")
    fake_platforms.__path__ = []
    fake_ec = types.ModuleType("webview.platforms.edgechromium")
    fake_ec.EdgeChrome = _FakeEdgeChrome
    for name, mod in (("webview", fake_webview),
                      ("webview.platforms", fake_platforms),
                      ("webview.platforms.edgechromium", fake_ec)):
        _saved_modules[name] = sys.modules.get(name)
        sys.modules[name] = mod


def _restore_webview_modules() -> None:
    for name, mod in _saved_modules.items():
        if mod is not None:
            sys.modules[name] = mod
        else:
            sys.modules.pop(name, None)


_inject_fake_webview_chain()
try:
    from app.native_interception import gate_window_open

    check("G1 类级门禁安装成功（替换 on_new_window_request）",
          gate_window_open() is True
          and _FakeEdgeChrome.on_new_window_request.__name__
          == "_gated_on_new_window_request")

    inst = _FakeEdgeChrome()

    inst.on_new_window_request(None, _FakeArgs("https://example.com/"))
    check("G2 安全 https URI → 当前窗口内放行",
          inst.loaded == ["https://example.com/"])

    inst.loaded.clear()
    for uri, tag in (("file:///C:/Windows/win.ini", "file"),
                     ("javascript:alert(1)", "javascript"),
                     ("__raise__", "get_Uri异常")):
        inst.on_new_window_request(None, _FakeArgs(uri))
        check(f"G3 新窗口不安全 URI 拒绝（fail-closed）: {tag}",
              inst.loaded == [],
              detail=f"{uri!r} 不应被 load_url")

    inst.on_new_window_request(None, _FakeArgs("about:blank"))
    check("G4 about:blank 放行（窗口内打开）",
          inst.loaded == ["about:blank"])
finally:
    _restore_webview_modules()

# ============================================================
# 4) 单源契约：坏解析（window.gui.webview）只允许存在于 shell_adapter 兜底
# ============================================================
repo = Path(__file__).resolve().parent
bad: list[str] = []
candidates = [repo / "main_webview.py", *(repo / "app").glob("*.py")]
for f in candidates:
    text = f.read_text(encoding="utf-8")
    if 'getattr(gui, "webview"' in text and f.name != "shell_adapter.py":
        bad.append(f.name)
check("S1 坏解析路径（gui.webview）全仓仅存于 shell_adapter 兜底",
      bad == [], detail=f"残留文件: {bad}")

if failures:
    print("FAILED: " + str(len(failures)))
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("OK: native core resolution / window-open gate selftest passed")
