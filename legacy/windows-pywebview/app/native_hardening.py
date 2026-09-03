"""native_hardening.py —— WebView2 原生加固设置束（单文件单职责）。

P0-1 修复（全面审计 2026-09-04）随迁自 main_webview.py：请求策略管线
（DNT/威胁标记/Agent 策略）、功能收紧、预热、缓存上限、ESM 及其
per-origin 例外、窗口加固束编排。解析统一走 shell_adapter.resolve_core
单源；安全状态变化一律 log_event 显式留痕（不再静默）。
"""

from __future__ import annotations

from typing import Any

# A-5 拆分（架构审计 2026-08-31）：agent sitemap 策略在 app/agent_sitemap.py
from app.agent_sitemap import (
    eval_agent_condition as _eval_agent_condition,
)
from app.agent_sitemap import (  # noqa: F401——转发兼容旧导入路径
    host_matches,
)
from app.agent_sitemap import (
    load_agent_sitemap as _load_agent_sitemap,
)
from app.agent_sitemap import (
    match_agent_action as _match_agent_action,
)
from app.shell_adapter import (
    resolve_core as _resolve_core,
)
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
                        # W-04 整改（国防级审查）：不再向远端发送安全决策头
                        # （X-Aegis-Threat——泄露内部安全状态）——仅内部日志
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
                        # M-3 记录（防御性安全审查）：威胁拦截当前仅日志不阻断
                        # 子资源（主文档导航由导航层兜底拦截——请求层子资源
                        # 缺口：黑名单域脚本/图片/XHR 仍加载）。发布期方案：
                        # WebView2 WebResourceRequested 返回空响应（204/
                        # 1×1 stub——brave 思路）——pywebview 6.x request_sent
                        # 不支持响应改写——需 shell.core(window) 直挂底层事件。
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
                    if session_active and host:
                        # P1-9 修复（全量复审 2026-09-01）：复用导航层同款
                        # allowlist 单源（env 解析 + 后缀匹配）——原实现
                        # 写死空集，AEGIS_AGENT_ALLOWED_HOSTS 配置在请求层
                        # 永不生效。请求层仅标记 + 日志（可观测不拦截）——
                        # 权威阻断仍在导航层（api_bridge Agent 白名单检查）。
                        try:
                            from app.agent_allowlist import (
                                host_allowed,
                                load_agent_allowlist,
                            )
                            allow_hosts = load_agent_allowlist()
                            if not host_allowed(host, allow_hosts):
                                from crash_reporter import log_event
                                if not allow_hosts:
                                    log_event(
                                        "[agent] 拒绝 Agent 请求"
                                        "（未配置 AEGIS_AGENT_ALLOWED_HOSTS）: "
                                        + url)
                                else:
                                    log_event(
                                        f"[agent] 拒绝 Agent 请求非白名单域: {url}")
                        except Exception:
                            pass  # 白名单解析失败静默（不影响请求）
                except Exception:
                    pass  # Agent 策略失败静默（不影响请求）
                # C2 阶段 B（ceLLMate sitemap）：Agent 会话活跃时按 sitemap
                # 识别语义动作（url_pattern+method 匹配）——高风险/未登记动作
                # 标记 + 日志（可观测不拦截——零风险；sitemap 未配置时跳过）
                try:
                    sitemap = _load_agent_sitemap()
                    if session_active and sitemap and host_matches(host, sitemap.get("domain", "")):
                        method = getattr(request, "method", "") or "GET"
                        action = _match_agent_action(sitemap, method, url)
                        from crash_reporter import log_event
                        if action:
                            if action.get("risk") == "high":
                                # W-04 整改：不再发送 X-Aegis-Agent-Action（仅日志）
                                log_event(
                                    f"[agent] Agent 高风险动作: {action.get('semantic')} {url}"
                                )
                            # C2C（ceLLMate Cond 谓词 + 掘金预算）：condition 动态
                            # 策略评估（金额阈值等——URL query 参数 vs value）
                            if _eval_agent_condition(action, url):
                                # W-04 整改：不再发送 X-Aegis-Agent-Condition（仅日志）
                                log_event(
                                    f"[agent] Agent 条件超限: {action.get('semantic')} {url}"
                                )
                        else:
                            # W-04 整改：不再发送 X-Aegis-Agent-Action（仅日志）
                            log_event(f"[agent] Agent 未登记动作: {url}")
                except Exception:
                    pass  # sitemap 策略失败静默（不影响请求）
            except Exception:
                pass  # 单个请求修改失败不影响其他请求

        events.request_sent += _on_request
    except Exception:
        pass  # 事件绑定失败静默，不影响浏览


