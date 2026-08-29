"""bridge_hooks.py —— 页面加载完成回调（单文件单职责）。

从 api_bridge.py 拆出（结构审计）：on_loaded 是"页面加载完成后刷新
当前标签并注入工具栏"的独立职责，不依赖 Api 类内部状态（只通过参数
接收 window/api），与桥方法解耦。api_bridge re-export 保持兼容。
"""

from typing import Any

from .fingerprint_pipeline import (
    build_fingerprint_pipeline_js,
    build_link_intercept_js,
    generate_session_seed,
)
from .shell_toolbar import build_toolbar_js

# 指纹防护管道：每会话生成一次种子，所有页面共享
_session_seed = generate_session_seed()


def on_loaded(window: Any, api: Any) -> None:
    """每页加载完成后：刷新当前标签 url/title，并注入工具栏（含新标签页）。

    注意：该回调在 pywebview 的后台线程中执行；本函数自身绝不抛异常。
    get_current_url 属于只读查询（winforms 后端线程安全），可直接调用；
    注入（evaluate_js）统一走 api._eval 投递到导航线程执行。
    """
    if window is None or api is None:
        return
    try:
        url = window.get_current_url() or ""
    except Exception:
        url = ""
    api._update_current(url)
    try:
        # 注入指纹防护 9 阶段管道（参照 Rust fingerprint_pipeline + Android FINGERPRINT_SHIELD_JS）
        fp_js = build_fingerprint_pipeline_js(_session_seed)
        api._eval(fp_js)
    except Exception:
        pass  # 页面不允许注入时静默降级
    try:
        # FIX-4: 使用独立的链接拦截函数（不再内联 javascript: URL 放行逻辑）
        link_js = build_link_intercept_js()
        api._eval(link_js)
    except Exception:
        pass  # 页面不允许注入时静默降级
    try:
        # 内嵌标签数据 → 单次注入，零 HTTP 往返。
        kb = None  # None = 默认表 DEFAULT_KEYBINDINGS
        try:
            cfg = getattr(api, "config", None)
            raw = getattr(cfg, "keybindings_json", "") if cfg else ""
            if raw:
                import json as _json
                parsed = _json.loads(raw)
                if isinstance(parsed, dict):
                    kb = {k: str(v)[:1] for k, v in parsed.items()
                          if isinstance(v, str) and v}
        except Exception:
            kb = None  # 用户配置解析失败时静默回退默认表
        # 标签位置：读取 config.tabs_position（top/left），默认 top
        tabs_pos = "top"
        # 影子字段接入：地址栏联想开关（config.search_suggestions，默认开）
        sugg_enabled = True
        try:
            cfg = getattr(api, "config", None)
            if cfg is not None:
                tp = getattr(cfg, "tabs_position", "top") or "top"
                if tp in ("top", "left"):
                    tabs_pos = tp
                sugg_enabled = bool(getattr(cfg, "search_suggestions", True))
        except Exception:
            tabs_pos = "top"
        # W-02（国防级审查）：工具栏注入脚本已最小化（B0-W-01 移除敏感
        # 方法——注入仅剩非敏感 UI 导航/标签操作）；原生受信 WebUI 迁移
        # 为发布期架构项（注入式 UI 与远程页面同 DOM 的彻底隔离）
        #
        # 标签条快照（CHANGELOG Planned：标签增强落地）：
        # - 受信本地页（host 为空——壳页/新标签页）：注入**脱敏快照**
        #   （title/pinned/group——无 URL；标签条渲染/拖拽/固定所需最小集）；
        # - 远程页面：维持 B0-W-01 空快照（同 DOM 注入模型下，URL/标题
        #   均可被页面 DOM 读取——零泄露）。
        snapshot: dict = {}
        try:
            from urllib.parse import urlparse
            page_host = (urlparse(url).hostname or "") if url else ""
            if not page_host:  # 本地受信页（file:/// 壳页等）
                raw = api._tabs_snapshot()
                snapshot = {
                    "tabs": [
                        {k: t.get(k) for k in ("title", "pinned", "group")}
                        for t in raw.get("tabs", [])
                    ],
                    "current": raw.get("current", 0),
                }
        except Exception:
            snapshot = {}  # 快照失败 → 空标签条（与 B0-W-01 行为一致）
        js = build_toolbar_js(url, snapshot,
                              keybindings=kb,
                              tabs_position=tabs_pos,
                              search_suggestions=sugg_enabled)
        api._eval(js)
    except Exception:
        pass  # 页面不允许注入（CSP 严格站点 / 空白页）时静默降级
