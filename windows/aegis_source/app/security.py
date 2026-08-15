"""security.py —— 统一安全关口（v1.4 安全整改）。

原则：所有导航入口（IPC / 会话恢复 / 书签 / 历史 / 拨号 / 命令行 / 地址栏）
加载 URL 前必须经过 safe_url()；危险文件下载必须二次确认；
敏感数据文件在 POSIX 上收紧为 0600。
"""

import os
import sys
from urllib.parse import urlparse

# 外部可导航 scheme（白名单）
EXTERNAL_SAFE_SCHEMES = {"http", "https"}
# about: 用于空白页
ABOUT_SCHEMES = {"about"}
# 壳层内部伪协议（setHtml 场景，不应来自外部输入）
INTERNAL_SCHEMES = {"aegis", "reader", "data", "blob"}

# 可执行/脚本类危险下载扩展名（Windows 为主）
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".pif", ".vbs",
    ".vbe", ".js", ".jse", ".wsf", ".wsh", ".ps1", ".psm1", ".lnk",
    ".hta", ".jar", ".apk", ".dll", ".reg", ".cpl", ".appref-ms",
}


def scheme_of(url: str) -> str:
    try:
        return (urlparse(url).scheme or "").lower()
    except Exception:
        return ""


def safe_url(url: str, allow_internal: bool = True) -> str:
    """统一导航过滤：返回可安全加载的 URL，否则返回空串。

    - http/https 永远放行
    - about: 与内部伪协议仅在 allow_internal=True（壳层自身流程）时放行
    - file:/javascript:/vbscript:/chrome: 等一律拒绝
    """
    url = (url or "").strip()
    if not url:
        return ""
    s = scheme_of(url)
    if s in EXTERNAL_SAFE_SCHEMES:
        return url
    if allow_internal and (s in ABOUT_SCHEMES or s in INTERNAL_SCHEMES):
        return url
    return ""


def is_dangerous_download(path_or_url: str) -> bool:
    """判断下载目标是否为可执行/脚本类高危类型。

    M-4 修复（防御性安全审查）：Windows 落盘语义——反复剥离尾部点与
    空格后再判定（a.exe. → .exe——CWE-59 变体）；URL 解码覆盖 %2E 等
    编码变体；解析异常 fail-closed（按危险处理——拒绝）。
    """
    try:
        path = urlparse(path_or_url).path if "://" in path_or_url else path_or_url
        from urllib.parse import unquote
        path = unquote(path)
        while path.endswith((".", " ")):
            path = path[:-1]
        ext = os.path.splitext(path)[1].lower()
        return ext in DANGEROUS_EXTENSIONS
    except Exception:
        return True  # M-4：解析异常 fail-closed——按危险处理


def normalize_credential_host(host: str) -> str:
    """R9：凭据 key 归一化到简化 eTLD+1（可注册域）。

    无 public suffix 表：两级后缀启发式——常见多级后缀（com/cn/co 等）
    取最后 3 段，其余取最后 2 段。用于 L3 密码库匹配：
    login.bank.com 与 www.bank.com 共用条目；
    bank.com.evil.com 归一到 evil.com（混淆域名负例，防误配）。
    """
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        return ""
    parts = h.split(".")
    if len(parts) <= 2:
        return h
    # 两级后缀（co.uk / co.jp / com.cn 等）：parts[-2] 为 co/gov/edu 等
    # 且 parts[-1] 为地区/国家后缀 → 可注册域取最后 3 段；否则取最后 2 段。
    two_level = {"co", "gov", "edu", "com", "net", "org", "ac", "ne", "or"}
    cc = {"uk", "jp", "cn", "kr", "au", "br", "in", "ru", "fr", "de",
          "nz", "za", "us", "sg", "hk", "tw"}
    if len(parts) >= 3 and parts[-2] in two_level and parts[-1] in cc:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def harden_perms(path: str):
    """收紧敏感文件权限：POSIX 为 0600；Windows 把 DACL 限制为当前用户。

    S-3 修复：Windows 分支不再直接 return —— IPC 令牌/配置等文件此前
    继承目录 ACL，同机其他账户可读。现在断开继承并只保留当前用户一条 ACE。
    """
    if sys.platform == "win32":
        _harden_perms_win(path)
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _harden_perms_win(path: str):
    """Windows：断开 ACL 继承，只授予当前用户访问权。失败静默降级。"""
    try:
        if not os.path.exists(path):
            return
        if _harden_perms_win_api(path):
            return
        _harden_perms_win_icacls(path)
    except Exception:
        # 权限收紧属于纵深防御，任何异常都不应影响主流程
        pass


def _harden_perms_win_api(path: str) -> bool:
    """优先走 pywin32：DACL 只留当前用户，并置 PROTECTED（断开继承）。"""
    try:
        import ntsecuritycon
        import win32api
        import win32security
    except ImportError:
        return False
    try:
        sid, _, _ = win32security.LookupAccountName("", win32api.GetUserName())
        dacl = win32security.ACL()
        # 授予完全控制：令牌/配置文件下次启动仍需由本用户重写
        dacl.AddAccessAllowedAce(win32security.ACL_REVISION,
                                 ntsecuritycon.FILE_ALL_ACCESS, sid)
        win32security.SetNamedSecurityInfo(
            path, win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION
            | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, dacl, None)
        return True
    except Exception:
        return False


def _harden_perms_win_icacls(path: str):
    """回退方案：icacls 断继承 + 只授权当前用户（不经 shell，无注入面）。"""
    import subprocess

    user = (os.environ.get("USERNAME") or "").strip()
    if not user:
        return
    try:
        subprocess.run(
            ["icacls", os.path.abspath(path), "/inheritance:r",
             "/grant:r", f"{user}:F"],
            shell=False, check=False, timeout=10,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass
