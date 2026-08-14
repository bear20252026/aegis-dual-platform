# -*- coding: utf-8 -*-
"""ima_client.py —— Aegis 调用 IMA（腾讯云知识库）OpenAPI 的纯 Python 封装。

设计要点（与项目 P0 规则一致）：
- 不重新实现签名/凭证逻辑，直接复用已通过安全审计的 node 脚本 `ima_api.cjs`
  （该脚本仅把凭证放进 `ima.qq.com` 的请求头，绝不外泄 ClientID / API Key）。
- 凭证读取位置：`~/.config/ima/client_id` 与 `~/.config/ima/api_key`
  （与 node 脚本一致；也可走环境变量 IMA_OPENAPI_CLIENTID / IMA_OPENAPI_APIKEY）。
- 所有写入笔记的内容在进入网络前，强制过滤本地图片引用（遵循 IMA 技能规则）。
- 全部为纯函数 + 一次 subprocess 调用，便于单元测试（mock subprocess 即可）。

依赖：仅标准库（os / json / subprocess / re / datetime）。
"""

import os
import re
import json
import subprocess
from datetime import datetime, timezone

# --------------------------------------------------------------------------- #
# 路径解析
# --------------------------------------------------------------------------- #
_HOME = os.path.expanduser("~")
SKILL_DIR = os.path.join(_HOME, ".workbuddy", "skills", "ima-skill")
IMA_API_JS = os.path.join(SKILL_DIR, "ima_api.cjs")
# 随安装包分发的 IMA 资源目录（含 ima_api.cjs / node.exe / meta.json）
_BUNDLED_IMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ima")
IMA_CONFIG_DIR = os.path.join(_HOME, ".config", "ima")
CLIENT_ID_FILE = os.path.join(IMA_CONFIG_DIR, "client_id")
API_KEY_FILE = os.path.join(IMA_CONFIG_DIR, "api_key")

# 写笔记接口仅支持 Markdown
_CONTENT_FORMAT = 1


def api_key_path():
    """返回应放置 IMA API Key 的文件路径（用于 UI 提示）。"""
    return API_KEY_FILE


def _managed_node():
    """返回本机受管 node 可执行文件路径（若存在）。"""
    cand = os.path.join(
        _HOME, ".workbuddy", "binaries", "node", "versions", "22.22.2", "node.exe"
    )
    return cand if os.path.isfile(cand) else None


def _resolve_ima_js():
    """优先使用随安装包内置的 ima_api.cjs，找不到再回退到技能目录。"""
    bundled = os.path.join(_BUNDLED_IMA_DIR, "ima_api.cjs")
    if os.path.isfile(bundled):
        return bundled
    return os.path.join(SKILL_DIR, "ima_api.cjs")


def find_node():
    """按优先级解析 node 运行时：内置 node > 环境变量 > 受管 node > PATH。"""
    # 1) 安装包内置的 node（与 ima_api.cjs 同目录分发）
    bundled = os.path.join(_BUNDLED_IMA_DIR, "node.exe")
    if os.path.isfile(bundled):
        return bundled
    # 2) 显式指定的 node
    env = os.environ.get("AEGIS_NODE")
    if env and os.path.isfile(env):
        return env
    # 3) 本机受管 node
    managed = _managed_node()
    if managed:
        return managed
    # 4) 系统 PATH
    import shutil
    on_path = shutil.which("node")
    if on_path:
        return on_path
    return None


# --------------------------------------------------------------------------- #
# 凭证诊断
# --------------------------------------------------------------------------- #
def is_configured():
    """是否已具备 IMA 调用所需的 client_id 与 api_key。"""
    return os.path.isfile(CLIENT_ID_FILE) and os.path.isfile(API_KEY_FILE)


def config_hint():
    """返回给用户看的中文配置指引。"""
    return (
        "尚未配置 IMA API Key。请到 https://ima.qq.com/agent-interface 获取，"
        "然后写入文件：\n" + API_KEY_FILE + "\n"
        "（Client ID 已就位；仅需补上 api_key 一行即可。）"
    )


# --------------------------------------------------------------------------- #
# 底层调用
# --------------------------------------------------------------------------- #
_CODE_MSG = {
    20002: "API Key 超过调用频率限制，请稍后重试。",
    20004: "API Key 鉴权失败，请检查密钥是否正确。",
    210001: "请求参数错误。",
    210004: "IMA 空间不足。",
    210005: "无权操作该笔记（非本人笔记）。",
    210006: "该笔记已被删除。",
    210008: "版本冲突，请重新获取笔记后再操作。",
    210009: "单篇笔记超过大小上限，请拆分后保存。",
    210035: "目标笔记本不存在。",
}


def _friendly(code, msg):
    if code in _CODE_MSG:
        return _CODE_MSG[code]
    if msg:
        return str(msg)
    return f"IMA 返回错误码 {code}"


