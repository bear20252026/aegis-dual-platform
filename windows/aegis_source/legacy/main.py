# -*- coding: utf-8 -*-
"""main.py —— Aegis 程序入口。

启动流程：
1. QtWebEngine 必须在 QApplication 之前初始化（Qt5 要求）
2. 解析命令行参数（无痕 / 配置文件 / 数据目录 / 初始 URL）
3. 单实例：QLockFile + QLocalServer IPC ——
   重复启动时把 URL 转给已运行实例的新标签并聚焦其窗口
4. 创建 BrowserContext 与主窗口
"""

import sys
import os
import time
import secrets
import argparse
import hashlib

# ---- 必须在创建 QApplication 之前导入 WebEngine ----
from PySide6.QtCore import Qt, QLockFile
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.browser import BrowserContext
from app.paths import resolve_data_dir
from app.version import APP_NAME

_IPC_PREFIX = "Aegis-ipc-"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Aegis 现代浏览器")
    p.add_argument("--incognito", action="store_true",
                   help="无痕模式（不保存历史/Cookie/缓存/密码）")
    p.add_argument("--profile", default="default",
                   help="配置文件名称（默认 default）")
    p.add_argument("--data-dir", default=None,
                   help="用户数据根目录")
    p.add_argument("--new-window", action="store_true",
                   help="即使已运行也打开新窗口")
    p.add_argument("url", nargs="?", default="",
                   help="启动时打开的网址")
    return p.parse_args(argv)


def acquire_single_instance(data_dir: str):
    """单实例锁。返回 (lock, is_new)，重复启动返回已存在的锁。"""
    lock_file = os.path.join(data_dir, "single_instance.lock")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError:
        pass
    lock = QLockFile(lock_file)
    lock.setStaleLockTime(30_000)  # 30 秒无响应的陈旧锁自动接管
    if lock.tryLock(0):
        return lock, True
    return lock, False


# ---------------------------------------------------------------------- #
# 单实例 IPC（QLocalServer / QLocalSocket）
# ---------------------------------------------------------------------- #
def _ipc_name(data_dir: str) -> str:
    """按数据目录隔离 IPC 命名空间，避免多配置文件互相串扰。"""
    digest = hashlib.md5(os.path.abspath(data_dir).encode()).hexdigest()
    return _IPC_PREFIX + digest[:12]


def try_forward_url(data_dir: str, url: str) -> bool:
    """若已有实例在监听，则带令牌把 URL 转发给它并返回 True。

    协议（v1.4 M2 修复）：`令牌\nURL`。令牌由服务端每次启动时生成并
    写入数据目录（POSIX 0600）。无有效令牌的连接一律丢弃 ——
    同机任意进程无法再强行注入导航。
    """
    from PySide6.QtNetwork import QLocalSocket
    token = _read_token(data_dir)
    if not token:
        return False
    sock = QLocalSocket()
    sock.connectToServer(_ipc_name(data_dir))
    if not sock.waitForConnected(300):
        sock.abort()
        return False
    try:
        payload = token + "\n" + (url or "")
        sock.write(payload.encode("utf-8"))
        sock.waitForBytesWritten(1000)
        sock.flush()
    finally:
        sock.disconnectFromServer()
    return True


def _token_path(data_dir: str) -> str:
    return os.path.join(data_dir, "ipc.token")


