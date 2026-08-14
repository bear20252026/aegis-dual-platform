"""sync.py —— 加密同步备份（云同步的客户端侧，标准 #34）。

本地侧能力（已完备）：
- 把书签/历史摘要/阅读清单/部分设置打包为 JSON
- 用户口令 PBKDF2(25万轮) 派生 Fernet 密钥端到端加密
- 格式：ABSYNC1 + salt(16B) + Fernet token；篡改/错口令即拒绝

传输侧（已留接口）：
- LocalFileTransport：文件导入导出（本轮可用）
- WebDAVTransport：PUT/GET 到自建 WebDAV / 坚果云等（配置后即可用）

密钥只由口令当场派生，永不落盘 —— 与密码库的密钥策略一致。
"""

import base64
import hashlib
import json
import os

_MAGIC = b"ABSYNC1"
_PBKDF2_ROUNDS = 250_000


class SyncError(Exception):
    pass


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"),
                              salt, _PBKDF2_ROUNDS)
    return base64.urlsafe_b64encode(key)


def encrypt_bundle(payload: dict, passphrase: str) -> bytes:
    """打包并加密。"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise SyncError("缺少 cryptography，无法加密同步包")
    if not passphrase:
        raise SyncError("口令不能为空")
    salt = os.urandom(16)
    token = Fernet(_derive_key(passphrase, salt)).encrypt(
        json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return _MAGIC + salt + token


def decrypt_bundle(blob: bytes, passphrase: str) -> dict:
    """解密并校验；任何失败抛 SyncError（绝不返回半截数据）。"""
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError:
        raise SyncError("缺少 cryptography")
    if not blob or not blob.startswith(_MAGIC):
        raise SyncError("不是有效的 Aegis 同步包")
    salt, token = blob[len(_MAGIC):len(_MAGIC) + 16], blob[len(_MAGIC) + 16:]
    try:
        payload = Fernet(_derive_key(passphrase, salt)).decrypt(token)
    except (InvalidToken, Exception):
        raise SyncError("口令错误或数据已损坏")
    try:
        return json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise SyncError("同步包内容损坏")


# ---------------------------------------------------------------------- #
class SyncCollector:
    """从 BrowserContext 收集可同步数据 / 写回。"""

    def __init__(self, ctx):
        self.ctx = ctx

    def collect(self) -> dict:
        from .version import APP_VERSION
        ctx = self.ctx
        return {
            "app": "Aegis",
            "version": APP_VERSION,
            "bookmarks": [{"title": b["title"], "url": b["url"]}
                          for b in ctx.bookmarks.all()],
            "reading_list": [{"url": r["url"], "title": r["title"],
                              "read": r["read"]}
                             for r in ctx.reading.all()],
            "settings": {
                "homepage": ctx.config.homepage,
                "engine": ctx.config.engine,
                "theme": ctx.config.theme,
            },
        }

    def restore(self, payload: dict, merge: bool = True) -> dict:
        # v2.1.2 修复：同步包来自外部（可能是他人的备份文件），
        # 恢复前先对 URL 做 scheme 白名单过滤，杜绝向书签/阅读清单
        # 注入 javascript:/file: 等危险地址。
        try:
            from .security import safe_url
        except Exception:
            safe_url = None
        ctx = self.ctx
        stats = {"bookmarks": 0, "reading": 0}
        for b in payload.get("bookmarks", []):
            url = safe_url(b.get("url", ""), allow_internal=False) if safe_url \
                else b.get("url", "")
            if not url:
                continue
            if ctx.bookmarks.add(b.get("title", ""), url):
                stats["bookmarks"] += 1
        for r in payload.get("reading_list", []):
            url = safe_url(r.get("url", ""), allow_internal=False) if safe_url \
                else r.get("url", "")
            if not url:
                continue
            if ctx.reading.add(url, r.get("title", "")):
                stats["reading"] += 1
        if not merge:
            cfg = ctx.config
            s = payload.get("settings", {})
            if isinstance(s.get("homepage"), str) and s["homepage"].startswith(("http://", "https://")):
                cfg.homepage = s["homepage"]
            if isinstance(s.get("engine"), str):
                cfg.engine = s["engine"]
            if s.get("theme") in ("auto", "dark", "light"):
                cfg.theme = s["theme"]
        return stats


# ---------------------------------------------------------------------- #
class LocalFileTransport:
    def save(self, blob: bytes, path: str):
        with open(path, "wb") as f:
            f.write(blob)

    def load(self, path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()


class WebDAVTransport:
    """最小 WebDAV 传输（PUT 覆盖 / GET 读取）。

    安全约束（对照原版）：
    - **强制 HTTPS**：非 https:// 地址直接拒绝，杜绝明文传输凭据；
    - 支持 Bearer Token 鉴权（优先），回退 Basic；
    - 依赖系统 CA 校验证书（urllib 默认行为），自签/异常证书会报 URLError。
    """

    def __init__(self, url: str, username: str = "", password: str = "",
                 token: str = ""):
        if not url:
            raise SyncError("未配置同步地址")
        if not url.startswith("https://"):
            raise SyncError("同步地址必须走 HTTPS（已拒绝明文 http://）")
        self.url = url
        self._auth = None
        if token:
            self._auth = "Bearer " + token
        elif username:
            raw = f"{username}:{password}".encode()
            self._auth = "Basic " + base64.b64encode(raw).decode("ascii")

    def _request(self, method: str, data: bytes | None = None):
        import urllib.request

        orig_netloc = self.url.split("//", 1)[-1].split("/", 1)[0]

        class _NoDowngradeRedirect(urllib.request.HTTPRedirectHandler):
            """v2.1.2 修复：urllib 默认会跟随 https→http 的 302 并
            **原样转发 Authorization 头**——明文通道直接泄掉凭据，
            击穿"强制 HTTPS"承诺。此处拒绝任何非 https 跳转目标，
            且跨主机跳转剥离鉴权头（防凭据被转发给第三方）。"""

            def redirect_request(self, req, fp, code, msg, headers, newurl):
                newurl = str(newurl)
                if not newurl.lower().startswith("https://"):
                    raise SyncError(
                        "同步服务器尝试重定向到非 HTTPS 地址，已拒绝")
                newreq = super().redirect_request(
                    req, fp, code, msg, headers, newurl)
                try:
                    if newurl.split("//", 1)[-1].split("/", 1)[0] != orig_netloc:
                        newreq.remove_header("Authorization")
                except Exception:
                    pass
                return newreq

        req = urllib.request.Request(self.url, data=data, method=method)
        if self._auth:
            req.add_header("Authorization", self._auth)
        opener = urllib.request.build_opener(_NoDowngradeRedirect())
        # urlopen 对 https 默认校验证书；证书异常会抛 URLError，
        # 这里不吞掉，交由调用方提示用户。
        return opener.open(req, timeout=30)

    def save(self, blob: bytes, path: str | None = None):
        self._request("PUT", data=blob).close()

    def load(self, path: str | None = None) -> bytes:
        return self._request("GET").read()


def load_webdav_auth() -> tuple:
    """读取 WebDAV 鉴权凭据（token 优先，其次密码）。

    顺序：环境变量 AEGIS_WEBDAV_TOKEN / AEGIS_WEBDAV_PASSWORD →
    ~/.config/aegis/sync.key（支持格式：token:xxx / password:xxx / 裸值一行）。
    凭据不入 config.json，避免明文落盘（与密码库同哲学）。
    返回 (token, password)，可能均为空串。
    """
    import os
    token = (os.environ.get("AEGIS_WEBDAV_TOKEN") or "").strip()
    password = (os.environ.get("AEGIS_WEBDAV_PASSWORD") or "").strip()
    if token or password:
        return token, password
    try:
        p = os.path.join(os.path.expanduser("~"), ".config", "aegis", "sync.key")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                val = f.read().strip()
            if val.startswith("token:"):
                return val[6:].strip(), ""
            if val.startswith("password:"):
                return "", val[9:].strip()
            return "", val
    except Exception:
        pass
    return "", ""