def _call(api_path, body, timeout=30.0):
    """调用 node 脚本访问 IMA OpenAPI。

    返回 (ok: bool, data: dict|str|None, error: str|None)。
    ok=True 时 data 为解析后的响应体（已解开外层 data 信封）；
    ok=False 时 error 为可读中文错误。
    """
    node = find_node()
    if not node:
        return (False, None, "未找到 node 运行时，无法调用 IMA（请安装 Node.js）。")
    js = _resolve_ima_js()
    if not os.path.isfile(js):
        return (False, None, "未找到 IMA 脚本 ima_api.cjs，IMA 功能不可用。")

    try:
        # v2.1.2 修复：Windows 冻结版下 subprocess 会闪一下黑色控制台窗口，
        # 用 CREATE_NO_WINDOW 抑制（仅 win32 存在该常量）。
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            [node, js, api_path, json.dumps(body, ensure_ascii=False)],
            capture_output=True, text=True, cwd=os.path.dirname(js), timeout=timeout,
            **kwargs,
        )
    except subprocess.TimeoutExpired:
        return (False, None, "调用 IMA 超时，请检查网络后重试。")
    except Exception as exc:  # pragma: no cover - 运行环境异常
        return (False, None, f"调用 IMA 失败：{exc}")

    if proc.returncode != 0:
        err = _parse_stderr(proc.stderr)
        return (False, None, err)

    raw = (proc.stdout or "").strip()
    if not raw:
        return (True, None, None)
    try:
        data = json.loads(raw)
    except Exception:
        return (True, raw, None)

    # IMA 成功信封：{"code":0,"msg":"","data":{...}}
    if isinstance(data, dict):
        code = data.get("code")
        if code is not None and code not in (0, "0", None):
            return (False, data, _friendly(code, data.get("msg")))
        if "data" in data and isinstance(data["data"], (dict, list)):
            data = data["data"]
    return (True, data, None)


def _parse_stderr(stderr):
    """node 脚本出错时 stderr 为 JSON {code,msg}。"""
    stderr = (stderr or "").strip()
    if not stderr:
        return "调用 IMA 脚本失败（无错误详情）。"
    try:
        obj = json.loads(stderr)
        code = obj.get("code")
        msg = obj.get("msg") or obj.get("message")
        if code is not None and code < 0:
            # 脚本自身错误（如缺凭证），msg 已含指引
            return str(msg or "IMA 脚本错误")
        return _friendly(code, msg)
    except Exception:
        return stderr


# --------------------------------------------------------------------------- #
# 本地图片过滤（IMA 技能强制规则）
# --------------------------------------------------------------------------- #
_LOCAL_IMG_RE = re.compile(
    r"!\[[^\]]*\]\((?!https?://)([^)]+)\)", re.IGNORECASE
)


def strip_local_images(markdown):
    """移除 Markdown 中指向本地文件的图片引用，返回 (清洗后文本, 被移除的路径列表)。

    仅保留以 http(s):// 开头的网络图片；本地路径（file:///、C:\\、/Users/... 等）
    一律移除，避免把本地图片塞进不支持它的 IMA 笔记接口。
    """
    removed = []

    def _sub(m):
        removed.append(m.group(1))
        return ""

    clean = _LOCAL_IMG_RE.sub(_sub, markdown)
    return clean, removed


# --------------------------------------------------------------------------- #
# 高层 API
# --------------------------------------------------------------------------- #
def create_note(content, folder_id=None, timeout=30.0):
    """新建一篇 Markdown 笔记。返回 (ok, note_id|None, error|None)。"""
    if not is_configured():
        return (False, None, config_hint())
    content, _ = strip_local_images(content)
    if not content.strip():
        return (False, None, "笔记内容为空，无法保存。")
    body = {"content_format": _CONTENT_FORMAT, "content": content}
    if folder_id:
        body["folder_id"] = folder_id
    ok, data, err = _call("openapi/note/v1/import_doc", body, timeout)
    if not ok:
        return (False, None, err)
    note_id = (data or {}).get("note_id") if isinstance(data, dict) else None
    if not note_id:
        return (False, None, "IMA 未返回笔记 ID，保存可能未成功。")
    return (True, note_id, None)


def append_note(note_id, content, timeout=30.0):
    """向已有笔记追加 Markdown 内容。返回 (ok, error|None)。"""
    if not is_configured():
        return (False, config_hint())
    content, _ = strip_local_images(content)
    if not content.strip():
        return (False, "追加内容为空。")
    body = {"note_id": note_id, "content_format": _CONTENT_FORMAT, "content": content}
    ok, data, err = _call("openapi/note/v1/append_doc", body, timeout)
    if not ok:
        return (False, err)
    return (True, None)