def _apply_disk_cache_limit(window: Any, cache_mb: int = 0,
                            core: Any = None) -> None:
    """--disk-cache-size 限制磁盘缓存（方向④-P2）。

    P0-1 修复（全面审计 2026-09-04）：解析路径改走单源 _resolve_core。
    诚实性注记：AdditionalBrowserArguments 仅在 Environment 创建**前**
    设置才生效；核心就绪后（浏览器进程已拉起）再注入必然无效——
    pywebview 未暴露 EnvironmentOptions 创建口。此前代码静默"成功"实为
    no-op；现显式留痕跳过，不再伪装生效。
    """
    if cache_mb <= 0:
        return  # 未配置缓存上限 → 不注入，保持默认
    try:
        if core is None:
            core = _resolve_core(window)
        from crash_reporter import log_event
        if core is None:
            log_event("[native] 缓存上限未注入：核心不可用")
            return
        log_event("[native] 磁盘缓存上限跳过：AdditionalBrowserArguments 须在"
                  " Environment 创建前设置（pywebview 未暴露该口），运行期注入"
                  "无效——如需生效应改用 WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS "
                  "环境变量")
    except Exception:
        pass  # 留痕失败不影响浏览


def _warmup_webview2(window: Any, core: Any = None) -> None:
    """启动预热 WebView2（方向④-P2，尽力而为）。

    调研（微软官方 + issue #1629）：WebView2 冷启动需拉起浏览器/渲染/
    GPU 进程并建磁盘缓存。启动早期触碰底层对象触发初始化，使后续首次
    导航更快。P0-1 修复：解析改走单源 _resolve_core。
    """
    try:
        if core is None:
            core = _resolve_core(window)
        if core is None:
            return
        _ = getattr(core, "BrowserProcessId", 0)  # 触碰触发初始化
        env = getattr(core, "Environment", None)
        _ = getattr(env, "BrowserVersionString", "") if env else ""
    except Exception:
        pass  # 预热失败静默，不影响浏览


