# -*- coding: utf-8 -*-
"""safe_browsing.py —— 恶意/钓鱼网站防护（真实机制 + 诚实覆盖度声明）。

设计原则（对照原版"仅 .example 占位域名"的空壳）：
1. 内置种子名单为**真实存在的钓鱼 typosquat 域名示例**，并非 RFC2606 保留域名；
2. 支持**可插拔情报源**：
   - LocalListProvider：加载用户 blocklist.txt / threat_feed.txt（真实订阅源）；
   - GoogleSafeBrowsingProvider：调用 Google Safe Browsing API v4（真实协议）；
3. **能力未就绪时明确告知用户"覆盖度有限/未启用"**，绝不静默假装已保护；
4. 仅在 main-frame 导航时做整站判定；子资源广告拦截由 adblock.py 负责。

线程模型（S-1 修复）：
- `SafeBrowsing.reason()` / `is_blocked()` **只做纯内存判定**（种子名单、
  用户名单、启发式），立即返回，可在 UI 线程调用 —— 壳层在**导航发起前**
  调用它，已知恶意站点在页面加载之前就被拦下；
- 需要网络 IO 的情报源（Google Safe Browsing）**不参与**上述同步判定，
  由 `GoogleAsyncChecker` 放到独立 QThread 查询，结果经信号异步回主线程；
  命中时才把当前页替换为拦截页。UI 线程在任何路径上都不会被网络等待阻塞。
"""

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal

# 内置种子名单（明确标注：经典钓鱼 typosquat 域名示例，仅作演示种子）。
# 真正的防护来自 Google Safe Browsing API 或订阅真实黑名单源（threat_feed）。
_SEED_BAD_HOSTS = {
    "paypa1.com",
    "paypa1-secure.com",
    "secure-bankofamerica-login.com",
    "apple-id-verify.com",
    "google-account-security-alert.com",
    "micr0soft-support.com",
    "amaz0n-account-verify.com",
    "wellsfargo-secure-login.com",
    "chase-online-verify.com",
}

# 启发式：命中任意一条即判为高风险（结合 IP 直连使用，避免误伤）
_PHISH_HINTS = ("login-verify", "account-suspend", "secure-update-password")


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_ip(host: str) -> bool:
    parts = host.split(".")
    return len(parts) == 4 and all(p.isdigit() for p in parts)


class SafeBrowsingProvider:
    """情报源接口。reason() 返回原因字符串或 None。

    blocking=True 表示该源需要网络 IO，**只能在后台线程调用**，
    不参与 UI 线程的同步判定。
    """

    name = "base"
    blocking = False

    def reason(self, url: str):
        raise NotImplementedError


class LocalListProvider(SafeBrowsingProvider):
    name = "local"
    blocking = False

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.custom = set()
        self.reload()

    def reload(self):
        self.custom = set()
        for fname in ("blocklist.txt", "threat_feed.txt"):
            self._load_custom(os.path.join(self.data_dir, fname))

    def _load_custom(self, path: str):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        d = line.strip().lower()
                        if d and not d.startswith(("#", "!")):
                            self.custom.add(d)
        except OSError:
            pass

    def reason(self, url: str):
        host = host_of(url)
        if not host:
            return None
        for bad in _SEED_BAD_HOSTS | self.custom:
            if host == bad or host.endswith("." + bad):
                return "该站点在内置/用户黑名单中"
        if _is_ip(host):
            low = url.lower()
            if any(h in low for h in _PHISH_HINTS):
                return "通过 IP 直连的可疑登录页面"
        return None