def _read_token(data_dir: str) -> str:
    try:
        with open(_token_path(data_dir), "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


class IpcServer:
    """监听重复启动请求：校验令牌后新标签打开 URL 并激活窗口。"""

    def __init__(self, data_dir: str, window):
        from PySide6.QtNetwork import QLocalServer
        from app.security import harden_perms
        self.window = window
        self._data_dir = data_dir
        # 每次启动生成随机令牌，旧令牌文件立即失效
        self._token = secrets.token_hex(32)
        try:
            os.makedirs(data_dir, exist_ok=True)
            with open(_token_path(data_dir), "w", encoding="utf-8") as f:
                f.write(self._token)
            harden_perms(_token_path(data_dir))
        except OSError:
            pass
        name = _ipc_name(data_dir)
        QLocalServer.removeServer(name)  # 清理上次崩溃遗留
        self.server = QLocalServer()
        if self.server.listen(name):
            self.server.newConnection.connect(self._on_conn)

    def _on_conn(self):
        while self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            # v2.1.2 修复：连接上挂一个累积缓冲——QLocalSocket 不保证
            # 「令牌\nURL」一次性送达；旧逻辑只读第一个分片，长 URL 会被截断。
            conn.setProperty("aegis_buf", b"")
            conn.readyRead.connect(
                lambda c=conn: self._read(c))
            conn.disconnected.connect(
                lambda c=conn: self._finalize(c))
            # 连接即携带数据时 readyRead 可能不再触发，主动读一次
            self._read(conn)

    def _read(self, conn):
        if conn.property("aegis_ipc_done"):
            return
        raw = bytes(conn.readAll())
        if not raw:
            # 连接刚建立数据尚未到达：等待 readyRead 再次触发
            return
        buf = bytes(conn.property("aegis_buf") or b"") + raw
        if b"\n" not in buf:
            # 尚未收全「令牌\nURL」，继续累积（防御超长注入：1MB 上限）
            if len(buf) > 1 << 20:
                conn.setProperty("aegis_ipc_done", True)
                conn.deleteLater()
                return
            conn.setProperty("aegis_buf", buf)
            return
        self._finalize(conn)

    def _finalize(self, conn):
        """连接结束时按已收全的缓冲做一次完整裁决（幂等：处理过即标记）。"""
        if conn.property("aegis_ipc_done"):
            return
        conn.setProperty("aegis_ipc_done", True)
        buf = bytes(conn.property("aegis_buf") or b"")
        conn.setProperty("aegis_buf", b"")
        conn.deleteLater()
        if not buf:
            return
        text = buf.decode("utf-8", "ignore")
        token, _, url = text.partition("\n")
        # v2.1.2 修复：恒定时序比较，避免字节级时序侧信道窥探令牌。
        if not secrets.compare_digest(token.encode("utf-8"),
                                      self._token.encode("utf-8")):
            print("[ipc] 拒绝了一个无有效令牌的连接")
            # R7：IPC 拒绝事件审计
            try:
                from app.security_audit import audit
                audit(self._data_dir, "ipc_denied", "", "bad-token")
            except Exception:
                pass
            return
        from app.security import safe_url
        url = safe_url(url.strip()) or ""
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda u=url: self._open(u))

    def _open(self, url: str):
        w = self.window
        if url:
            w.open_new_tab(url, switch=True)
        w.showNormal()
        w.raise_()
        w.activateWindow()


def create_window(incognito=False, profile_name="default",
                  data_dir=None, initial_url=""):
    """创建主窗口。返回 (window, context)。"""
    base_dir = resolve_data_dir(data_dir)
    ctx = BrowserContext(base_dir, profile_name=profile_name,
                         incognito=incognito)

    from ui.main_window import MainWindow
    window = MainWindow(ctx)
    if initial_url:
        window.open_new_tab(initial_url, switch=True)
    window.show()
    return window, ctx


