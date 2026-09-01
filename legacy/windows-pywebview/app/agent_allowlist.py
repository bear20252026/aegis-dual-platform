"""agent_allowlist.py —— Agent 网络白名单单源（P1-9，全量复审 2026-09-01）。

此前请求层（main_webview._apply_request_policy）与导航层
（tab_ops._is_navigation_safe_url）各自实现 AEGIS_AGENT_ALLOWED_HOSTS
解析：请求层还是模块级写死空集 `AGENT_ALLOWED_HOSTS: set[str] = set()`
（env 配置永不生效，语义漂移）。本模块收敛为单一事实来源：
env 解析（逗号分隔、小写化）+ 后缀匹配（等于白名单域或其子域）。
"""

from __future__ import annotations

import os


def load_agent_allowlist() -> set[str]:
    """读取 AEGIS_AGENT_ALLOWED_HOSTS（逗号分隔域名，小写化）。

    返回空集表示未配置——调用方语义：Agent 会话活跃时一律拒绝。
    """
    raw = os.environ.get("AEGIS_AGENT_ALLOWED_HOSTS", "").strip()
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def host_allowed(host: str, allow_hosts: set[str]) -> bool:
    """域名匹配：host 等于白名单域或为其子域（后缀匹配）。

    与原导航层实现逐字同语义（host == c or host.endswith("." + c)）。
    """
    host = (host or "").strip().lower()
    if not host:
        return False
    return any(host == c or host.endswith("." + c) for c in allow_hosts)
