# -*- coding: utf-8 -*-
"""threat_feed.py —— 恶意站点情报订阅源（SafeBrowsing 的数据补给线）。

支持订阅远端纯文本黑名单（每行一个域名），兼容常见语法子集：
  - 注释行：以 ! 或 # 开头
  - AdBlock 主机语法：||example.com^  → example.com
  - 普通行：example.com

刷新后落盘缓存到数据目录 threat_feed.txt，供 SafeBrowsing 合并。
刷新在后台线程执行，绝不阻塞 UI。

S-4 安全约束：订阅源地址**强制 https://**（明文 http 可被投毒，
直接污染本地黑名单）。file:// 只在显式设置离线测试开关
`AEGIS_THREAT_FEED_ALLOW_FILE=1` 时才放行，默认一律拒绝。
"""

import os
import re
import threading
from urllib.parse import urlparse

# 离线自测白名单开关（默认关闭）：允许 file:// 订阅源
_ALLOW_FILE_ENV = "AEGIS_THREAT_FEED_ALLOW_FILE"


def file_feed_allowed() -> bool:
    """是否显式开启了 file:// 订阅源（离线测试用）。"""
    return os.environ.get(_ALLOW_FILE_ENV, "") == "1"


def validate_feed_url(feed_url: str) -> str:
    """校验订阅源地址：合法返回原地址，非法返回空串。

    - https://  永远放行；
    - file://   仅在 AEGIS_THREAT_FEED_ALLOW_FILE=1 时放行；
    - 其余（http/ftp/data/…）一律拒绝。
    """
    url = (feed_url or "").strip()
    if not url:
        return ""
    try:
        scheme = (urlparse(url).scheme or "").lower()
    except Exception:
        return ""
    if scheme == "https":
        return url
    if scheme == "file" and file_feed_allowed():
        return url
    return ""


def parse_feed_line(line: str):
    """把一行文本规整为域名；无效返回 None。"""
    text = line.strip()
    if not text or text.startswith(("!", "#")):
        return None
    # AdBlock 主机语法 ||host^
    if text.startswith("||") and text.endswith("^"):
        text = text[2:-1]
    elif text.startswith("||"):
        text = text[2:]
    # 去掉协议与路径残留
    text = re.sub(r"^https?://", "", text).split("/")[0].split(":")[0]
    text = text.strip().strip("^").lower()
    if not text or "." not in text and text != "localhost":
        return None
    return text


def fetch_feed(feed_url: str, timeout: float = 15.0) -> list:
    """拉取并解析订阅源，返回域名列表。

    只接受 https://（file:// 需显式开启离线测试开关），否则抛 ValueError。
    """
    import urllib.request
    url = validate_feed_url(feed_url)
    if not url:
        raise ValueError("订阅源地址必须为 https://（file:// 需显式开启离线测试开关）")
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    domains = []
    seen = set()
    for line in raw.splitlines():
        d = parse_feed_line(line)
        if d and d not in seen:
            seen.add(d)
            domains.append(d)
    return domains


class ThreatFeedUpdater:
    """把订阅源域名合并进数据目录缓存文件。"""

    def __init__(self, data_dir: str):
        self._dir = data_dir
        self._file = os.path.join(data_dir, "threat_feed.txt")

    def cache_path(self) -> str:
        return self._file

    def load_cached(self) -> set:
        try:
            if os.path.exists(self._file):
                with open(self._file, "r", encoding="utf-8") as f:
                    return {l.strip() for l in f if l.strip()}
        except OSError:
            pass
        return set()

    def refresh(self, feed_url: str, on_done=None, on_error=None,
                verify=None):
        """后台线程拉取；完成回调 (count)，失败回调 (message)。

        R1：verify 为可选签名校验 callable(raw_bytes)->bool；
        非 None 时校验失败拒绝落盘（服务端签名分发未就绪时保持 None）。
        """
        if not feed_url:
            if on_error:
                on_error("未配置订阅源地址（threat_feed_url）")
            return
        if not validate_feed_url(feed_url):
            if on_error:
                on_error("订阅源地址必须为 HTTPS")
            return

        def _worker():
            try:
                import urllib.request
                with urllib.request.urlopen(feed_url, timeout=15.0) as resp:
                    raw = resp.read()
                if verify is not None:
                    ok = False
                    try:
                        ok = bool(verify(raw))
                    except Exception as e:
                        raise ValueError(f"签名校验异常：{e}")
                    if not ok:
                        raise ValueError("签名校验失败，拒绝落盘")
                domains = []
                seen = set()
                for line in raw.decode("utf-8", "ignore").splitlines():
                    d = parse_feed_line(line)
                    if d and d not in seen:
                        seen.add(d)
                        domains.append(d)
                os.makedirs(self._dir, exist_ok=True)
                with open(self._file, "w", encoding="utf-8") as f:
                    f.write("\n".join(domains))
                from .security import harden_perms
                harden_perms(self._file)
                if on_done:
                    on_done(len(domains))
            except Exception as e:
                if on_error:
                    on_error(f"订阅源刷新失败：{e}")

        threading.Thread(target=_worker, daemon=True).start()