def _install_crash_hooks(base_dir: str):
    """R7：未捕获异常 + faulthandler 落盘（本地诊断，绝不自动上传）。

    崩溃堆栈写入 <数据目录>/crash.log，下次启动可人工查看；
    不采集任何浏览 URL 全文（隐私优先）。
    """
    import faulthandler
    import traceback as _tb
    try:
        faulthandler.enable()
    except Exception:
        pass
    crash_file = os.path.join(base_dir, "crash.log")

    def _hook(typ, val, tb):
        try:
            with open(crash_file, "a", encoding="utf-8") as f:
                f.write("\n=== %s ===\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
                f.write("".join(_tb.format_exception(typ, val, tb)))
        except Exception:
            pass
        sys.__excepthook__(typ, val, tb)

    sys.excepthook = _hook


def main():
    boot_ts = time.perf_counter()
    # 高 DPI 与 WebEngine 基础环境
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    # QtWebEngine 以插件加载时必须共享 OpenGL 上下文，
    # 否则部分机器会渲染异常/直接崩溃。
    QGuiApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

    args = parse_args()
    base_dir = resolve_data_dir(args.data_dir)
    _install_crash_hooks(base_dir)   # R7：崩溃堆栈本地落盘

    # DevTools 远程调试 + 用户自定义 Chromium 参数（QApplication 前设置）
    _apply_engine_env(base_dir)

    # Windows 任务栏分组/通知归属（标准 #35）
    from app.os_integration import set_app_user_model_id
    set_app_user_model_id()

    # v2.1.5：注册随包资产自定义 scheme（aegisasset://），用于把随包壁纸
    # 安全地渲染进新标签页。必须在任何 QWebEngineProfile 创建前调用。
    try:
        from app.asset_scheme import ensure_registered as _ensure_asset_scheme
        _ensure_asset_scheme()
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setQuitOnLastWindowClosed(True)
    _apply_window_icon(app)

    # 单实例：已有实例运行时把 URL 转发给它然后退出
    lock, is_new = acquire_single_instance(base_dir)
    if not is_new and not args.new_window:
        if args.url and try_forward_url(base_dir, args.url):
            print("Aegis 已在运行，已把网址发送至现有窗口。")
        else:
            print("Aegis 已在运行。")
        return 0

    # 系统协议集成：aegis://https://... -> https://...
    url = args.url or ""
    if url.startswith("aegis://"):
        url = url[len("aegis://"):]

    window, ctx = create_window(
        incognito=args.incognito,
        profile_name=args.profile,
        data_dir=args.data_dir,
        initial_url=url,
    )

    # 启动性能度量（标准 #1：量化冷启动耗时）
    boot_ms = (time.perf_counter() - boot_ts) * 1000.0
    ctx.boot_ms = boot_ms
    window.status.showMessage(f"就绪 · 启动耗时 {boot_ms:.0f} ms", 5000)
    print(f"[startup] 窗口可见耗时 {boot_ms:.0f} ms")

    # 起 IPC 服务接收后续启动请求
    ipc = IpcServer(base_dir, window)
    window._ipc_server = ipc  # 防止被 GC

    # 关闭时保存配置
    app.aboutToQuit.connect(ctx.save_config)

    code = app.exec()
    return code


def _apply_window_icon(app):
    """设置窗口/任务栏图标（assets/icon.png，缺失时安静跳过）。"""
    from PySide6.QtGui import QIcon
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base, "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))


def _apply_engine_env(base_dir: str):
    """QApplication 创建前注入：DevTools 端口 + 用户自定义 Chromium 参数。"""
    from app.config import AppConfig
    cfg = AppConfig.load(base_dir)
    # R11：应用配置语言（重启生效；tr() 语言包随之切换）
    try:
        from app.i18n import set_lang
        set_lang(getattr(cfg, "language", "zh-CN"))
    except Exception:
        pass
    port = cfg.devtools_port
    if port and port > 0:
        os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = str(port)
        # v1.4 M4：远程调试协议可读写本页所有 Cookie/DOM/执行 JS，
        # QtWebEngine 未提供鉴权 —— 启用即显著扩大本地攻击面。
        print(f"[安全警告] DevTools 远程调试已开启于端口 {port}，"
              "仅建议在可信环境排障时使用。")
    # R3：DoH 加密 DNS（候选参数；上线前须在捆绑 Chromium 二进制验证
    # --dns-over-https-* 开关名，参照审查规范 3.4.2 strings 验证法）
    if getattr(cfg, "doh_mode", "off") != "off":
        providers = {
            "cloudflare": "https://cloudflare-dns.com/dns-query",
            "google": "https://dns.google/dns-query",
            "alidns": "https://dns.alidns.com/dns-query",
            "dnspod": "https://doh.pub/dns-query",
        }
        tpl = providers.get(getattr(cfg, "doh_provider", "cloudflare"),
                            providers["cloudflare"])
        prev = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        if "DnsOverHttps" not in prev:
            flag = ("--enable-features=AsyncDns,DnsOverHttps "
                    "--enable-dns-over-https --dns-over-https-upgrade "
                    f"--dns-over-https-template={tpl}")
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (prev + " " + flag).strip()
    extra = (cfg.chromium_flags or "").strip()
    if extra:
        prev = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (prev + " " + extra).strip()
    # 防 WebRTC/IP 泄露：默认只暴露公网接口地址，隐藏真实内网 IP。
    # v2.1.1 修复：参数名必须为 force-webrtc-ip-handling-policy
    # （已在 PySide6 6.11.1 捆绑的 Chromium 140 二进制中验证；
    # 旧写法 --force-webrtc-ip-policy 不是合法开关，会被静默忽略）。
    if cfg.webrtc_ip_leak_protection:
        prev = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        if "force-webrtc-ip-handling-policy" not in prev:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
                (prev + " --force-webrtc-ip-handling-policy="
                 "default_public_interface_only").strip())


if __name__ == "__main__":
    sys.exit(main())
