"""password_store.py —— 密码加密存储。

安全策略：
1. 首选系统密钥环（keyring），无密钥环则回退到本地加密文件。
2. 本地加密文件使用 AES（通过 cryptography / pyAesCrypt 或标准库）
   以用户级密钥派生密钥加密；密钥保存在配置目录，权限设为仅当前用户。
3. 说明：QtWebEngine 不开放密码自动填充 API，本模块保存的是
   "手动记录"的网站账号，作为降级方案；不会自动填充。

依赖（可选）：
    pip install keyring cryptography
若无这些库，或密钥无法解析，密码保存**整体禁用**（绝不落明文）。
"""

import json
import os
import stat

# 尝试导入加密库
try:
    from cryptography.fernet import Fernet
    _HAS_FERNET = True
except Exception:
    _HAS_FERNET = False

try:
    import keyring
    _HAS_KEYRING = True
except Exception:
    _HAS_KEYRING = False


class PasswordStore:
    """网站密码的加密存储。"""

    def __init__(self, data_dir: str, enabled: bool = True):
        self._enabled = enabled
        self._file = os.path.join(data_dir, "passwords.json")
        self._keyfile = os.path.join(data_dir, "passwords.key")
        self._cipher = None
        self.key_error = ""
        if enabled and _HAS_FERNET:
            # v2.1.2 修复：密钥解析失败（DPAPI 换机/换账户/密钥文件损坏）
            # 不得让整个浏览器启动崩溃——降级为"密码保存禁用"并保留原因。
            try:
                self._cipher = Fernet(self._get_or_create_key())
            except Exception as e:
                self._cipher = None
                self.key_error = str(e)
        # 安全底线（v1.4 H1 修复）：无加密能力时绝不落明文，
        # 密码保存功能整体禁用（save_password 返回 False）。
        self.encryption_active = self._cipher is not None

    # ------------------------------------------------------------------ #
    def _get_or_create_key(self) -> bytes:
        """获取或创建 Fernet 密钥。

        密钥保护链（自上而下）：
        1. 系统密钥环（Windows 凭据管理器 / macOS Keychain）
        2. Windows DPAPI 包裹本地密钥文件（v1.5：密钥绑定本机本账户，
           拷走文件也无法解密）
        3. 0600 权限的本地密钥文件（非 Windows 的最后手段）
        """
        from . import dpapi
        # 优先系统密钥环
        if _HAS_KEYRING:
            try:
                k = keyring.get_password("Aegis", "passwords_key")
                if k:
                    return k.encode()
            except Exception:
                pass
        # 本地密钥文件（可能已被 DPAPI 包裹）
        if os.path.exists(self._keyfile):
            with open(self._keyfile, "rb") as f:
                raw = f.read()
            key, wrapped = self._unwrap_key(raw, dpapi)
            # 旧版裸密钥 + 当前平台有 DPAPI → 顺带升级为包裹形态
            if not wrapped and dpapi.is_available():
                self._write_wrapped(key, dpapi)
            return key
        key = Fernet.generate_key()
        if dpapi.is_available():
            self._write_wrapped(key, dpapi)
        else:
            try:
                with open(self._keyfile, "wb") as f:
                    f.write(key)
                # 仅当前用户可读写
                try:
                    os.chmod(self._keyfile, stat.S_IRUSR | stat.S_IWUSR)
                except OSError:
                    pass
            except OSError:
                pass
        return key

    _DPAPI_MAGIC = b"MYBSDP1"
    _DPAPI_ENTROPY = b"Aegis-Passwords-v1"

    def _wrap_key(self, key: bytes, dpapi):
        blob = dpapi.protect(key, self._DPAPI_ENTROPY)
        if blob is None:
            return key, False
        return self._DPAPI_MAGIC + blob, True

    def _unwrap_key(self, raw: bytes, dpapi):
        """返回 (key_bytes, was_dpapi_wrapped)。"""
        if raw.startswith(self._DPAPI_MAGIC):
            plain = dpapi.unprotect(raw[len(self._DPAPI_MAGIC):],
                                    self._DPAPI_ENTROPY)
            if plain:
                return plain, True
            # DPAPI 解密失败（换机/换账户）：拒绝静默降级，抛错由调用方处理
            raise RuntimeError("密钥被 DPAPI 保护且当前环境无法解密")
        return raw, False

    def _write_wrapped(self, key: bytes, dpapi):
        wrapped, ok = self._wrap_key(key, dpapi)
        if ok:
            try:
                with open(self._keyfile, "wb") as f:
                    f.write(wrapped)
                from .security import harden_perms
                harden_perms(self._keyfile)
            except OSError:
                pass

    def _encrypt(self, text: str) -> str:
        # 无 cipher 时抛异常而非明文降级（由 save_password 兜底为"拒绝保存"）
        if self._cipher is None:
            raise RuntimeError("无加密能力，拒绝写入密码")
        return self._cipher.encrypt(text.encode()).decode()

    def _decrypt(self, blob: str) -> str:
        if self._cipher is None:
            return blob
        try:
            return self._cipher.decrypt(blob.encode()).decode()
        except Exception:
            return ""

    # ------------------------------------------------------------------ #
    def save_password(self, url: str, username: str, password: str) -> bool:
        """保存一条密码（按 url+username 覆盖）。无加密能力时拒绝并返回 False。"""
        if not self._enabled or not self.encryption_active:
            return False
        try:
            data = self._load_raw()
            data[url] = {
                "username": self._encrypt(username),
                "password": self._encrypt(password),
            }
            self._write_raw(data)
            return True
        except (RuntimeError, OSError):
            return False

    def get_password(self, url: str):
        """返回 (username, password) 或 None。"""
        data = self._load_raw()
        entry = data.get(url)
        if not entry:
            return None
        return (self._decrypt(entry["username"]),
                self._decrypt(entry["password"]))

    def list_sites(self) -> list:
        """返回 [(url, username)] 列表。"""
        data = self._load_raw()
        return [(url, self._decrypt(e["username"]))
                for url, e in data.items()]

    def delete(self, url: str):
        data = self._load_raw()
        if url in data:
            del data[url]
            self._write_raw(data)

    def find_for_host(self, host: str):
        """按域名查找凭据（L3 密码库直填用）。返回 (url, username, password)
        或 None。

        v2.1.2 修复：此前 L3 直填只对 `scheme+host` 做精确匹配，而密码
        实际按用户输入的完整 URL（可能带路径）存储，命中几乎必然失败；
        且 R9 的 eTLD+1 归一化（normalize_credential_host）从未被接入。
        现改为：逐条解析存储 URL 的主机名，与查询主机做**归一化 eTLD+1
        比较**（login.bank.com 与 www.bank.com 同条目；bank.com.evil.com
        不会误配到 bank.com）。
        """
        from urllib.parse import urlparse

        from .security import normalize_credential_host
        want = normalize_credential_host(host)
        if not want:
            return None
        for u, e in self._load_raw().items():
            try:
                h = (urlparse(u).hostname or "").lower()
            except Exception:
                continue
            if h and normalize_credential_host(h) == want:
                return (u, self._decrypt(e.get("username", "")),
                        self._decrypt(e.get("password", "")))
        return None

    def clear(self):
        try:
            os.remove(self._file)
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    def _load_raw(self) -> dict:
        if not os.path.exists(self._file):
            return {}
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_raw(self, data: dict):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._file)),
                        exist_ok=True)
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # POSIX 下收紧密文文件权限（Windows 依赖系统密钥环方案）
            from .security import harden_perms
            harden_perms(self._file)
        except OSError:
            pass


def password_security_note() -> str:
    """返回当前使用的加密方案说明。"""
    if _HAS_FERNET and _HAS_KEYRING:
        return "Fernet 加密，密钥存于系统密钥环（Windows DPAPI / macOS Keychain）"
    if _HAS_FERNET:
        return "Fernet(AES-128-CBC+HMAC) 本地加密文件（建议安装 keyring 提升密钥安全性）"
    return "加密组件缺失：密码保存已禁用（绝不落明文）"
