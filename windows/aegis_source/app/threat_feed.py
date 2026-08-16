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
    # nosec B310: url 已由 validate_feed_url 强制为 https（上方校验），
    # 非 https 地址在此路径前已抛 ValueError。
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310
        # L-4 修复（防御性安全审查）：订阅源大小上限——防恶意/失控源
        # 耗尽内存（Content-Length 预检 + 流式读取 5MB 上限）
        raw_bytes = _read_limited(resp, max_bytes=5 * 1024 * 1024)
        raw = raw_bytes.decode("utf-8", "ignore")
    domains = []
    seen = set()
    for line in raw.splitlines():
        d = parse_feed_line(line)
        if d and d not in seen:
            seen.add(d)
            domains.append(d)
    return domains


def _read_limited(resp, max_bytes: int) -> bytes:
    """L-4：读取响应但限制最大字节（Content-Length 预检 + 流式截断）。"""
    try:
        cl = int(resp.headers.get("Content-Length") or 0)
        if cl > max_bytes:
            raise ValueError("订阅源过大（Content-Length 超限）")
    except ValueError:
        raise
    except Exception:
        pass
    chunks = []
    total = 0
    while True:
        chunk = resp.read(min(65536, max_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("订阅源过大（超过 5MB 上限）")
        chunks.append(chunk)
    return b"".join(chunks)


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
                    return {line.strip() for line in f if line.strip()}
        except OSError:
            pass
        return set()

    def refresh(self, feed_url: str, on_done=None, on_error=None,
                verify=None):
        """后台线程拉取；完成回调 (count)，失败回调 (message)。

        W-05 整改（国防级审查）：refresh 原被错误缩进到 host_is_blocked
        函数体内（不可达）——已修正为 ThreatFeedUpdater 类方法。
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
                # nosec B310: feed_url 已由 validate_feed_url 强制为 https（见上文），
                # 且可选 verify 签名校验；非 https 地址在此路径前已被拒绝。
                with urllib.request.urlopen(feed_url, timeout=15.0) as resp:  # nosec B310
                    # P1-2 修复（专家审查）：复用 _read_limited（限流读取——
                    # 防失控/恶意订阅源耗尽内存——N-12）
                    raw = _read_limited(resp, max_bytes=5 * 1024 * 1024)
                if verify is not None:
                    ok = False
                    try:
                        ok = bool(verify(raw))
                    except Exception as e:
                        raise ValueError(f"签名校验异常：{e}") from e
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
                # P1-2 修复（专家审查）：临时文件 + fsync + 原子 os.replace——
                # 防半写缓存（读取中断时旧缓存保持完整——N-12）
                tmp = self._file + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write("\n".join(domains))
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self._file)
                from .security import harden_perms
                harden_perms(self._file)
                if on_done:
                    on_done(len(domains))
            except Exception as e:
                if on_error:
                    on_error(f"订阅源刷新失败：{e}")

        threading.Thread(target=_worker, daemon=True).start()


def host_is_blocked(host: str, blocked: set) -> bool:
    """判断 host 是否命中黑名单（精确或子域后缀匹配，落地 A-②）。

    blocked 为 ThreatFeedUpdater.load_cached() 返回的域名集合。
    - 精确：example.com in blocked
    - 子域：evil.example.com 命中 blocked 中的 example.com
    - blocked 为空 → 一律放行（未配置订阅源时不影响正常浏览）
    """
    if not host or not blocked:
        return False
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        return False
    if h in blocked:
        return True
    # 子域后缀匹配：逐级剥离最左标签
    parts = h.split(".")
    for i in range(1, len(parts)):
        if ".".join(parts[i:]) in blocked:
            return True
    return False