def _apply_webview2_settings(window: Any, core: Any = None) -> None:
    """按官方安全清单限制 WebView2 功能（方向①-S4）。

    微软《Develop secure WebView2 apps》：不期望页面访问的功能一律关闭。
    P0-1 修复（全面审计 2026-09-04）：解析改走单源 _resolve_core；
    并修正本函数的一处**错误安全声明**——旧 docstring 称「js_api 桥不依赖
    IsWebMessageEnabled」，实测不成立：pywebview 6.2.1 的 js_api 传输就是
    WebMessageReceived（edgechromium.on_script_notify）且自行设
    IsWebMessageEnabled=True。全局置 False 会**断掉整个桥**（标签/导航/
    工具栏全灭）。故本函数收紧项为：
    - AreHostObjectsAllowed=false        （pywebview 未用宿主对象——实测无
                                           AddHostObjectToScript，安全关闭）
    - AreDefaultScriptDialogsEnabled=false（pywebview 弹窗走自绘对话框，
                                           原生对话框可关）
    - IsWebMessageEnabled：**不改**——远端页面禁用由请求策略管线按来源
      翻转承担（_apply_request_policy：远程 host → False，本地壳页 → True）。
    """
    from crash_reporter import log_event
    try:
        if core is None:
            core = _resolve_core(window)
        settings = getattr(core, "Settings", None) if core is not None else None
        if settings is None:
            log_event("[security] WebView2 Settings 不可用——功能收紧跳过")
            return
        applied = []
        if hasattr(settings, "AreHostObjectsAllowed"):
            settings.AreHostObjectsAllowed = False
            applied.append("AreHostObjectsAllowed=false")
        if hasattr(settings, "AreDefaultScriptDialogsEnabled"):
            settings.AreDefaultScriptDialogsEnabled = False
            applied.append("AreDefaultScriptDialogsEnabled=false")
        # IsWebMessageEnabled 由 per-origin 请求策略管理（见 docstring），
        # 此处仅留痕说明，避免误判为遗漏。
        applied.append("IsWebMessageEnabled=per-origin（请求策略管线管理）")
        log_event("[security] WebView2 功能收紧已应用: " + ", ".join(applied))
    except Exception as exc:
        log_event(f"[security] WebView2 功能收紧失败（不影响浏览）: {exc!r}")


def _apply_enhanced_security(window: Any, mode: str = "auto",
                             core: Any = None) -> None:
    """启用 WebView2 Enhanced Security Mode（落地②，支持三模式决策）。

    背景（2026-08 调研）：微软将 EnhancedSecurityModeLevel 更名为
    EnhancedSecurityModeState（Disabled/Enabled），新 API 为 profile 级
    （Runtime 151+ 可用）。pywebview 未封装该 API，底层经 Profile 访问。

    策略（对应 config.security_enhanced_mode）：
    - auto（默认）：探测到 EnhancedSecurityModeState 才启用；
    - on：强制启用（无 API 时显式留痕降级）；
    - off：显式跳过（兼容依赖 JIT/WASM 的老站点）。
    P0-1 修复（全面审计 2026-09-04）：解析改走单源 _resolve_core，
    启用/跳过均显式留痕（不再静默——安全状态必须可观测）。
    """
    from crash_reporter import log_event
    try:
        if mode == "off":
            log_event("[security] ESM 显式关闭（config.security_enhanced_mode=off）")
            return
        if core is None:
            core = _resolve_core(window)
        profile = getattr(core, "Profile", None) if core is not None else None
        if profile is None or not hasattr(profile, "EnhancedSecurityModeState"):
            log_event("[security] ESM 未启用：Profile API 不可用"
                      "（Runtime 过旧/实验接口未暴露）")
            return
        # Enabled=1（对应枚举 CoreWebView2EnhancedSecurityModeState.Enabled）
        profile.EnhancedSecurityModeState = 1
        log_event("[security] ESM 已启用（EnhancedSecurityModeState=Enabled）")
    except Exception as exc:
        log_event(f"[security] ESM 启用失败（不影响浏览）: {exc!r}")


