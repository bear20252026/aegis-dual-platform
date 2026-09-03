"""native_interception.py —— 新窗口门禁 + 原生拦截 + 启动后挂接编排。

P0-1/P0-2 修复（全面审计 2026-09-04）的落点：
- gate_window_open()  类级替换 pywebview EdgeChrome.on_new_window_request——
  新窗口 URI 强制过 safe_url 门禁（先于实例创建，无竞态）
- post_start_setup()  shell.start(func) 回调：等核心就绪后按序挂接
  指纹前置注入 / 新窗口兜底 / 下载显式提示 / 监控 / 崩溃监听 / 加固束
"""

from __future__ import annotations

from app.native_hardening import _apply_window_hardening
from app.native_monitoring import (
    _install_crash_listener,
    _install_probe_and_monitoring,
)
from app.shell_adapter import (
    resolve_core as _resolve_core,
)
from app.url_utils import is_navigation_safe as _is_navigation_safe


def gate_window_open() -> bool:
    """P0-2 修复（全面审计 2026-09-04）：window.open/target=_blank 原生门禁。

    pywebview 自带 NewWindowRequested 处理器（EdgeChrome.on_new_window_request）
    对目标 URI 零校验——set_Handled 后直接 load_url，任何页面可经新窗口
    路径把 file:/内网/威胁黑名单地址灌入当前窗口（safe_url 红线失守口）。

    修复：在 pywebview 创建任何窗口实例**之前**类级替换该处理器——保留
    「在当前窗口内打开」的产品语义，但目标 URI 强制过与地址栏同一门禁
    （is_navigation_safe），不安全 URI 拒绝导航并留痕（fail-closed）。
    类级替换先于实例创建 → 与 pywebview 的 on_webview_ready 订阅时序无关，
    无竞态。返回 False（版本变更/导入失败）由调用方留痕——此时
    _install_native_interception 的 core 级处理器作为兜底仍会注册。
    """
    try:
        import webview.platforms.edgechromium as _ec
        chrome_cls = getattr(_ec, "EdgeChrome", None)
        if chrome_cls is None or not hasattr(chrome_cls, "on_new_window_request"):
            return False

        def _gated_on_new_window_request(self, sender, args):
            """类级替换版：pywebview 原语义（当前窗口打开）+ safe_url 门禁。"""
            args.set_Handled(True)
            # 取 URI 失败 → fail-closed 拒绝（自检 G3 回归：空串不得放行）
            try:
                uri = str(args.get_Uri() or "")
            except Exception:
                from crash_reporter import log_event
                log_event("[security] 新窗口 URI 读取失败——拒绝导航"
                          "（fail-closed）")
                return
            try:
                if uri and uri != "about:blank" and not _is_navigation_safe(uri):
                    from crash_reporter import log_event
                    log_event(f"[security] 新窗口请求拒绝（未过安全门禁）: "
                              f"{uri[:200]}")
                    return
            except Exception:
                from crash_reporter import log_event
                log_event("[security] 新窗口请求安全校验异常——拒绝导航"
                          "（fail-closed）")
                return
            try:
                import webview as _wv
                if _wv.settings.get("OPEN_EXTERNAL_LINKS_IN_BROWSER"):
                    import webbrowser
                    webbrowser.open(uri)
                    return
            except Exception:
                pass  # 开关读取失败 → 保持窗口内打开语义
            self.load_url(uri)

        chrome_cls.on_new_window_request = _gated_on_new_window_request
        from crash_reporter import log_event
        log_event("[security] 新窗口原生门禁已生效（类级，先于实例创建）")
        return True
    except Exception as exc:
        try:
            from crash_reporter import log_event
            log_event(f"[security] 新窗口类级门禁安装失败（降级 core 级注册）: "
                      f"{exc!r}")
        except Exception:
            pass
        return False


