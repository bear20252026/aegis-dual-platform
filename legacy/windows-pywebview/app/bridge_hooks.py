"""bridge_hooks.py —— 页面加载完成回调（单文件单职责）。

从 api_bridge.py 拆出（结构审计）：on_loaded 是"页面加载完成后刷新
当前标签并注入工具栏"的独立职责，不依赖 Api 类内部状态（只通过参数
接收 window/api），与桥方法解耦。api_bridge re-export 保持兼容。
"""

from typing import Any

from .shell_toolbar import build_toolbar_js


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
        js = build_toolbar_js(url, {}, keybindings=kb,  # B0-W-01：不再传全量标签（敏感读取移除——标签列表 UI 降级；空 dict 匹配类型）
                              tabs_position=tabs_pos,
                              search_suggestions=sugg_enabled)
        api._eval(js)
    except Exception:
        pass  # 页面不允许注入（CSP 严格站点 / 空白页）时静默降级