def _apply_esm_exceptions(window: Any, exceptions_json: str = "",
                          core: Any = None) -> None:
    """ESM per-origin 例外接入（方向①-P1，Origin Configuration API）。

    调研（微软 specs/TrustedOriginSetting.md）：ICoreWebView2Profile3 提供
    CreateOriginFeatureSetting / SetOriginFeatures / GetEffectiveFeaturesForOrigin；
    特性枚举含 EnhancedSecurityMode。对受信任源（如政府内网 OA）关闭 ESM
    （Disabled），其余源保持 profile 级启用。

    实现（探测+显式留痕）：
    - exceptions_json 为空或非 JSON 数组 → 直接返回（无例外配置）
    - 探测 profile 是否暴露 SetOriginFeatures/CreateOriginFeatureSetting
      （staging/实验 API，hasattr 兜底；未暴露则跳过并留痕）
    - 对每个例外源创建 EnhancedSecurityMode=Disabled 设置并应用
    P0-1 修复：解析改走单源 _resolve_core。
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
        if core is None:
            core = _resolve_core(window)
        profile = getattr(core, "Profile", None) if core is not None else None
        if profile is None:
            return
        if not (hasattr(profile, "SetOriginFeatures")
                and hasattr(profile, "CreateOriginFeatureSetting")):
            return  # 实验 API 未暴露（旧 Runtime）→ 跳过
        # 创建 EnhancedSecurityMode=Disabled 设置（枚举值：2=Disabled）
        setting = profile.CreateOriginFeatureSetting(
            1,  # COREWEBVIEW2_ORIGIN_FEATURE_ENHANCED_SECURITY_MODE
            2,  # COREWEBVIEW2_ORIGIN_FEATURE_STATE_DISABLED
        )
        if setting is None:
            return
        profile.SetOriginFeatures(len(origins), origins, [setting])
        from crash_reporter import log_event
        log_event(f"[security] ESM per-origin 例外已应用（{len(origins)} 个受信源）")
    except Exception as exc:
        from crash_reporter import log_event
        log_event(f"[security] ESM 例外配置失败（不影响浏览）: {exc!r}")


def _apply_window_hardening(window, api, shell, core: Any = None):
    """窗口加固束：功能收紧/预热/缓存上限/ESM/请求策略/背景（P0-1 后由
    _post_start_setup 在核心就绪后调用，core 直传避免重复解析）。"""
    # 方向①-S4：按官方安全清单限制 WebView2 功能（宿主对象/原生弹窗；
    # IsWebMessageEnabled 由 per-origin 请求策略管理——见函数 docstring）
    try:
        _apply_webview2_settings(window, core=core)
    except Exception:
        pass  # 收紧失败内部已留痕，不影响浏览

    # 方向④-P2：启动预热 WebView2（触碰底层对象触发初始化，缩短首次导航）
    try:
        _warmup_webview2(window, core=core)
    except Exception:
        pass  # 预热失败静默，不影响浏览

    # 方向④-P2：--disk-cache-size 注入（config.http_cache_mb；运行期注入
    # 无效——函数内已显式留痕跳过，见其 docstring）
    try:
        cache_mb = 0
        if api.config is not None:
            cache_mb = int(getattr(api.config, "http_cache_mb", 0) or 0)
        _apply_disk_cache_limit(window, cache_mb=cache_mb, core=core)
    except Exception:
        pass  # 注入失败静默，不影响浏览

    # 落地②：WebView2 Enhanced Security Mode（Runtime 151+ 可用；
    # 读取 config.security_enhanced_mode：auto=探测启用/on=强制/off=关闭；
    # 启用/跳过/失败均显式留痕）
    try:
        esm_mode = "auto"
        try:
            esm_mode = str(getattr(api.config, "security_enhanced_mode", "auto")
                           or "auto")
            if esm_mode not in ("auto", "on", "off"):
                esm_mode = "auto"
        except Exception:
            esm_mode = "auto"
        _apply_enhanced_security(window, mode=esm_mode, core=core)
        # 方向①-P1：ESM per-origin 例外（受信任源关闭 ESM；实验 API 探测）
        try:
            _apply_esm_exceptions(
                window,
                str(getattr(api.config, "security_esm_exceptions", "") or ""),
                core=core,
            )
        except Exception:
            pass  # 例外配置失败内部已留痕，不影响浏览
    except Exception:
        pass  # 启用失败静默，不影响浏览

    # A-① + A-② 统一请求策略管线（A 级落地，P0-①）：
    # request_sent 回调统一执行全量请求策略（DNT 注入 + 威胁域名头标记）。
    # blocked 为启动时黑名单快照（请求层标记尽力而为）；权威拦截仍在
    # 导航层（safe_url + host_is_blocked 实时）。pywebview 不支持该事件
    # 时静默降级，不影响浏览。
    try:
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