def _install_native_interception(window, shell, api, core=None,
                                 window_gate_ok: bool = False):
    """指纹防护前置注入（FIX-1）+ 新窗口 core 级兜底门禁 + 下载显式提示。

    P0-1 时序修复（全面审计 2026-09-04）：本函数原在 shell.start() 之前
    调用，core 恒为 None（window.native 未创建），整段静默 no-op；现由
    _post_start_setup 在窗口/WebView2 就绪后调用。
    """
    from crash_reporter import log_event
    if core is None:
        core = _resolve_core(window)
    if core is None:
        log_event("[security] WebView2 核心不可用——FIX-1 指纹前置注入与"
                  "core 级新窗口兜底未注册（指纹防护退 on_loaded 注入）")
        return

    # === FIX-1: 指纹防护前置注入 ===
    # AddScriptToExecuteOnDocumentCreated 在任何页面脚本执行前注入，无法被
    # 页面脚本绕过。注：核心就绪时首屏（本地壳页，可信）可能已开始加载，
    # 前置注入覆盖其后全部文档；远端页面的首个文档保证被覆盖。
    try:
        from app.fingerprint_pipeline import (
            build_fingerprint_pipeline_js,
            generate_session_seed,
        )
        _fp_seed = generate_session_seed()
        _fp_js = build_fingerprint_pipeline_js(_fp_seed)
        # 真机冒烟（2026-09-04）：pythonnet 对该方法的暴露名随 SDK 版本
        # 存在差异——按候选探测，全部不可达时显式降级（不静默）。
        _inject = None
        for _name in ("AddScriptToExecuteOnDocumentCreated",
                      "AddScriptToExecuteOnDocumentCreatedAsync",
                      "add_ScriptToExecuteOnDocumentCreated"):
            _candidate = getattr(core, _name, None)
            if _candidate is not None:
                _inject = _candidate
                break
        if _inject is None:
            log_event("[security] FIX-1 未注入：pythonnet 未暴露"
                      " AddScriptToExecuteOnDocumentCreated（SDK/运行时差异）——"
                      "降级 on_loaded 注入（bridge_hooks 兜底）")
        else:
            _inject(_fp_js)
            log_event("[security] 指纹防护已注入（页面脚本前生效——FIX-1）")
    except Exception as exc:
        # P0-1 修复：不再静默——显式留痕降级（bridge_hooks.py on_loaded 兜底）
        log_event(f"[security] FIX-1 指纹前置注入失败，降级 on_loaded 注入: "
                  f"{exc!r}")

    # === 新窗口 core 级门禁（仅类级门禁安装失败时注册，避免安全 URI 双重
    # load_url 造成可见的重复导航）===
    if not window_gate_ok:
        try:
            def _on_new_window_requested(sender, args):
                """WebView2 NewWindowRequested 处理器（core 级兜底）。

                拦截所有新窗口请求（target=_blank / window.open），
                过安全门禁后在当前窗口内导航，不交给系统浏览器。"""
                try:
                    uri = args.get_Uri()
                    if uri:
                        args.put_Handled(True)  # 阻止 WebView2 打开新窗口
                        # H-1（审计 2026-08-31）+ P0-2（2026-09-04）：新窗口
                        # 请求与普通导航同权——必须过白名单（file:/javascript:/
                        # data:/blob: 等一律拒绝）；经 NavQueue 投递，绝不在
                        # WebView2 事件线程直接 load_url（死锁 + 越权双因）
                        if uri != "about:blank" and not _is_navigation_safe(uri):
                            log_event("[security] NewWindowRequested 拒绝"
                                      "非白名单 URI")
                            return
                        api._load(uri)
                except Exception:
                    pass  # 单事件失败不影响后续事件
            core.add_NewWindowRequested(_on_new_window_requested)
            log_event("[nav] NewWindowRequested core 级兜底拦截已注册"
                      "（类级门禁未安装）")
        except Exception as exc:
            log_event(f"[security] NewWindowRequested core 级兜底注册失败: "
                      f"{exc!r}")

    # === A2 修复（P0-3，全面审计 2026-09-04）：下载显式提示 ===
    # pywebview 默认 ALLOW_DOWNLOADS=False 且 on_download_starting 直接
    # Cancel——下载被静默禁用（点击无任何反应）。完整下载管理属批次 3；
    # 本修复在下载发起时给用户明确反馈 + 安全日志留痕（取消语义不变，
    # 由 pywebview 默认行为承担；Handled=true 额外抑制任何原生下载 UI）。
    try:
        def _on_download_starting(sender, args):
            try:
                args.put_Handled(True)
            except Exception:
                pass  # 属性缺失时保持 pywebview 默认取消
            try:
                from crash_reporter import log_event
                log_event("[security] 下载请求已取消（当前版本不支持下载）")
            except Exception:
                pass
            try:
                # 经 NavQueue 投递（红线⑤：事件线程绝不直接 evaluate_js）
                api._notify("当前版本不支持下载，该操作已取消")
            except Exception:
                pass  # 提示失败不影响取消语义
        core.DownloadStarting += _on_download_starting
        log_event("[nav] 下载显式提示已注册（下载默认禁用——P0-3）")
    except Exception as exc:
        log_event(f"[nav] DownloadStarting 订阅失败（pywebview 默认取消仍生效）: "
                  f"{exc!r}")


def post_start_setup(window, shell, api, window_gate_ok: bool = False) -> None:
    """窗口/WebView2 就绪后的原生层挂接（P0-1 时序修复的迁移落点）。

    顺序：等内核就绪（有界）→ 链接拦截 + 指纹前置注入 → probe/监控 →
    崩溃监听 → 窗口加固束。每步失败显式留痕（不再静默吞）。
    """
    from crash_reporter import log_event
    # 真机跟进修复（2026-09-04）：本函数现于首个 loaded 事件（GUI 线程）
    # 调用——CoreWebView2 必已就绪，单次解析即可；不再后台线程轮询
    # （跨 STA 线程触碰 WinForms 属性会挂死，真机实测）。
    core = _resolve_core(window)
    if core is None:
        log_event("[native] WebView2 核心不可用——原生加固层降级"
                  "（NewWindowRequested 仅类级门禁兜底，指纹防护退 on_loaded 注入）")
    _install_native_interception(window, shell, api, core,
                                 window_gate_ok=window_gate_ok)
    _install_probe_and_monitoring(window, api)
    _install_crash_listener(window, core)
    _apply_window_hardening(window, api, shell, core)