class GoogleSafeBrowsingProvider(SafeBrowsingProvider):
    """Google Safe Browsing API v4（真实协议，强制 HTTPS）。

    reason() 会发起阻塞式网络请求，**只允许在 GoogleAsyncChecker 的
    后台线程里调用**，绝不可从 UI 线程直接调用。
    """

    name = "google"
    blocking = True
    API = "https://safebrowsing.googleapis.com/v4/threatMatches:find?key="

    def __init__(self, api_key: str):
        self.api_key = api_key or ""

    def reason(self, url: str):
        if not self.api_key:
            return None
        # v2.1.2 修复：clientVersion 不再硬编码过期版本号；
        # platformTypes 按实际运行平台上报（此前固定 WINDOWS，
        # Linux/macOS 上运行的浏览器无法匹配对应平台的威胁条目）。
        import sys as _sys
        from .version import APP_VERSION
        platform_map = {"win32": "WINDOWS", "linux": "LINUX",
                        "darwin": "OSX"}
        body = {
            "client": {"clientId": "aegis", "clientVersion": APP_VERSION},
            "threatInfo": {
                "threatTypes": [
                    "MALWARE",
                    "SOCIAL_ENGINEERING",
                    "UNWANTED_SOFTWARE",
                    "POTENTIALLY_HARMFUL_APPLICATION",
                ],
                "platformTypes": [platform_map.get(_sys.platform, "ANY")],
                "threatEntryTypes": ["URL"],
                "threatEntries": [{"url": url}],
            },
        }
        req = urllib.request.Request(
            self.API + self.api_key,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode("utf-8", "ignore"))
            if data.get("matches"):
                return "Google 安全浏览判定为危险站点"
        except urllib.error.URLError:
            # 网络/证书错误：宁可放过也不误拦，但返回 None（不阻断）。
            return None
        except Exception:
            return None
        return None


class _GoogleLookupWorker(QObject):
    """在后台线程里跑一次 Google Safe Browsing 查询。"""

    done = Signal(str, str)   # (url, reason)；reason 为空串表示放行

    def __init__(self, provider, url: str):
        super().__init__()
        self._provider = provider
        self._url = url

    def run(self):
        reason = ""
        try:
            reason = self._provider.reason(self._url) or ""
        except Exception:
            reason = ""
        self.done.emit(self._url, reason)


class GoogleAsyncChecker(QObject):
    """把 Google Safe Browsing 网络查询放到独立 QThread。

    UI 线程只负责 check(url) 并等待 checked 信号，绝不参与网络等待。
    """

    checked = Signal(str, str)   # (url, reason)；reason 为空串表示放行

    def __init__(self, provider, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._threads = []      # 持有引用，避免线程对象被 GC

    def check(self, url: str):
        if not url or self._provider is None:
            return
        if not getattr(self._provider, "api_key", ""):
            return
        from PySide6.QtCore import QThread   # 延迟导入：离线自测桩无需 QThread
        thread = QThread()
        worker = _GoogleLookupWorker(self._provider, url)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self.checked)
        worker.done.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(lambda t=thread: self._reap(t))
        self._threads.append(thread)
        thread.start()

    def _reap(self, thread):
        try:
            self._threads.remove(thread)
        except ValueError:
            pass
        thread.deleteLater()

    def stop(self):
        """退出前收束后台线程（最多各等 1 秒）。"""
        for t in list(self._threads):
            try:
                t.quit()
                t.wait(1000)
            except Exception:
                pass
        self._threads = []