def list_notes(limit=20, timeout=30.0):
    """列出近期笔记。返回 (ok, [ {note_id,title,summary,modify_time} ], error|None)。"""
    if not is_configured():
        return (False, [], config_hint())
    body = {"folder_id": "", "sort_type": 0, "cursor": "", "limit": limit}
    ok, data, err = _call("openapi/note/v1/list_note", body, timeout)
    if not ok:
        return (False, [], err)
    raw = (data or {}).get("note_book_list") or []
    items = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        mt = it.get("modify_time")
        items.append({
            "note_id": it.get("note_id"),
            "title": it.get("title") or "(无标题)",
            "summary": it.get("summary") or "",
            "modify_time": mt,
        })
    return (True, items, None)


def save_web_clip(title, url, body="", selected_text=None,
                  folder_id=None, timeout=30.0):
    """把"正在看的网页"整理成一篇 Markdown 笔记并保存到 IMA。

    - title: 网页标题
    - url:   网页地址
    - body:  用户自己写的备注
    - selected_text: 用户在网页中选中的原文（作为"网页摘录"）
    返回 (ok, note_id|None, error|None)。
    """
    if not title:
        title = "未命名网页剪辑"
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    parts = ["# " + title, "", f"> 来源：{url}", f"> 保存时间：{ts}", ""]
    if selected_text and selected_text.strip():
        parts.append("## 网页摘录")
        parts.append("")
        parts.append(selected_text.strip())
        parts.append("")
    if body and body.strip():
        parts.append("## 我的笔记")
        parts.append("")
        parts.append(body.strip())
        parts.append("")
    content = "\n".join(parts).strip() + "\n"
    return create_note(content, folder_id=folder_id, timeout=timeout)


# --------------------------------------------------------------------------- #
# 知识库（wiki）读取
# --------------------------------------------------------------------------- #
def list_knowledge_bases(limit=20, timeout=30.0):
    """列出用户有权限访问的全部知识库（含「昆仑山知识库」等）。

    用 get_addable_knowledge_base_list（无需关键词即可列出全部），
    而非 search_knowledge_base（那是带关键词的搜索，空词返回 0）。
    返回 (ok, [ {kb_id,name,description} ], error|None)。
    """
    if not is_configured():
        return (False, [], config_hint())
    # 该端点 limit 范围 1-50，做防御性收敛
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 50))
    body = {"cursor": "", "limit": limit}
    ok, data, err = _call(
        "openapi/wiki/v1/get_addable_knowledge_base_list", body, timeout)
    if not ok:
        return (False, [], err)
    raw = (data or {}).get("addable_knowledge_base_list") or []
    items = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        items.append({
            "kb_id": it.get("id"),
            "name": it.get("name") or "(未命名)",
            "description": "",
        })
    return (True, items, None)


def list_kb_docs(kb_id, folder_id=None, limit=20, timeout=30.0):
    """列出某知识库（或某文件夹）下的内容。

    用 get_knowledge_list；返回里文件与文件夹混排——有 folder_id 的是文件夹，
    有 media_id 的是文件。返回 (ok, [ {media_id,title,media_type,is_folder} ], error|None)。
    """
    if not is_configured():
        return (False, [], config_hint())
    if not kb_id:
        return (False, [], "缺少 knowledge_base_id。")
    # 该端点 limit 范围 1-50，做防御性收敛
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 50))
    body = {"knowledge_base_id": kb_id, "cursor": "", "limit": limit}
    if folder_id:
        body["folder_id"] = folder_id
    ok, data, err = _call("openapi/wiki/v1/get_knowledge_list", body, timeout)
    if not ok:
        return (False, [], err)
    raw = (data or {}).get("knowledge_list") or []
    items = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        folder_id_ = it.get("folder_id")
        items.append({
            "media_id": it.get("media_id"),
            "title": it.get("title") or it.get("name") or "(未命名)",
            "media_type": it.get("media_type"),
            "is_folder": bool(folder_id_),
        })
    return (True, items, None)


def get_kb_doc_content(media_id, timeout=30.0):
    """读取某条知识库条目的原文。

    返回 (ok, kind, payload, error)：
    - kind="url"  → payload 为可在浏览器打开的原文链接
    - kind="note" → payload 为笔记纯文本
    - ok=False    → error 为可读错误
    """
    if not is_configured():
        return (False, None, None, config_hint())
    if not media_id:
        return (False, None, None, "缺少 media_id。")
    ok, data, err = _call("openapi/wiki/v1/get_media_info",
                          {"media_id": media_id}, timeout)
    if not ok:
        return (False, None, None, err)
    data = data or {}
    # 笔记型：转调笔记接口取纯文本
    if data.get("media_type") == 11:
        nb_id = (data.get("notebook_ext_info") or {}).get("notebook_id")
        if nb_id:
            ok2, content, err2 = _call(
                "openapi/note/v1/get_doc_content",
                {"note_id": nb_id, "target_content_format": 0}, timeout)
            if ok2:
                txt = content if isinstance(content, str) \
                    else (content or {}).get("content")
                return (True, "note", txt, None)
            return (False, "note", None, err2)
    url = (data.get("url_info") or {}).get("url")
    if url:
        return (True, "url", url, None)
    return (False, None, None, "该条目无法直接读取原文，请在 IMA 客户端查看。")
