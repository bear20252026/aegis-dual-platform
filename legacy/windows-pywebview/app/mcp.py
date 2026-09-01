"""mcp.py —— 轻量 MCP（Model Context Protocol）接入（单文件单职责）。

职责：把 Aegis 的浏览器动作暴露为 MCP 工具，供外部 AI 代理通过标准
JSON-RPC 2.0 协议调用。借鉴 ShardBrowser 的 MCP 思路与 legacy
computer_use 的"动作白名单 × 权限"模式，但更轻量、纯逻辑可单测。

协议（MCP 工具调用的最小子集）：
- `tools/list`            → 返回可用工具清单（名称/描述/参数）
- `tools/call`            → 执行工具（name + arguments）→ 结果
- 请求为 JSON-RPC 2.0 对象：{jsonrpc:"2.0", id, method, params}

安全边界（P0）：
- **工具白名单**：只暴露经审核的动作（导航/标签/分组），绝不暴露
  任意 JS 执行或文件读写；新增工具必须显式登记在 _TOOLS。
- **参数强校验**：index/text 等参数做类型/范围校验，非法一律拒绝。
- **凭据隔离**：本模块不接收、不返回任何 token/密码/密钥。
- **纯函数**：不持有窗口引用，由调用方注入 api（鸭子类型），可单测。
"""

import json
import time
from dataclasses import dataclass
from typing import Any

# JSON-RPC 2.0 版本号
_JSONRPC = "2.0"


def _err(code: int, message: str) -> dict:
    """构造 JSON-RPC 错误响应。"""
    return {"jsonrpc": _JSONRPC, "id": None,
            "error": {"code": code, "message": message}}


