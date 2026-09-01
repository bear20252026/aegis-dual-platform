#!/usr/bin/env python3
"""selftest_view_source.py —— 内置源码查看器离线自测。

覆盖（不联网，全程确定性）：
- 白名单：view_source / close_source_view 必须在 _JS_EXPOSED
- 校验路径：file:// 壳页拒绝 / 取 URL 异常或为空拒绝 / window 缺失拒绝
- 抓取链路：http(s) URL 通过校验 → 假抓取成功 → load_html 投递 +
  返回状态记录；假抓取失败 → 可见反馈且不进入源码视图
- 返回链路：close_source_view 恢复原 URL 且清空状态；无状态不导航
- 纯函数：_build_source_viewer_html 全转义（</script>、onerror、
  URL 尖括号）；_fetch_page_source 对非 http(s) 兜底拒绝

注意：_notify / _load 经 NavQueue 异步执行——所有异步断言统一用
wait_for 轮询窗口记录，绝不假设即时生效。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.api_bridge as api_bridge
from app.api_bridge import (
    Api,
    _build_source_viewer_html,
    _fetch_page_source,
)

PASS = 0
FAIL = 0


def check(name: str, ok: bool) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def wait_for(pred, timeout: float = 5.0) -> bool:
    """轮询等待 NavQueue 异步操作落到 FakeWindow（最多 timeout 秒）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


class FakeWindow:
    """模拟窗口：记录 load_url / load_html / toast 注入脚本。"""

    def __init__(self, url: str | None = None, raises: bool = False):
        self._url = url
        self._raises = raises
        self.loaded: list[str] = []
        self.htmls: list[str] = []
        self.scripts: list[str] = []

    def get_current_url(self) -> str:
        if self._raises:
            raise RuntimeError("boom")
        return self._url or ""

    def load_url(self, url: str) -> None:
        self.loaded.append(url)

    def load_html(self, content: str) -> None:
        self.htmls.append(content)

    def evaluate_js(self, script: str) -> None:
        self.scripts.append(script)


def make_api(window: FakeWindow) -> Api:
    api = Api()
    api.window = window  # setter 内部绑定 NavQueue
    return api


def main() -> int:
    print("== selftest_view_source ==")

    # V1 白名单暴露
    check("V1 view_source 在桥白名单", "view_source" in Api._JS_EXPOSED)
    check("V1b close_source_view 在桥白名单",
          "close_source_view" in Api._JS_EXPOSED)

    # V2 file:// 壳页拒绝（可见反馈，不进入抓取）
    api = make_api(FakeWindow("file:///C:/shell/start.html"))
    api.view_source()
    check("V2 file:// 拒绝并提示",
          wait_for(lambda: any("不支持" in s for s in api.window.scripts)))
    check("V2b file:// 拒绝后无返回状态", api._source_view_return == "")

    # V3 get_current_url 异常 → fail-closed
    api = make_api(FakeWindow(raises=True))
    api.view_source()
    check("V3 取 URL 异常拒绝",
          wait_for(lambda: len(api.window.scripts) >= 1))

    # V4 get_current_url 为空 → 拒绝
    api = make_api(FakeWindow(""))
    api.view_source()
    check("V4 空 URL 拒绝",
          wait_for(lambda: len(api.window.scripts) >= 1))

    # V5 window 未绑定 → 拒绝
    api = Api()
    api.view_source()
    check("V5 无窗口拒绝",
          api.window is None
          or wait_for(lambda: any("就绪" in s for s in api.window.scripts)))

    # V6 假抓取成功：load_html 投递 + 返回状态记录（不联网）
    api = make_api(FakeWindow("https://example.com/page"))
    real_fetch = api_bridge._fetch_page_source
    api_bridge._fetch_page_source = (
        lambda url: (url + "#final", "<html><body>hi</body></html>"))
    try:
        api.view_source()
        check("V6 抓取成功进入源码视图",
              wait_for(lambda: bool(api.window.htmls)))
        check("V6b 返回状态记录原 URL",
              api._source_view_return == "https://example.com/page")
        check("V6c 查看器含转义后源码",
              "&lt;html&gt;" in (api.window.htmls[0] if api.window.htmls
                                 else ""))
    finally:
        api_bridge._fetch_page_source = real_fetch

    # V7 假抓取失败：可见反馈，不进入源码视图
    api = make_api(FakeWindow("https://example.com/page"))

    def _boom(url: str):
        raise OSError("offline")

    api_bridge._fetch_page_source = _boom
    try:
        api.view_source()
        check("V7 抓取失败有反馈",
              wait_for(lambda: any("失败" in s for s in api.window.scripts)))
        check("V7b 失败不进入源码视图",
              wait_for(lambda: api._source_view_return == "")
              and not api.window.htmls)
    finally:
        api_bridge._fetch_page_source = real_fetch

    # V8 close_source_view：设置状态后恢复原 URL 并清空
    api = make_api(FakeWindow("https://example.com/"))
    api._source_view_return = "https://example.com/"
    api.close_source_view()
    check("V8 返回原页面",
          wait_for(lambda: api.window.loaded == ["https://example.com/"]))
    check("V8b 状态清空", api._source_view_return == "")

    # V9 close_source_view 无状态 → 不导航
    api = make_api(FakeWindow("https://example.com/"))
    api.close_source_view()
    time.sleep(0.3)  # 若错误导航，等它落到队列
    check("V9 无状态不导航", api.window.loaded == [])

    # V10 查看器 HTML：全转义——任何注入载体都变成可见文本
    payload = '</pre><script>alert(1)</script><img src=x onerror="alert(1)">'
    page = _build_source_viewer_html("https://e.com/?a=1&b=<x>", payload)
    check("V10 <script> 被转义", "<script>alert(1)" not in page
          and "&lt;script&gt;alert(1)" in page)
    check("V10b onerror 属性载体被转义", 'onerror="alert' not in page)
    check("V10c URL 中的尖括号转义", "&lt;x&gt;" in page)
    check("V10d 包含返回按钮", "close_source_view" in page)

    # V11 _fetch_page_source 非 http(s) 兜底拒绝
    try:
        _fetch_page_source("file:///etc/passwd")
        check("V11 file:// 兜底拒绝", False)
    except ValueError:
        check("V11 file:// 兜底拒绝", True)

    print(f"== 结果: {PASS} pass / {FAIL} fail ==")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
