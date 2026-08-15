"""asset_scheme.py —— 随包资产的安全自定义 scheme（aegisasset://）。

背景：新标签页（setHtml + CSP `img-src 'none'`）默认不允许任何图片/外部
资源。为了把随包壁纸安全地渲染进 NTP，而**不放宽为任意 http/file 加载**，
这里注册一个只读的自定义 scheme：

    aegisasset://wallpapers/aurora-magenta.jpg

安全边界（P0）：
- **白名单**：只允许命中 `WALLPAPERS` 常量中登记的固定文件名，任何
  其他路径一律 404——不存在"用 url 拼出任意文件"的面。
- **防路径穿越**：对 path 做 basename 规整，拒绝含 `/` `..` `\\` 的请求。
- **只读静态**：handler 只 GET 磁盘上 assets/wallpapers/ 内的文件字节，
  无脚本、无重定向、无外部网络。
- scheme 注册必须在创建任何 QWebEngineProfile 之前完成（Qt 约束），
  由 main.py 在构造 QApplication 前调用 ensure_registered()。
"""

import os

from .paths import app_base_dir

SCHEME_NAME = b"aegisasset"
SCHEME_STR = "aegisasset"

# 壁纸 host 段（URL 里 aegisasset://<host>/<file> 的 host）
WP_HOST = "wallpapers"

# 白名单：随包壁纸文件名（新增壁纸须在此登记，否则 404）
WALLPAPERS = (
    "aurora-magenta.jpg",
    "aurora-lime.jpg",
    "aurora-twilight.jpg",
    "aurora-violet.jpg",
)

_registered = False


def _wallpapers_dir() -> str:
    root = getattr(__import__("sys"), "_MEIPASS", None) or app_base_dir()
    return os.path.join(root, "assets", "wallpapers")


def wallpaper_url(name: str) -> str:
    """返回某张随包壁纸的 aegisasset:// URL（仅白名单内有效）。"""
    if name not in WALLPAPERS:
        return ""
    return f"{SCHEME_STR}://{WP_HOST}/{name}"


def ensure_registered():
    """注册自定义 scheme（幂等；必须在 QWebEngineProfile 创建前调用）。"""
    global _registered
    if _registered:
        return
    try:
        from PySide6.QtWebEngineCore import QWebEngineUrlScheme
        scheme = QWebEngineUrlScheme(SCHEME_NAME)
        # Host 段为 wallpapers，路径为文件名；启用 CORS 便于 CSS 背景引用
        scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
        # PySide6 stub 未声明这两个 flag，实际 Qt API 存在 —— 加 ignore 避免静态误报
        scheme.setFlags(QWebEngineUrlScheme.SecureScheme  # type: ignore[attr-defined]
                        | QWebEngineUrlScheme.CorsEnabled)  # type: ignore[attr-defined]
        QWebEngineUrlScheme.registerScheme(scheme)
        _registered = True
    except Exception:
        # Qt 版本差异/已注册等情形下静默降级（NTP 回退纯渐变背景）
        pass


def _fail_code():
    """返回请求失败枚举（跨 Qt 版本取可用常量）。"""
    try:
        from PySide6.QtWebEngineCore import QWebEngineUrlRequestJob
    except Exception:
        return 0
    for cand in ("UrlNotFound", "NotFound", "RequestDenied"):
        v = getattr(QWebEngineUrlRequestJob, cand, None)
        if v is not None:
            return v
    return 0


class AegisAssetHandler:
    """QWebEngineUrlSchemeHandler 实现：仅白名单随包壁纸可被读取。

    用 __new__ 动态返回 Qt 子类实例，避免在无 QtWebEngine 的自测桩
    环境（selftest）导入本模块时即失败。请求对象为 QWebEngineUrlRequestJob，
    正确 API：setReply(content_type, bytes) / fail(reason)。
    """

    def __new__(cls, parent=None):
        from PySide6.QtWebEngineCore import QWebEngineUrlSchemeHandler

        class _Handler(QWebEngineUrlSchemeHandler):
            def requestStarted(self, job):
                try:
                    url = job.requestUrl()
                    host = (url.host() or "").lower()
                    name = (url.path() or "").lstrip("/")
                    # A7（pyscg-0044 Canonicalize Input Before Validating，
                    # OpenSSF Python 安全编码指南）：验证前规范化输入——
                    # NFKC 防 Unicode 变体绕过（如全角/兼容字符伪装路径
                    # 穿越，CWE-180 变体）；零风险（合法名规范化后不变）
                    try:
                        name = unicodedata.normalize("NFKC", name)
                    except Exception:
                        pass  # 规范化失败保持原样（校验仍按原样执行）
                    # host 必须是 wallpapers；文件名须在白名单且无路径穿越
                    ok = (host == WP_HOST and name in WALLPAPERS
                          and "/" not in name and "\\" not in name
                          and ".." not in name)
                    fpath = os.path.join(_wallpapers_dir(), name) if ok else ""
                    if not (fpath and os.path.isfile(fpath)):
                        job.fail(_fail_code())
                        return
                    with open(fpath, "rb") as f:
                        data = f.read()
                    job.setReply(b"image/jpeg", data)
                except Exception:
                    try:
                        job.fail(_fail_code())
                    except Exception:
                        pass

        return _Handler(parent)