def _ok(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": _JSONRPC, "id": req_id, "result": result}


# --------------------------------------------------------------------------- #
# P0-02 修复（专家审查 2026-08-16——MCP 信任边界重建——中英搜索对齐：
# MCP 2026-07-28 授权规范（scope 最小权限）+ 掘金五层权限模型）
# 认证上下文/资源预算/scope 映射——传输层验证 token 后构造，网页内容不得构造
# --------------------------------------------------------------------------- #
MAX_RAW_REQUEST_BYTES = 64 * 1024
MAX_ARGUMENT_BYTES = 16 * 1024
MAX_TEXT_BYTES = 8 * 1024
MAX_RESULT_BYTES = 64 * 1024


@dataclass(frozen=True)
class AgentAuthContext:
    """认证上下文（短期令牌/主体/scope/nonce——一次性消费——审计）。"""
    principal: str
    scopes: frozenset
    expires_at: float
    nonce: str

    def allows(self, scope: str) -> bool:
        return bool(self.principal) and time.time() < self.expires_at and scope in self.scopes


_TOOL_SCOPE = {
    "navigate": "navigation:write",
    "new_tab": "tabs:write",
    "switch_tab": "tabs:write",
    "close_tab": "tabs:write",
    "pin_tab": "tabs:write",
    "get_search_engine": "settings:read",
    "get_tabs": "tabs:sensitive_read",
}


def _json_within_limit(value: Any, limit: int) -> bool:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= limit
    except (TypeError, ValueError, OverflowError):
        return False


def _redact_url(value: Any) -> str:
    """P0-03 修复：敏感读取最小化——去除 query/fragment（防 query secret 泄露）。"""
    from urllib.parse import urlsplit, urlunsplit
    if not isinstance(value, str):
        return ""
    try:
        p = urlsplit(value)
        return urlunsplit((p.scheme, p.netloc, p.path, "", ""))
    except ValueError:
        return ""


# --------------------------------------------------------------------------- #
# 工具定义（白名单）。name → (描述, 参数 JSON Schema, 处理函数)
# 处理函数签名：fn(api, **kwargs) -> Any
# 参数 schema 为标准 JSON Schema（properties/required/description）——
# Agent 友好标准化（R2 + 2026 架构趋势审计第 8.5 节新方向）：
# LLM/Agent 可直接据 schema 生成参数，且与 OpenAPI/MCP inputSchema 兼容。
# --------------------------------------------------------------------------- #
def _t_navigate(api, **kw):
    text = kw.get("text", "")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text 必须为非空字符串")
    api.navigate(text)
    return {"ok": True}


def _t_new_tab(api, **kw):
    url = kw.get("url", "")
    api.new_tab(url if isinstance(url, str) else "")
    return {"ok": True}


def _t_switch_tab(api, **kw):
    idx = kw.get("index")
    if type(idx) is not int or idx < 0:  # P0-03：type(x) is int——True 不被当作索引
        raise ValueError("index 必须为非负整数")
    api.switch_tab(idx)
    return {"ok": True}


def _t_close_tab(api, **kw):
    idx = kw.get("index")
    if not isinstance(idx, int) or idx < 0:
        raise ValueError("index 必须为非负整数")
    api.close_tab(idx)
    return {"ok": True}


def _t_pin_tab(api, **kw):
    idx = kw.get("index")
    if not isinstance(idx, int) or idx < 0:
        raise ValueError("index 必须为非负整数")
    ok = api.pin_tab(idx)
    return {"ok": ok is not False}


def _t_get_tabs(api, **kw):
    # P0-03 修复：敏感读取最小化——去 query/fragment + 长度限制（防敏感泄露）
    snapshot = api.get_tabs()
    if not isinstance(snapshot, dict):
        return {"tabs": [], "current": -1}
    tabs = []
    for tab in snapshot.get("tabs", []):
        if isinstance(tab, dict):
            tabs.append({
                "title": str(tab.get("title", ""))[:256],
                "url": _redact_url(tab.get("url", "")),
                "pinned": bool(tab.get("pinned", False)),
                "group": str(tab.get("group", "默认"))[:64],
            })
    return {"tabs": tabs, "current": snapshot.get("current", -1)}


def _t_get_search_engine(api, **kw):
    return api.get_search_engine()


# 工具白名单（唯一登记处；新增动作必须在此添加并写明用途）。
# 参数 schema 为标准 JSON Schema（Agent 友好，tools/list 原样输出）。
_TOOLS: dict[str, dict[str, Any]] = {
    "navigate": {
        "description": "在当前标签导航到 URL 或搜索词",
        "parameters": {
            "type": "object",
            # A5（final-development-checklist）：OWASP 严格 JSON Schema——
            # additionalProperties:false 防参数注入（工具参数视为不受信）
            "additionalProperties": False,
            "properties": {
                "text": {
                    "type": "string",
                    "description": "URL 或搜索词（非空）",
                },
            },
            "required": ["text"],
        },
        # A5：返回网页内容——输出不可信标注（WebMCP untrustedContentHint）
        "untrusted_result": True,
        "fn": _t_navigate,
    },
    "new_tab": {
        "description": "新建标签页（可选 URL）",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "新标签的起始 URL（空则默认页）",
                },
            },
        },
        "fn": _t_new_tab,
    },
    "switch_tab": {
        "description": "切换到指定索引的标签",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "目标标签索引（非负）",
                },
            },
            "required": ["index"],
        },
        "fn": _t_switch_tab,
    },
    "close_tab": {
        "description": "关闭指定索引的标签",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "要关闭的标签索引（非负）",
                },
            },
            "required": ["index"],
        },
        "fn": _t_close_tab,
    },
    "pin_tab": {
        "description": "固定指定索引的标签（置顶）",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "要固定的标签索引（非负）",
                },
            },
            "required": ["index"],
        },
        "fn": _t_pin_tab,
    },
    "get_tabs": {
        "description": "返回全部标签快照（标题/URL/固定/分组）",
        "parameters": {"type": "object", "properties": {}},
        "fn": _t_get_tabs,
    },
    "get_search_engine": {
        "description": "返回当前搜索引擎与可选列表",
        "parameters": {"type": "object", "properties": {}},
        "fn": _t_get_search_engine,
    },
}


