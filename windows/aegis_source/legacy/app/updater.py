"""updater.py —— 签名更新框架（安全基线：离线签名 + HTTPS + 可选证书锁定）。

商业级浏览器更新的信任模型（本实现采用）：
1. 发布方用 **只有自己持有的 Ed25519 私钥** 对 manifest 签名；
2. 浏览器内 **写死对应的公钥**，先验证签名，签名不对直接拒收，根本不下安装包；
3. manifest 与安装包地址 **强制 HTTPS**；
4. （可选）对更新服务器证书做 SHA-256 锁定（cert pinning），异常证书直接拒；
5. 下载后再次校验 SHA-256，然后才交安装器。

manifest 示例：
{
  "version": "2.1.0",
  "url": "https://update.example.com/Aegis-2.1.0-setup.exe",
  "sha256": "<hex>",
  "notes": "修复更新器信任链",
  "signature": "<base64(ed25519( version\\nurl\\nsha256\\nnotes ))>"
}

全部网络操作走 QNetworkAccessManager 异步，绝不阻塞 UI 线程。
update_url 为空（默认）则整个功能静默关闭 —— 无隐藏行为。
"""

import base64
import hashlib
import json
import os
import tempfile

from PySide6.QtCore import QCryptographicHash, QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkRequest

from .version import APP_VERSION, is_newer

# --------------------------------------------------------------------------- #
# 受信任公钥集（R5 密钥轮换）：key_id -> base64 公钥。
# 信任集变更只能随已签名的版本发布（信任根不可自举）——常规轮换：
# 提前 2 个发布周期把新公钥加入本集，随后用新私钥签名并声明 key_id。
# 紧急吊销：从本集移除被质疑的 key_id 并随新版本发布。
# 私钥（PKCS8 PEM）存放于仓库外的本地目录 .secrets/update_signing_key
# （该目录已自带 .gitignore 全量忽略），签名请用 tools/sign_release.py。
UPDATE_PUBLIC_KEYS = {
    "v1": "BlqSOVfvsBTlJM2Vvqj+ge/XqeQRYEvuVhyPU1VokvA=",
}
# 兼容旧引用（无 key_id 的 manifest 默认走 v1）
UPDATE_PUBLIC_KEY_B64 = UPDATE_PUBLIC_KEYS["v1"]


def _b64dec(s: str) -> bytes:
    return base64.b64decode(s)


def _public_key(key_id: str = ""):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    kid = (key_id or "").strip() or "v1"
    b64 = UPDATE_PUBLIC_KEYS.get(kid)
    if not b64 or b64.startswith("REPLACE_WITH"):
        return None
    try:
        return Ed25519PublicKey.from_public_bytes(_b64dec(b64))
    except Exception:
        return None


def _canonical(manifest: dict) -> bytes:
    """签名覆盖字段：version / url / sha256 / notes，按固定顺序拼接。"""
    return "\n".join([
        str(manifest.get("version", "")),
        str(manifest.get("url", "")),
        str(manifest.get("sha256", "")),
        str(manifest.get("notes", "")),
    ]).encode("utf-8")


def verify_manifest_signature(manifest: dict) -> bool:
    """验证 manifest 的离线签名。任一异常均返回 False（拒绝）。

    R5：按 manifest.key_id 路由到对应公钥；key_id 未知/未配置公钥
    一律拒绝（宁可错过更新，不可受骗）。
    """
    sig = manifest.get("signature")
    if not sig:
        return False
    key = _public_key(manifest.get("key_id", ""))
    if key is None:
        return False
    try:
        key.verify(_b64dec(sig), _canonical(manifest))
        return True
    except Exception:
        return False


def _peer_leaf_sha256(reply) -> str:
    """取对端叶子证书 SHA-256（十六进制），用于证书锁定。"""
    try:
        conf = reply.sslConfiguration()
        chain = conf.peerCertificateChain() or []
        if not chain:
            cert = conf.peerCertificate()
            if not cert.isNull():
                chain = [cert]
        if not chain:
            return ""
        return bytes(chain[0].digest(QCryptographicHash.Sha256).toHex()).decode(
            "ascii"
        ).lower()
    except Exception:
        return ""


class UpdateChecker(QObject):
    """启动后或菜单触发的更新检查器。"""

    update_available = Signal(dict)   # manifest dict（已验签）
    check_failed = Signal(str)        # 错误说明（给用户看的）
    download_finished = Signal(str)   # 本地安装包路径（已验签+验哈希）

    def __init__(self, config, parent=None, data_dir: str = ""):
        super().__init__(parent)
        self.config = config
        self.data_dir = data_dir
        from PySide6.QtNetwork import QNetworkAccessManager
        self._net = QNetworkAccessManager(self)
        self._net.finished.connect(self._on_reply)
        self._net.sslErrors.connect(self._on_ssl_errors)
        self._download_reply = None
        self._download_path = ""
        self._download_sha = ""
        self._manifest_reply = None
        self._pin = getattr(config, "update_pinned_cert_sha256", "") or ""

    # ------------------------------------------------------------------ #
    def enabled(self) -> bool:
        # MSIX/App Installer 已具备平台级更新与修复能力，不再下载并启动 EXE。
        try:
            from .package_runtime import is_msix_packaged
            if is_msix_packaged():
                return False
        except Exception:
            # 检测失败时维持传统分发行为，不影响非 MSIX 用户。
            pass
        return bool(getattr(self.config, "update_url", ""))

    @staticmethod
    def _require_https(url: str) -> bool:
        return url.startswith("https://")

    def _on_ssl_errors(self, reply, errors):
        # 任何 SSL 错误一律拒绝（含自签/过期/域名不符）。
        reply.abort()
        # v2.1.2 修复：下载中途 SSL 失败也要清掉临时文件，避免残骸堆积。
        if reply is self._download_reply:
            self._cleanup_temp()
        self.check_failed.emit("更新通道 SSL 校验失败，已终止（可能存在中间人）")

    def check(self):
        """发起更新检查；未配置更新源时直接报"已是最新流程关闭"。"""
        if not self.enabled():
            self.check_failed.emit("当前由 App Installer 或未配置更新源管理更新")
            return
        url = getattr(self.config, "update_url", "")
        if not url:
            self.check_failed.emit("未配置更新源（设置 update_url 后启用）")
            return
        if not self._require_https(url):
            self.check_failed.emit("更新源必须走 HTTPS，已拒绝不安全的地址")
            return
        req = self._safe_request(url)
        self._manifest_reply = self._net.get(req)

    @staticmethod
    def _safe_request(url: str):
        """构造请求：禁止跟随"降级/不安全"重定向。

        v2.1.2 修复：QNetworkAccessManager 默认跟随重定向，且允许
        https→http 降级——更新通道若被 302 到明文地址，manifest/安装包
        与证书锁定都会被绕过。此处显式设置为 NoLessSafe（仅同级或更安全的
        跳转），保持信任链完整。
        """
        req = QNetworkRequest(QUrl(url))
        try:
            from PySide6.QtNetwork import QNetworkRequest as _NR
            req.setAttribute(_NR.RedirectPolicyAttribute,
                             _NR.NoLessSafeRedirectPolicy)
        except Exception:
            pass
        return req

    def _on_reply(self, reply):
        try:
            # 证书锁定（可选）：manifest 与安装包下载**都**校验。
            # v2.1.2 修复：此前只在 manifest 阶段锁定，下载阶段被漏掉。
            if self._pin:
                leaf = _peer_leaf_sha256(reply)
                if leaf and leaf != self._pin.lower():
                    self._cleanup_temp()
                    self.check_failed.emit("更新服务器证书与锁定值不符，已终止")
                    return
            if reply.error() != reply.NoError:
                if reply is self._download_reply:
                    self._cleanup_temp()
                    self.check_failed.emit("更新包下载失败")
                else:
                    self.check_failed.emit("检查更新失败：网络或 SSL 错误")
                return
            # v2.1.2 修复：用"应答对象身份"分发，而非请求 URL 字符串比较——
            # 服务器重定向后 reply.request().url() 会变，旧逻辑会把 manifest
            # 响应误判成下载包（或反之）。
            if reply is getattr(self, "_manifest_reply", None):
                self._manifest_reply = None
                self._on_manifest(reply)
            else:
                self._on_download_reply(reply)
        finally:
            reply.deleteLater()

    def _on_manifest(self, reply):
        try:
            data = json.loads(bytes(reply.readAll()).decode("utf-8", "ignore"))
        except Exception:
            self.check_failed.emit("更新清单解析失败")
            return
        ver = str(data.get("version", ""))
        if not ver:
            self.check_failed.emit("更新清单缺少版本号")
            return
        # 关键：先验签，再谈版本比较与下载。
        if not verify_manifest_signature(data):
            self.check_failed.emit("更新清单签名校验失败，已拒绝（来源不可信）")
            return
        if is_newer(ver, APP_VERSION):
            data.setdefault("notes", "")
            self.update_available.emit(data)
        else:
            self.check_failed.emit(f"当前已是最新版本（{APP_VERSION}）")

    # ------------------------------------------------------------------ #
    def download(self, manifest: dict):
        """下载安装包到临时目录，完成后校验 sha256 并发信号。"""
        url = manifest.get("url") or ""
        self._download_sha = (manifest.get("sha256") or "").strip().lower()
        if not url:
            self.check_failed.emit("更新清单缺少下载地址")
            return
        if not self._require_https(url):
            self.check_failed.emit("安装包地址必须走 HTTPS，已拒绝")
            return
        # v2.1.2 修复：清单必须携带非空 sha256 才允许下载。
        # 此前若 sha256 为空，下载完成后直接跳过完整性校验——
        # 攻击者一旦能让清单不含哈希，签名验签就形同虚设。
        if not self._download_sha or len(self._download_sha) != 64:
            self.check_failed.emit("更新清单缺少有效 SHA-256，拒绝下载")
            return
        # 临时文件一旦创建，任何失败路径都必须删除（否则每次失败都留残骸）
        fd, path = tempfile.mkstemp(
            prefix="Aegis-update-", suffix=os.path.basename(url) or ".pkg"
        )
        self._download_path = path
        try:
            os.close(fd)
            req = self._safe_request(url)
            self._download_reply = self._net.get(req)
        except Exception:
            self._cleanup_temp()
            self.check_failed.emit("更新包下载启动失败")

    def _cleanup_temp(self):
        """删除下载临时文件（可重复调用）。"""
        path, self._download_path = self._download_path, ""
        if not path:
            return
        try:
            os.remove(path)
        except OSError:
            pass

    def _on_download_reply(self, reply):
        if reply.error() != reply.NoError:
            self._cleanup_temp()
            self.check_failed.emit("更新包下载失败")
            return
        try:
            with open(self._download_path, "wb") as f:
                f.write(bytes(reply.readAll()))
        except OSError:
            self._cleanup_temp()
            self.check_failed.emit("更新包写入磁盘失败")
            return
        if self._download_sha:
            actual = self._sha256_of(self._download_path)
            if actual != self._download_sha:
                self._cleanup_temp()
                # R7：更新包被拒属于关键安全事件，落审计日志
                try:
                    from .security_audit import audit
                    audit(self.data_dir, "update_rejected", "", "sha256-mismatch")
                except Exception:
                    pass
                self.check_failed.emit("更新包校验失败（SHA-256 不匹配），已丢弃")
                return
        # 此时 manifest 已验签、安装包哈希已匹配 —— 可放心交安装器。
        self.download_finished.emit(self._download_path)

    @staticmethod
    def _sha256_of(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