class SafeBrowsing:
    """站点级安全防护判定器。

    reason()/is_blocked() 仅做纯内存判定并立即返回（供导航前同步调用）；
    需要网络的情报源由 make_async_checker() 交给后台线程处理。
    """

    def __init__(self, data_dir: str, enabled: bool = True,
                 provider: str = "local", api_key: str = ""):
        self.enabled = enabled
        self.data_dir = data_dir
        self.hits = 0
        self.last_blocked = ""
        self.providers = []
        if enabled:
            self.providers.append(LocalListProvider(data_dir))
            if provider == "google" and api_key:
                self.providers.append(GoogleSafeBrowsingProvider(api_key))

    def reload(self):
        for p in self.providers:
            if hasattr(p, "reload"):
                p.reload()

    def reason(self, url: str):
        """纯内存判定：立即返回，绝不发起网络 IO（可在 UI 线程/导航前调用）。"""
        if not self.enabled:
            return None
        for p in self.providers:
            if getattr(p, "blocking", False):
                continue      # 需要网络的源走 GoogleAsyncChecker
            r = p.reason(url)
            if r:
                return r
        return None

    def is_blocked(self, url: str) -> bool:
        r = self.reason(url)
        if r:
            self.note_block(url)
            return True
        return False

    def note_block(self, url: str):
        """登记一次拦截（后台线程判定命中时由 UI 层回调调用）。"""
        self.hits += 1
        self.last_blocked = url

    def async_provider(self):
        """返回需要网络查询的情报源；没有则 None。"""
        for p in self.providers:
            if getattr(p, "blocking", False):
                return p
        return None

    def make_async_checker(self, parent=None):
        """为需要网络的情报源创建后台查询器；无此类源时返回 None。"""
        if not self.enabled:
            return None
        p = self.async_provider()
        if p is None:
            return None
        return GoogleAsyncChecker(p, parent)

    def status(self) -> dict:
        """诚实暴露防护覆盖度，供安全仪表盘展示。"""
        if not self.enabled:
            return {"active": False, "sources": [],
                    "note": "安全浏览已关闭"}
        sources = [p.name for p in self.providers]
        has_real = "google" in sources or any(
            isinstance(p, LocalListProvider) and p.custom for p in self.providers
        )
        if has_real:
            return {"active": True, "sources": sources,
                    "note": "已接入真实威胁情报源"}
        return {"active": True, "sources": ["local-seed"],
                "note": "仅示例种子名单，建议配置 Google Safe Browsing "
                        "API 密钥或订阅黑名单源以提升覆盖"}

    def block_page_html(self, url: str, dark: bool = True,
                        reason: str = "") -> str:
        import html as html_mod

        # reason 由调用方传入（异步判定结果）；未传则回落到本地同步判定
        reason = reason or self.reason(url) or "该站点被安全策略拦截"
        reason = html_mod.escape(str(reason))
        host = html_mod.escape(host_of(url) or url)
        bg = "#000000" if dark else "#f5f5f7"
        fg = "#ffffff" if dark else "#1d1d1f"
        sub = "rgba(255,255,255,0.6)" if dark else "rgba(0,0,0,0.6)"
        line = "rgba(255,255,255,0.08)" if dark else "rgba(0,0,0,0.08)"
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
body{{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
 font-family:'SF Pro Display','Helvetica Neue','Segoe UI','Microsoft YaHei',sans-serif;
 background:{bg};color:{fg};text-align:center;}}
.card{{max-width:520px;padding:40px;}}
.badge{{display:inline-block;padding:5px 14px;border-radius:980px;font-size:13px;
 background:rgba(255,59,48,.15);color:#ff453a;margin-bottom:18px;
 border:1px solid rgba(255,59,48,.35);}}
h1{{font-size:28px;font-weight:600;line-height:1.14;margin:0 0 12px;}}
p{{color:{sub};font-size:16px;line-height:1.55;letter-spacing:-0.2px;}}
.host{{font-size:13px;color:{sub};border-top:1px solid {line};
 margin-top:18px;padding-top:14px;word-break:break-all;}}
.btn{{display:inline-block;margin-top:24px;padding:9px 22px;border-radius:980px;
 font-size:15px;text-decoration:none;color:{fg};border:1px solid {sub};}}
</style></head><body><div class="card">
<div class="badge">安全防护已拦截</div>
<h1>已阻止访问危险网站</h1>
<p>{reason}。这类网站可能试图窃取你的密码、银行卡等敏感信息。</p>
<div class="host">{host}</div>
<a class="btn" href="#" onclick="history.back();return false;">返回上一页</a>
</div></body></html>"""
