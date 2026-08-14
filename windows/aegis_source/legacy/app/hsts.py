"""hsts.py —— HSTS 预加载与严格传输安全。

商业级浏览器内置一份 HSTS 预加载名单：对名单内主机，浏览器会
- 自动把 http:// 升级为 https://（防止 SSL stripping）；
- 证书错误时**绝不**允许继续（HSTS 主机无例外）。

这里内置一份精简但真实的常见大站预加载种子（节选自公开 HSTS 预加载列表），
并支持从数据目录 hsts_preload.txt 扩展。覆盖度有限，仅作基线增强。
"""

from urllib.parse import urlparse

# 精简 HSTS 预加载种子（真实存在的强 HSTS 站点；非穷举）。
_HSTS_SEED = {
    "google.com", "www.google.com", "youtube.com", "mail.google.com",
    "github.com", "www.github.com", "gist.github.com",
    "wikipedia.org", "www.wikipedia.org", "commons.wikimedia.org",
    "twitter.com", "x.com", "facebook.com", "www.facebook.com",
    "login.microsoftonline.com", "account.microsoft.com",
    "appleid.apple.com", "id.apple.com",
    "paypal.com", "www.paypal.com", "accounts.google.com",
    "dropbox.com", "www.dropbox.com", "cloudflare.com", "www.cloudflare.com",
    "proton.me", "mail.proton.me", "fastmail.com", "1password.com",
    "linkedin.com", "www.linkedin.com", "reddit.com", "www.reddit.com",
    "amazon.com", "www.amazon.com", "tinyurl.com",
}


def _load_extra(data_dir: str) -> set:
    extra = set()
    import os

    p = os.path.join(data_dir, "hsts_preload.txt")
    try:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    d = line.strip().lower()
                    if d and not d.startswith(("#", "!")):
                        extra.add(d)
    except OSError:
        pass
    return extra


def is_hsts(host: str, data_dir: str = "") -> bool:
    """host 是否在 HSTS 预加载名单中（含子域后缀匹配）。"""
    host = (host or "").lower()
    if not host:
        return False
    pool = _HSTS_SEED | _load_extra(data_dir)
    if host in pool:
        return True
    return any(host.endswith("." + d) for d in pool)


def preload_count(data_dir: str = "") -> dict:
    """返回 HSTS 预加载覆盖概况（供安全仪表盘如实展示）。"""
    extra = _load_extra(data_dir)
    return {
        "seed": len(_HSTS_SEED),
        "extra": len(extra),
        "total": len(_HSTS_SEED | extra),
    }


def maybe_upgrade(url: str, data_dir: str = "") -> str:
    """若 http:// 且 host 在 HSTS 名单，返回升级后的 https:// 地址；否则原样。"""
    try:
        p = urlparse(url)
    except Exception:
        return url
    if p.scheme == "http" and is_hsts(p.hostname or "", data_dir):
        return url.replace("http://", "https://", 1)
    return url
