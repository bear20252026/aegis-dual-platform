"""agent_sitemap.py —— Agent sitemap 语义动作匹配（A-5 拆分，架构审计 2026-08-31）。

原寄生在 main_webview.py:36-111 的纯策略逻辑下沉至此（单文件单职责——
入口薄壳只做启动组装，不做策略匹配）。

C2 阶段 B（ceLLMate sitemap）：内网 Agent sitemap（JSON——语义动作
↔ HTTP 消息映射，见 docs/release/agent-sitemap.example.json；默认空=
未启用（仅阶段 A 域白名单）——内网运维按需配置）。
"""

from __future__ import annotations

AGENT_SITEMAP_PATH = ""


def load_agent_sitemap() -> dict | None:
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


def host_matches(host: str, configured: str) -> bool:
    """P0-03 修复（专家审查）：精确/子域边界匹配（替代 host in domain——
    防 portal.www.gov.cn 与 gov.cn 误配——DNS 边界后缀匹配）。"""
    h = (host or "").lower().rstrip(".")
    c = (configured or "").lower().rstrip(".")
    return bool(h and c) and (h == c or h.endswith("." + c))


def match_agent_action(sitemap: dict | None, method: str, url: str) -> dict | None:
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


def eval_agent_condition(action: dict | None, url: str) -> bool:
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
