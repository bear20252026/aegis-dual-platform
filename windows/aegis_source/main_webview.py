"""main_webview.py —— Aegis 入口（薄壳，仅负责启动组装）。

架构（S1 拆分后）：
- 本文件只做四件事：解析参数、创建窗口、绑定 Api 桥、启动看门狗。
- 业务逻辑已按单一职责拆分到 app/ 下：
    app/shell_toolbar.py  注入式工具栏脚本（TOOLBAR_JS + 渲染）
    app/nav_queue.py      导航线程队列（窗口操作串行化，防死锁）
    app/api_bridge.py     js_api 桥（标签/导航/书签/历史/壁纸/搜索）
- 本文件不 import Qt；webview 延迟导入（仅 main() 运行时）。

运行（源码）：
    python main_webview.py
    python main_webview.py --smoke-test   # 无窗口自检：建隐藏窗口→10 秒→退出
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Any

from app.api_bridge import SEARCH_ENGINES, START_URL, Api, on_loaded

# C2 阶段 A（ceLLMate 借鉴）：Agent 请求白名单域（agent-browser domain
# allowlist 模式——Agent 会话活跃时仅允许这些域的请求；默认空=Agent 活跃
# 时非白名单域请求标记 + 日志（可观测不拦截）——政府内网按需配置内网域）
AGENT_ALLOWED_HOSTS: set[str] = set()

# C2 阶段 B（ceLLMate sitemap）：内网 Agent sitemap 路径（JSON——语义动作
# ↔ HTTP 消息映射，见 docs/release/agent-sitemap.example.json；默认空=未
# 启用（仅阶段 A 域白名单）——内网运维按需配置）
AGENT_SITEMAP_PATH = ""


def _load_agent_sitemap() -> dict | None:
    """加载内网 Agent sitemap（JSON）；未配置/失败返回 None（静默）。"""
    if not AGENT_SITEMAP_PATH:
        return None
    try:
        import json
        from pathlib import Path
        p = Path(AGENT_SITEMAP_PATH)
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _match_agent_action(sitemap: dict | None, method: str, url: str) -> dict | None:
    """按 sitemap 匹配请求的语义动作（url_pattern + method）；未匹配返回 None。"""
    if not sitemap:
        return None
    from urllib.parse import urlparse
    path = urlparse(url).path or "/"
    for act in sitemap.get("actions", []):
        pattern = act.get("url_pattern", "")
        # url_pattern 形如 "GET /api/docs/*"（方法 + 路径）；* 前缀通配
        parts = pattern.split(" ", 1)
        if len(parts) == 2 and parts[0] == method:
            p = parts[1]
            if p.endswith("*"):
                if path.startswith(p[:-1]):
                    return act
            elif path == p:
                return act
    return None


def _eval_agent_condition(action: dict | None, url: str) -> bool:
    """评估 sitemap 动作 condition（URL query 参数 vs value——operator 比较）。

    返回 True=条件超限（违反约束——标记可观测）；无 condition/参数缺失/
    格式无效 → False（保守不标记）。condition 定义允许值（lte=<= 等）。
    """
    if not action:
        return False
    cond = action.get("condition")
    if not cond:
        return False
    from urllib.parse import parse_qs, urlparse
    param = cond.get("param", "")
    operator = cond.get("operator", "lte")
    value = cond.get("value")
    if not param or value is None:
        return False
    vals = parse_qs(urlparse(url).query).get(param)
    if not vals:
        return False  # 参数缺失——保守不标记
    try:
        actual = float(vals[0])
        limit = float(value)
    except (TypeError, ValueError):
        return False  # 格式无效——保守不标记
    if operator == "lte":
        return actual > limit
    if operator == "gte":
        return actual < limit
    if operator == "eq":
        return actual != limit
    return False


def _apply_request_policy(window: Any, blocked: set | None = None,
                          shell: Any = None, api: Any = None) -> None:
    """统一请求策略管线（A 级落地，P0-①：DNT→威胁拦截统一回调链）。

    通过 pywebview request_sent 事件（底层 WebView2 WebResourceRequested）
    修改请求头。pywebview 6.x（已锁 6.2.1）**正式支持**该事件：回调接收
    Request 对象，`request.headers` 为字典，**变异后即用于请求**（官方
    语义，见 pywebview.flowrl.com/api window.events.request_sent）。

    统一回调链（一次请求走全量请求策略）：
    1. **DNT 注入**：do_not_track 开启时注入 `DNT: 1`（落地 A-①）；
    2. **威胁域名标记**：命中 threat_feed 黑名单的请求标记
       `X-Aegis-Threat: 1`（A-②，尽力而为的请求头标记——pywebview 6.x
       request_sent 仅能改请求头、不能拦截响应；**权威拦截仍在导航层**
       safe_url + host_is_blocked 实时判断）。

    blocked 为启动时黑名单快照（ThreatFeedUpdater.load_cached 一次），
    请求层标记尽力而为；导航层拦截用实时缓存（权威关口）。
    更旧版本不支持该事件/请求头修改时静默降级。
    """
    try:
        events = getattr(window, "events", None)
        if events is None:
            return
        if not hasattr(events, "request_sent"):
            return  # 版本不支持 → 静默降级

        def _on_request(request: Any) -> None:
            try:
                headers = getattr(request, "headers", None)
                if headers is None:
                    return
                headers["DNT"] = "1"  # 变异 headers 即生效（6.x 官方语义）
                # 威胁域名标记（尽力而为；命中黑名单 → 请求头标记）
                url = getattr(request, "url", "") or ""
                host = ""
                try:
                    from urllib.parse import urlparse
                    host = urlparse(url).hostname or ""
                except Exception:
                    host = ""
                # A4（final-development-checklist）：按来源动态 CoreWebView2Settings
                # （微软官方"Update settings based on the origin of the new page"）——
                # 非信任站点（远程网页）禁用 WebMessage 通道 + 脚本对话框；本地页面
                # 保持开启。js_api 桥不依赖 IsWebMessageEnabled（零功能影响）；设置
                # 幂等（每次请求按来源设置，下个导航生效——pywebview 无导航事件）。
                try:
                    core = shell.core(window) if shell is not None else None
                    settings = getattr(core, "Settings", None) if core is not None else None
                    if settings is not None:
                        remote = bool(host)  # host 非空 = 远程网页（非信任）
                        settings.IsWebMessageEnabled = not remote
                        settings.AreDefaultScriptDialogsEnabled = not remote
                except Exception:
                    pass  # 设置失败静默（版本不支持/属性缺失，不影响请求）
                if host and blocked:
                    from app.threat_feed import host_is_blocked
                    if host_is_blocked(host, blocked):
                        headers["X-Aegis-Threat"] = "1"
                        # 六维上下文记录增强（docs/threat-context-design.md 第 1 步）：
                        # method + request_type 推断（Content-Type/扩展名）入威胁日志，
                        # 可观测性增强——不改变拦截语义（政府级零风险门禁）
                        try:
                            from crash_reporter import log_event
                            method = getattr(request, "method", "") or "GET"
                            ctype = (headers.get("Content-Type") or "").lower()
                            path = url.split("?")[0].lower()
                            rtype = "other"
                            if "image" in ctype or path.endswith(
                                    (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico")):
                                rtype = "image"
                            elif "javascript" in ctype or path.endswith(".js"):
                                rtype = "script"
                            elif "html" in ctype or path.endswith(".html"):
                                rtype = "document"
                            log_event(
                                f"[threat] 请求头标记威胁域名: {url} "
                                f"(method={method}, type={rtype})"
                            )
                        except Exception:
                            pass
                # C2 阶段 A（ceLLMate 借鉴）：Agent 会话活跃时应用白名单域策略
                # （agent-browser domain allowlist 模式——防 Agent 数据外泄到
                # 非白名单域；标记 + 日志可观测，不改变拦截语义——零风险）
                try:
                    import time
                    session_active = (
                        api is not None
                        and (getattr(api, "_agent_session", None) or 0.0)
                        and time.time() - (getattr(api, "_agent_session", None) or 0.0) < 60
                    )
                    if session_active and host and host not in AGENT_ALLOWED_HOSTS:
                        headers["X-Aegis-Agent-Blocked"] = "1"
                        try:
                            from crash_reporter import log_event
                            log_event(f"[agent] Agent 请求非白名单域: {url}")
                        except Exception:
                            pass
                except Exception:
                    pass  # Agent 策略失败静默（不影响请求）
                # C2 阶段 B（ceLLMate sitemap）：Agent 会话活跃时按 sitemap
                # 识别语义动作（url_pattern+method 匹配）——高风险/未登记动作
                # 标记 + 日志（可观测不拦截——零风险；sitemap 未配置时跳过）
                try:
                    sitemap = _load_agent_sitemap()
                    if session_active and sitemap and host in sitemap.get("domain", ""):
                        method = getattr(request, "method", "") or "GET"
                        action = _match_agent_action(sitemap, method, url)
                        from crash_reporter import log_event
                        if action:
                            if action.get("risk") == "high":
                                headers["X-Aegis-Agent-Action"] = "high"
                                log_event(
                                    f"[agent] Agent 高风险动作: {action.get('semantic')} {url}"
                                )
                            # C2C（ceLLMate Cond 谓词 + 掘金预算）：condition 动态
                            # 策略评估（金额阈值等——URL query 参数 vs value）
                            if _eval_agent_condition(action, url):
                                headers["X-Aegis-Agent-Condition"] = "exceeded"
                                log_event(
                                    f"[agent] Agent 条件超限: {action.get('semantic')} {url}"
                                )
                        else:
                            headers["X-Aegis-Agent-Action"] = "unregistered"
                            log_event(f"[agent] Agent 未登记动作: {url}")
                except Exception:
                    pass  # sitemap 策略失败静默（不影响请求）
            except Exception:
                pass  # 单个请求修改失败不影响其他请求

        events.request_sent += _on_request
    except Exception:
        pass  # 事件绑定失败静默，不影响浏览


def _apply_disk_cache_limit(window: Any, cache_mb: int = 0) -> None:
    """注入 --disk-cache-size 限制磁盘缓存（方向④-P2，尽力而为）。

    调研（微软 Q&A）：大缓存会拖慢冷启动；`--disk-cache-size` 可限制
    EBWebView 用户数据目录膨胀。经 CoreWebView2EnvironmentOptions.
    AdditionalBrowserArguments 注入（pywebview 底层对象，探测+静默）。
    cache_mb<=0 表示不限制（默认，保持现状）。
    """
    if cache_mb <= 0:
        return  # 未配置缓存上限 → 不注入，保持默认
    try:
        gui = getattr(window, "gui", None)
        webview_ctrl = getattr(gui, "webview", None)
        core = getattr(webview_ctrl, "CoreWebView2", None)
        env = getattr(core, "Environment", None)
        options = getattr(env, "Options", None)
        if options is None or not hasattr(options, "AdditionalBrowserArguments"):
            return  # API 未暴露 → 静默
        current = str(getattr(options, "AdditionalBrowserArguments", "") or "")
        flag = f"--disk-cache-size={int(cache_mb) * 1024 * 1024}"
        if flag not in current:
            options.AdditionalBrowserArguments = current + " " + flag
    except Exception:
        pass  # 注入失败静默，不影响浏览


def _warmup_webview2(window: Any) -> None:
    """启动预热 WebView2（方向④-P2，尽力而为、静默降级）。

    调研（微软官方 + issue #1629）：WebView2 冷启动需拉起浏览器/渲染/
    GPU 进程并建磁盘缓存，可致数秒延迟。启动早期触碰底层对象触发
    Environment/Core 初始化，使后续首次导航更快；失败静默不影响浏览。
    """
    try:
        gui = getattr(window, "gui", None)
        webview_ctrl = getattr(gui, "webview", None)
        core = getattr(webview_ctrl, "CoreWebView2", None)
        if core is None:
            return
        _ = getattr(core, "BrowserProcessId", 0)  # 触碰触发初始化
        env = getattr(core, "Environment", None)
        _ = getattr(env, "BrowserVersionString", "") if env else ""
    except Exception:
        pass  # 预热失败静默，不影响浏览


def _apply_webview2_settings(window: Any) -> None:
    """按官方安全清单限制 WebView2 功能（方向①-S4，探测+静默降级）。

    微软《Develop secure WebView2 apps》建议：不期望页面访问的功能一律
    关闭，避免 web 内容越权访问宿主资源：
    - AreHostObjectsAllowed=false       （禁止页面访问宿主对象）
    - IsWebMessageEnabled=false         （禁止页面主动发 web 消息）
    - IsScriptEnabled=false             （纯静态页场景；Aegis 需 JS 保持 true）
    - AreDefaultScriptDialogsEnabled=false（禁止 alert/prompt 弹窗）

    Aegis 前端依赖 JS（工具栏注入），故 IsScriptEnabled 保持 true；
    其余按清单收紧。所有属性 hasattr 探测，缺失/失败静默降级。
    """
    try:
        gui = getattr(window, "gui", None)
        webview_ctrl = getattr(gui, "webview", None)
        core = getattr(webview_ctrl, "CoreWebView2", None)
        settings = getattr(core, "Settings", None)
        if settings is None:
            return  # 旧 Runtime / API 未暴露 → 静默
        # 收紧项：宿主对象访问 / web 消息 / 脚本弹窗（JS 本体保持启用）
        if hasattr(settings, "AreHostObjectsAllowed"):
            settings.AreHostObjectsAllowed = False
        if hasattr(settings, "IsWebMessageEnabled"):
            settings.IsWebMessageEnabled = False
        if hasattr(settings, "AreDefaultScriptDialogsEnabled"):
            settings.AreDefaultScriptDialogsEnabled = False
    except Exception:
        pass  # 收紧失败静默，不影响浏览


def _apply_enhanced_security(window: Any, mode: str = "auto") -> None:
    """启用 WebView2 Enhanced Security Mode（落地②，支持三模式决策）。

    背景（2026-08 调研）：微软将 EnhancedSecurityModeLevel 更名为
    EnhancedSecurityModeState（Disabled/Enabled），新 API 为 profile 级
    （COM ICoreWebView2ExperimentalProfile17，Runtime 151+ 可用）。
    pywebview 未封装该 API，但底层 WinForms WebView2 控件可通过
    window.gui.webview.CoreWebView2.Profile 访问。

    策略（对应 config.security_enhanced_mode）：
    - auto（默认）：探测到 EnhancedSecurityModeState 才启用；
    - on：强制启用（无 API 时静默降级，不影响浏览启动）；
    - off：显式跳过（兼容依赖 JIT/WASM 的老站点）。
    per-origin 例外（config.security_esm_exceptions）依赖实验
    Origin Configuration API，探测到才应用；任何失败静默降级。
    """
    try:
        if mode == "off":
            return  # 显式关闭：不启用 ESM
        gui = getattr(window, "gui", None)
        webview_ctrl = getattr(gui, "webview", None)
        core = getattr(webview_ctrl, "CoreWebView2", None)
        profile = getattr(core, "Profile", None)
        if profile is None or not hasattr(profile, "EnhancedSecurityModeState"):
            return  # Runtime 过旧/API 未暴露 → 静默降级
        # Enabled=1（对应枚举 CoreWebView2EnhancedSecurityModeState.Enabled）
        profile.EnhancedSecurityModeState = 1
    except Exception:
        pass  # 启用失败静默，不影响浏览


def _apply_esm_exceptions(window: Any, exceptions_json: str = "") -> None:
    """ESM per-origin 例外接入（方向①-P1，Origin Configuration API）。

    调研（微软 specs/TrustedOriginSetting.md）：ICoreWebView2Profile3 提供
    CreateOriginFeatureSetting / SetOriginFeatures / GetEffectiveFeaturesForOrigin；
    特性枚举含 EnhancedSecurityMode。对受信任源（如政府内网 OA）关闭 ESM
    （Disabled），其余源保持 profile 级启用。

    实现（探测+静默）：
    - exceptions_json 为空或非 JSON 数组 → 直接返回（无例外配置）
    - 探测 profile 是否暴露 SetOriginFeatures/CreateOriginFeatureSetting
      （staging/实验 API，hasattr 兜底；未暴露则静默放弃）
    - 对每个例外源创建 EnhancedSecurityMode=Disabled 设置并应用
    任何失败静默降级，绝不影响浏览启动。
    """
    if not exceptions_json:
        return
    try:
        import json as _json
        origins = _json.loads(exceptions_json)
        if not isinstance(origins, list) or not origins:
            return  # 非数组/空 → 无例外
        origins = [str(o) for o in origins if isinstance(o, str) and o]
        if not origins:
            return
        gui = getattr(window, "gui", None)
        webview_ctrl = getattr(gui, "webview", None)
        core = getattr(webview_ctrl, "CoreWebView2", None)
        profile = getattr(core, "Profile", None)
        if profile is None:
            return
        if not (hasattr(profile, "SetOriginFeatures")
                and hasattr(profile, "CreateOriginFeatureSetting")):
            return  # 实验 API 未暴露（旧 Runtime）→ 静默放弃
        # 创建 EnhancedSecurityMode=Disabled 设置（枚举值：2=Disabled）
        setting = profile.CreateOriginFeatureSetting(
            1,  # COREWEBVIEW2_ORIGIN_FEATURE_ENHANCED_SECURITY_MODE
            2,  # COREWEBVIEW2_ORIGIN_FEATURE_STATE_DISABLED
        )
        if setting is None:
            return
        profile.SetOriginFeatures(len(origins), origins, [setting])
    except Exception:
        pass  # 例外配置失败静默，不影响浏览


def main() -> int:
    # 壳抽象（禁止被困原则落地，2026-08-15）：通过 shell_adapter 获取
    # 壳实现，默认 pywebview；pytauri 为可插拔实现（壳可随时替换，
    # 业务 api_bridge/nav_queue 等零影响）。pywebview 为运行时依赖。
    from app.shell_adapter import get_shell
    shell = get_shell()  # 默认 pywebview（配置/参数可切 pytauri）

    # 关键：新窗口请求（target=_blank 链接）必须在当前窗口打开，
    # 而不是交给系统默认浏览器（默认 True 会导致点百度热搜跳去谷歌浏览器）。
    try:
        shell.settings()['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False
    except Exception:
        pass

    # 崩溃报告收集器：任何线程未捕获异常 → 写入 crash_reports/（后台静默，绝不弹窗）
    try:
        from crash_reporter import install_crash_reporter
        data_dir0 = ""
        try:
            from app.paths import resolve_data_dir
            data_dir0 = resolve_data_dir()
        except Exception:
            pass
        install_crash_reporter(data_dir0 or None)
    except Exception:
        pass

    if "--smoke-test" in sys.argv:
        return _smoke_test(shell)

    api = Api()
    try:
        from app.bookmark_store import BookmarkStore
        from app.config import AppConfig
        from app.history_store import HistoryStore
        from app.paths import resolve_data_dir
        data_dir = resolve_data_dir()
        api._data_dir = data_dir
        api.bookmarks = BookmarkStore(data_dir)
        api.history = HistoryStore(data_dir)
        api.config = AppConfig.load(data_dir)
        if api.config is not None:
            eng = getattr(api.config, "engine", "") or ""
            if eng in SEARCH_ENGINES:
                api._engine = eng
    except Exception:
        pass  # 书签/历史/配置不可用时降级为纯浏览

    window = shell.create_window(
        api,
        START_URL,
        title="Aegis 安全浏览器",
        width=1280,
        height=820,
        min_size=(900, 600),
    )
    if window is None:
        print("[fatal] create_window 返回 None，无法启动", file=sys.stderr)
        return 1
    api.window = window      # 创建后再绑定 window 引用，供桥方法调用

    # 落地②：WebView2 兼容性探测（Runtime 版本 + 关键 API 可用性，
    # 写日志供监控/排障；Evergreen 2 周更新节奏下用于回归基线）
    try:
        from app.webview2_probe import (
            build_probe_report,
            compare_baseline,
            probe_performance,
            watch_runtime_update,
        )
        report = build_probe_report(window)
        from crash_reporter import log_event
        log_event(f"[probe] {report}")
        # 落地④：性能基线快照 + 与上次基线对比（内存显著变化告警）
        try:
            tab_count = len(api.get_tabs().get("tabs", []))
            perf = probe_performance(window, tab_count=tab_count)
            log_event(f"[perf] {perf}")
            import json as _json

            from app.paths import resolve_data_dir
            baseline_path = os.path.join(
                resolve_data_dir(), "webview2_perf_baseline.json")
            baseline: dict = {}
            try:
                with open(baseline_path, "r", encoding="utf-8") as f:
                    baseline = _json.load(f) or {}
            except (OSError, ValueError):
                baseline = {}
            diff = compare_baseline(perf, baseline)
            if diff.get("significant") or diff.get("gpu_changed"):
                log_event(f"[perf] 基线差异: {diff}")
            # 更新基线（当前快照作为下次对比基准）
            try:
                with open(baseline_path, "w", encoding="utf-8") as f:
                    _json.dump(perf, f, ensure_ascii=False)
            except OSError:
                pass
        except Exception:
            pass  # 性能监控失败静默，不影响浏览
        # 版本对比监控：Evergreen 后台下载新 Runtime 后，提示采用新版本
        # （持续运行的应用会继续用旧版，有安全影响；监听事件记录日志）
        def _on_new_runtime(ver: str) -> None:
            try:
                log_event(f"[probe] 新 WebView2 Runtime 可用: {ver or 'unknown'}"
                          f"（当前 {report.get('runtime_version', '')}，建议重启采用）")
            except Exception:
                pass
        watch_runtime_update(window, on_new_version=_on_new_runtime)
        # 方向④-P2：24h 周期性能复采样（慢速内存泄漏趋势；守护线程，
        # 复用 compare_baseline，显著变化/GPU 切换写日志）
        try:
            from app.paths import resolve_data_dir
            from app.webview2_probe import start_periodic_sampling
            start_periodic_sampling(
                window,
                tab_count_fn=lambda: len(api.get_tabs().get("tabs", [])),
                interval_hours=24.0,
                baseline_path=os.path.join(
                    resolve_data_dir(), "webview2_perf_baseline.json"),
            )
        except Exception:
            pass  # 复采样启动失败静默，不影响浏览
    except Exception:
        pass  # 探测失败静默，不影响浏览

    # 落地③：WebView2 进程崩溃监听（ProcessFailed.CrashReport，2026-07 新 API）。
    # 渲染/GPU 子进程崩溃时 Python 主进程仍存活，借此把崩溃详情写入
    # crash_reports/events.log（异常码/故障模块/偏移/崩溃 ID）；CrashReport
    # 为 None（正常退出/外部 kill/启动失败/挂起）时仅记录 kind 概要。
    try:
        gui = getattr(window, "gui", None)
        webview_ctrl = getattr(gui, "webview", None)
        core = getattr(webview_ctrl, "CoreWebView2", None)
        if core is not None and hasattr(core, "ProcessFailed"):
            def _on_process_failed(sender=None, args=None) -> None:
                try:
                    from crash_reporter import log_webview2_crash
                    kind = ""
                    report = None
                    if args is not None:
                        kind = str(getattr(args, "ProcessFailedKind", "") or "")
                        report = getattr(args, "CrashReport", None)
                    log_webview2_crash(report, kind=kind)
                except Exception:
                    pass  # 记录失败静默，不影响浏览
            core.ProcessFailed += _on_process_failed
    except Exception:
        pass  # 事件绑定失败静默，不影响浏览

    # 方向①-S4：按官方安全清单限制 WebView2 功能（宿主对象/web 消息/弹窗，
    # 探测+静默；JS 保持启用以支撑工具栏注入）
    try:
        _apply_webview2_settings(window)
    except Exception:
        pass  # 收紧失败静默，不影响浏览

    # 方向④-P2：启动预热 WebView2（触碰底层对象触发初始化，缩短首次导航）
    try:
        _warmup_webview2(window)
    except Exception:
        pass  # 预热失败静默，不影响浏览

    # 方向④-P2：--disk-cache-size 注入（config.http_cache_mb 限制磁盘缓存）
    try:
        cache_mb = 0
        if api.config is not None:
            cache_mb = int(getattr(api.config, "http_cache_mb", 0) or 0)
        _apply_disk_cache_limit(window, cache_mb=cache_mb)
    except Exception:
        pass  # 注入失败静默，不影响浏览

    # 落地②：WebView2 Enhanced Security Mode（Runtime 151+ 可用；
    # 读取 config.security_enhanced_mode：auto=探测启用/on=强制/off=关闭；
    # 尽力而为，API 未暴露/失败时静默降级，不影响浏览）
    try:
        esm_mode = "auto"
        try:
            esm_mode = str(getattr(api.config, "security_enhanced_mode", "auto")
                           or "auto")
            if esm_mode not in ("auto", "on", "off"):
                esm_mode = "auto"
        except Exception:
            esm_mode = "auto"
        _apply_enhanced_security(window, mode=esm_mode)
        # 方向①-P1：ESM per-origin 例外（受信任源关闭 ESM；实验 API 探测+静默）
        try:
            _apply_esm_exceptions(
                window,
                str(getattr(api.config, "security_esm_exceptions", "") or ""),
            )
        except Exception:
            pass  # 例外配置失败静默，不影响浏览
    except Exception:
        pass  # 启用失败静默，不影响浏览

    # A-① + A-② 统一请求策略管线（A 级落地，P0-①）：
    # request_sent 回调统一执行全量请求策略（DNT 注入 + 威胁域名头标记）。
    # blocked 为启动时黑名单快照（请求层标记尽力而为）；权威拦截仍在
    # 导航层（safe_url + host_is_blocked 实时）。pywebview 不支持该事件
    # 时静默降级，不影响浏览。
    try:
        from app.config import AppConfig
        dnt_enabled = True  # 默认开启（与 config 默认值一致）
        if api.config is not None:
            dnt_enabled = bool(getattr(api.config, "do_not_track", True))
        if dnt_enabled:
            blocked: set = set()
            try:
                from app.paths import resolve_data_dir
                from app.threat_feed import ThreatFeedUpdater
                blocked = ThreatFeedUpdater(resolve_data_dir()).load_cached()
            except Exception:
                blocked = set()  # 黑名单快照失败 → 仅 DNT，不影响浏览
            _apply_request_policy(window, blocked=blocked, shell=shell, api=api)
    except Exception:
        pass  # 统一策略绑定失败静默，不影响浏览

    # S5：Windows 11 系统级亚克力/Mica 背景（尽力而为，失败静默降级到 CSS 毛玻璃）
    try:
        from app.backdrop import apply_system_backdrop
        apply_system_backdrop(window, material="mica")
    except Exception:
        pass  # 非 Win11 / DWM 不可用等情形下静默，不影响浏览

    window.events.loaded += lambda: on_loaded(window, api)

    # 看门狗：监控导航线程健康度，疑似卡死 → dump 线程栈 + 自动重启导航线程
    try:
        from crash_reporter import dump_threads_to_report, log_event, start_watchdog
        healthy = {
            "recover_count": 0,
            "last_dump": 0.0,
        }

        def _watch() -> bool:
            ok = api._nav_healthy()
            if not ok:
                api._recover_nav()
                healthy["recover_count"] += 1
                # 立即 dump 线程栈（限流：60 秒内最多一次），
                # 确保"未响应"现场必然留下报告 —— 不能等 bad 计数（恢复太快会重置它）
                import time as _t
                now = _t.monotonic()
                if now - healthy["last_dump"] > 60.0:
                    healthy["last_dump"] = now
                    try:
                        dump_threads_to_report("看门狗：导航线程疑似卡死")
                    except Exception:
                        pass
                try:
                    log_event(f"看门狗：导航线程疑似卡死，已重启（第 {healthy['recover_count']} 次）")
                except Exception:
                    pass
            return ok

        start_watchdog(_watch, interval=2.0, timeout=4.0, name="nav")
    except Exception:
        pass  # 看门狗不可用时降级

    # 启动壳事件循环（经壳抽象——pywebview/pytauri 可插拔）
    shell.start()
    return 0


def _smoke_test(shell: Any) -> int:
    """无窗口自检：确认系统内核 WebView 能创建并加载真实页面后自动退出。"""
    import time

    result: dict[str, Any] = {"loaded": False, "url": None, "err": ""}
    w = shell.create_window(
        None, START_URL, title="Aegis smoke", width=500, height=360, hidden=True,
    )
    if w is None:
        print("[smoke] FAIL — create_window 返回 None")
        return 1

    def on_loaded() -> None:
        result["loaded"] = True
        try:
            result["url"] = w.get_current_url()
        except Exception as e:
            result["err"] = repr(e)
        for ww in shell.windows():
            try:
                ww.destroy()
            except Exception:
                pass

    w.events.loaded += on_loaded

    def fallback() -> None:
        time.sleep(10)
        if not result["loaded"]:
            result["err"] = "loaded 事件 10 秒内未触发"
            for ww in shell.windows():
                try:
                    ww.destroy()
                except Exception:
                    pass

    threading.Timer(1.0, fallback).start()
    shell.start()
    if result.get("loaded"):
        print(f"[smoke] OK — 系统内核 WebView 可用（loaded: {result.get('url')!r}）")
        return 0
    print(f"[smoke] FAIL — {result.get('err') or 'unknown'}")
    return 1


if __name__ == "__main__":
    import threading

    sys.exit(main())