# --------------------------------------------------------------------------- #
# JSON-RPC 2.0 请求处理（纯函数）
# --------------------------------------------------------------------------- #
def handle_request(api: Any, raw: str | dict, auth: AgentAuthContext | None = None) -> dict:
    """处理一条 MCP 请求（JSON 字符串或 dict），返回响应 dict。

    P0-02 修复（专家审查）：未认证默认拒绝（auth None/过期/超长 raw）；
    工具调用前校验 scope/资源预算。传输层验证 token 后构造 auth。
    """
    # P0-02：未认证/过期/超长请求一律拒绝（默认关闭未认证 MCP）
    if auth is None or not auth.principal or time.time() >= auth.expires_at:
        return _err(-32001, "未认证或身份已过期")
    if isinstance(raw, str) and len(raw.encode("utf-8")) > MAX_RAW_REQUEST_BYTES:
        return _err(-32602, "请求过大")
    if isinstance(raw, str):
        try:
            req = json.loads(raw)
        except ValueError:
            return _err(-32700, "Parse error")
    else:
        req = raw
    if not isinstance(req, dict) or req.get("jsonrpc") != _JSONRPC:
        return _err(-32600, "Invalid Request")
    req_id = req.get("id")
    method = req.get("method", "")
    params = req.get("params") or {}

    if method == "tools/list":
        tools = []
        for name, t in _TOOLS.items():
            tools.append({
                "name": name,
                "description": t["description"],
                "parameters": t["parameters"],
                # A5（final-development-checklist）：readOnly 声明（WebMCP
                # readOnlyHint 理念——查询类工具只读，Agent 决策参考）
                "readOnly": name.startswith(("get_", "current_")),
            })
        return _ok(req_id, {"tools": tools})

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        tool = _TOOLS.get(name)
        if tool is None:
            return _err(-32602, f"unknown tool: {name}")
        if not isinstance(arguments, dict):
            return _err(-32602, "arguments 必须为对象")
        # P0-02 修复：scope 校验（未授权工具拒绝）+ 参数/文本资源预算
        need = _TOOL_SCOPE.get(name)
        if need and not auth.allows(need):
            return _err(-32003, f"无权限调用 {name}（需 scope: {need}）")
        if not _json_within_limit(arguments, MAX_ARGUMENT_BYTES):
            return _err(-32602, "arguments 过大")
        # P0-03 修复：additionalProperties:false 无条件执行（空 schema 也拒绝额外参数）
        declared = set((tool["parameters"].get("properties") or {}).keys())
        extra = set(arguments.keys()) - declared
        if extra:
            return _err(-32602, f"unexpected arguments: {sorted(extra)}")
        # A5：工具调用审计（OWASP MCP 安全——审计回放理念；可观测性，
        # 不改变功能；参数/结果摘要截断防敏感外泄）
        try:
            from app.event_log import log_event
            log_event(f"[mcp] 工具调用: {name} args={str(arguments)[:120]}")
        except Exception:
            pass
        try:
            # C2 阶段 A（ceLLMate 借鉴）：工具调用刷新 Agent 会话活跃标记
            # （请求管线据此对 Agent 请求应用白名单域策略）
            # P2 修复（全量复审 2026-09-01）：改在工具执行【前】刷新——原先
            # 在执行后刷新，长工具（>60s）执行期间活跃标记已过期，请求管线
            # 把 Agent 请求当普通请求处理，白名单域策略静默失效
            try:
                api._agent_session = time.time()  # 用顶部全局 import time
            except Exception:
                pass
            result = tool["fn"](api, **arguments)
            # A5：输出不可信标注（WebMCP untrustedContentHint 理念——
            # 工具结果可能含外部数据（网页内容等），标注 untrusted 帮助
            # Agent 提高警惕；不改变功能）
            resp: dict = {"ok": True, "result": result}
            if tool.get("untrusted_result"):
                resp["untrusted"] = True
            return _ok(req_id, resp)
        except (TypeError, ValueError) as exc:
            return _err(-32602, f"invalid arguments: {exc}")
        except Exception as exc:
            # MCP 补审（官方 schema 2026-07：工具错误应在 result 内
            # isError=true——非协议级错误——LLM 才能看到并 self-correct；
            # 协议级 -32603 仅用于"找不到工具/服务不支持"等异常条件）
            resp_err: dict = {"ok": False, "isError": True,
                              "error": f"tool error: {exc}"}
            if tool.get("untrusted_result"):
                resp_err["untrusted"] = True
            return _ok(req_id, resp_err)

    return _err(-32601, f"method not found: {method}")
