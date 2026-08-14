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
# 工具定义（白名单）。name → (描述, 参数 schema, 处理函数)
# 处理函数签名：fn(api, **kwargs) -> Any
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
    if not isinstance(idx, int) or idx < 0:
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
    return api.get_tabs()


def _t_get_search_engine(api, **kw):
    return api.get_search_engine()


# 工具白名单（唯一登记处；新增动作必须在此添加并写明用途）
_TOOLS: dict[str, dict[str, Any]] = {
    "navigate": {
        "description": "在当前标签导航到 URL 或搜索词",
        "parameters": {"text": {"type": "string", "required": True}},
        "fn": _t_navigate,
    },
    "new_tab": {
        "description": "新建标签页（可选 URL）",
        "parameters": {"url": {"type": "string", "required": False}},
        "fn": _t_new_tab,
    },
    "switch_tab": {
        "description": "切换到指定索引的标签",
        "parameters": {"index": {"type": "integer", "required": True}},
        "fn": _t_switch_tab,
    },
    "close_tab": {
        "description": "关闭指定索引的标签",
        "parameters": {"index": {"type": "integer", "required": True}},
        "fn": _t_close_tab,
    },
    "pin_tab": {
        "description": "固定指定索引的标签（置顶）",
        "parameters": {"index": {"type": "integer", "required": True}},
        "fn": _t_pin_tab,
    },
    "get_tabs": {
        "description": "返回全部标签快照（标题/URL/固定/分组）",
        "parameters": {},
        "fn": _t_get_tabs,
    },
    "get_search_engine": {
        "description": "返回当前搜索引擎与可选列表",
        "parameters": {},
        "fn": _t_get_search_engine,
    },
}


# --------------------------------------------------------------------------- #
# JSON-RPC 2.0 请求处理（纯函数）
# --------------------------------------------------------------------------- #
def handle_request(api: Any, raw: str | dict) -> dict:
    """处理一条 MCP 请求（JSON 字符串或 dict），返回响应 dict。

    - 非法 JSON / 非 JSON-RPC 对象 → 错误响应（id=None）
    - 未知 method → method not found
    - 工具执行异常 → 包装为错误响应，绝不抛出
    """
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
        try:
            result = tool["fn"](api, **arguments)
            return _ok(req_id, {"ok": True, "result": result})
        except (TypeError, ValueError) as exc:
            return _err(-32602, f"invalid arguments: {exc}")
        except Exception as exc:
            return _err(-32603, f"tool error: {exc}")

    return _err(-32601, f"method not found: {method}")
