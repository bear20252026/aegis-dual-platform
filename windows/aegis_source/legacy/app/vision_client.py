"""vision_client.py —— AI 视觉能力客户端（设计文档 §4/§5）。

提供：
- capture_current_tab(tab)：把当前标签截图编码为 JPEG data URI（缩放+压缩）
- describe_screen(...)：模式 A，视觉模型看图回答
- decide_action(...)：模式 B，视觉模型输出动作 JSON（§7.2 协议）
- parse_action_json(raw)：容错解析 + 动作白名单/参数校验（纯函数，可离线单测）

双来源路由（§5）：
- ollama：本地 OpenAI 兼容端点（默认 http://localhost:11434/v1/chat/completions，
  Ollama 0.5+ 原生支持 image_url data URI）
- cloud/custom：任意 OpenAI 兼容云端端点（GPT-4o / Qwen-VL 等），
  密钥复用 app/ai_client.py 机制（环境变量优先，其次 ~/.config/aegis/<key>.key）

线程约定：本模块网络调用为阻塞式（urllib），**必须在后台线程执行**，
UI 层负责包 QThread/threading 并桥回主线程（与 threat_feed 同款模式）。
"""

import base64
import json
import urllib.error
import urllib.request

# 本地 Ollama 默认端点（OpenAI 兼容层）
OLLAMA_DEFAULT_ENDPOINT = "http://localhost:11434/v1/chat/completions"
OLLAMA_DEFAULT_MODEL = "qwen2.5-vl:7b"

# 动作白名单（§7.2）：GATE 与 computer_use 执行器共用。
# 前 7 项为页面动作；5 个原生动作（§7.7）由面板 Python 侧执行；
# qrcode/sms_input（§14）为人工介入请求动作（触发扫码/短信等待状态）。
ACTION_WHITELIST = {
    "click", "type", "scroll", "back", "wait", "done", "fail",
    "set_engine", "add_bookmark", "new_tab", "open_history", "open_settings",
    "qrcode", "sms_input",
}

# 浏览器原生动作（无 JS 模板，面板 Python 侧执行）
NATIVE_ACTIONS = frozenset(
    {"set_engine", "add_bookmark", "new_tab", "open_history", "open_settings"})

# R8：截图脱敏钩子（可选）。capture_current_tab 前对敏感区域（密码框/
# 手机号/卡号形态）模糊，降低画面内敏感信息进入模型的量。
# 默认无操作；接入方可用 set_redact_hook 提供（正则+几何双重探测）。
_REDACT_HOOK = None


def set_redact_hook(fn):
    """设置截图脱敏钩子 fn(QImage) -> QImage；传 None 表示不脱敏。"""
    global _REDACT_HOOK
    _REDACT_HOOK = fn


class VisionError(Exception):
    """视觉调用失败（携带用户可读信息）。"""


# --------------------------------------------------------------------------- #
# 截图管线（§4）
# --------------------------------------------------------------------------- #
def capture_current_tab(tab) -> str | None:
    """把当前标签页截图编码为 JPEG data URI；失败返回 None。

    等比缩放最长边至 vision_max_image_width、质量 vision_jpeg_quality——
    1080p 原图直接发送会超出多数 API 的体积上限。
    """
    if tab is None or not getattr(tab, "view", None):
        return None
    try:
        cfg = getattr(tab, "config", None)
        max_w = getattr(cfg, "vision_max_image_width", 1280) if cfg else 1280
        quality = getattr(cfg, "vision_jpeg_quality", 80) if cfg else 80
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        img = tab.view.grab().toImage()
        if img.isNull():
            return None
        w, h = img.width(), img.height()
        if w > max_w:
            img = img.scaledToWidth(max_w)
        elif h > max_w:
            img = img.scaledToHeight(max_w)
        # R8：可选脱敏钩子（敏感区域模糊）
        if _REDACT_HOOK is not None:
            try:
                img = _REDACT_HOOK(img)
            except Exception:
                pass
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "JPEG", quality)
        buf.close()
        b64 = base64.b64encode(bytes(ba)).decode("ascii")
        return "data:image/jpeg;base64," + b64
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 路由与请求（§5）
# --------------------------------------------------------------------------- #
def _load_api_key(provider: str) -> str:
    try:
        from .ai_client import load_api_key
        return load_api_key(provider)
    except Exception:
        return ""


def route(cfg) -> dict:
    """按 vision_provider 解析 (endpoint, model, api_key)。缺配置抛 VisionError。"""
    provider = getattr(cfg, "vision_provider", "ollama") if cfg else "ollama"
    if provider == "ollama":
        endpoint = (getattr(cfg, "vision_endpoint", "") or
                    OLLAMA_DEFAULT_ENDPOINT) if cfg else OLLAMA_DEFAULT_ENDPOINT
        model = (getattr(cfg, "vision_model", "") or
                 OLLAMA_DEFAULT_MODEL) if cfg else OLLAMA_DEFAULT_MODEL
        return {"endpoint": endpoint, "model": model, "api_key": ""}
    # cloud / custom
    endpoint = getattr(cfg, "vision_endpoint", "") if cfg else ""
    model = getattr(cfg, "vision_model", "") if cfg else ""
    key_provider = (getattr(cfg, "vision_cloud_key_provider", "vision")
                    if cfg else "vision")
    if not endpoint:
        raise VisionError("未配置视觉模型端点（设置 → AI → 视觉端点）")
    if not model:
        raise VisionError("未配置视觉模型名（如 gpt-4o / qwen-vl-max）")
    return {"endpoint": endpoint, "model": model,
            "api_key": _load_api_key(key_provider)}


def _chat(image_data_uri: str, prompt: str, system: str,
          temperature: float, timeout: float, cfg) -> str:
    """多模态请求：截图 + 文本 → 模型回复（阻塞式，调用方负责后台线程）。"""
    r = route(cfg)
    payload = {
        "model": r["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": image_data_uri}},
            ]},
        ],
        "temperature": temperature,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if r["api_key"]:
        headers["Authorization"] = "Bearer " + r["api_key"]
    req = urllib.request.Request(r["endpoint"], data=data,
                                 method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        raise VisionError(f"视觉模型调用失败：{e.reason or e}")
    except OSError as e:
        raise VisionError(f"视觉模型调用失败：{e}")
    return parse_reply(raw)


def parse_reply(raw: str) -> str:
    """从 OpenAI 兼容响应提取 message content；失败抛 VisionError。"""
    try:
        data = json.loads(raw or "")
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):   # 部分多模态响应 content 为数组
            parts = [c.get("text", "") for c in content
                     if isinstance(c, dict)]
            return "".join(parts).strip()
        return str(content).strip()
    except (ValueError, KeyError, IndexError, TypeError):
        raise VisionError("模型响应格式异常")


# --------------------------------------------------------------------------- #
# 模式 A：看图问答（§6）
# --------------------------------------------------------------------------- #
def describe_screen(image_data_uri: str, prompt: str, cfg,
                    timeout: float = 60.0) -> str:
    """视觉模型看图回答。失败抛 VisionError。"""
    if not image_data_uri or not prompt:
        raise VisionError("缺少截图或提问内容")
    system = ("你是一个视觉助手。根据用户提供的网页截图回答用户问题。"
              "描述要准确、简洁，只依据截图中的可见内容，不要臆测。")
    return _chat(image_data_uri, prompt, system, 0.3, timeout, cfg)


# --------------------------------------------------------------------------- #
# 模式 B：动作决策（§7.2）
# --------------------------------------------------------------------------- #
def decide_action(image_data_uri: str, task: str, step: int, cfg,
                  timeout: float = 30.0) -> dict:
    """输出严格 JSON 的动作指令。失败抛 VisionError。"""
    if not image_data_uri or not task:
        raise VisionError("缺少截图或任务描述")
    system = (
        "你是一个浏览器操控代理。根据当前网页截图，为完成任务输出下一步"
        "动作。只输出一个 JSON 对象，不要输出任何其他文字。动作格式：\n"
        '{"action":"click","x":<像素>,"y":<像素>,"reason":"..."}\n'
        '{"action":"type","x":<像素>,"y":<像素>,"text":"...","submit":true|false}\n'
        '{"action":"scroll","dx":0,"dy":<像素>}\n'
        '{"action":"back"}\n'
        '{"action":"wait","ms":<毫秒>}\n'
        '{"action":"done","summary":"..."}\n'
        '{"action":"fail","reason":"..."}\n'
        "规则：点击/输入坐标必须指向截图内的可见元素；"
        "无法继续时输出 fail 并说明原因；完成任务输出 done。"
    )
    prompt = f"任务：{task}\n当前是第 {step} 步。"
    raw = _chat(image_data_uri, prompt, system, 0.1, timeout, cfg)
    return parse_action_json(raw)


def parse_action_json(raw: str) -> dict:
    """容错解析模型输出的 JSON：去代码围栏、取首个合法 {...}。

    动作名白名单 + 参数类型/范围校验（GATE 前置），非法动作一律拒绝。
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            start = i
            break
    if start < 0:
        raise VisionError("模型未返回 JSON 动作")
    depth = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        raise VisionError("模型 JSON 不完整")
    try:
        action = json.loads(text[start:end + 1])
    except ValueError:
        raise VisionError("模型返回的 JSON 解析失败")
    if not isinstance(action, dict):
        raise VisionError("动作格式错误")
    name = action.get("action")
    if name not in ACTION_WHITELIST:
        raise VisionError(f"动作 {name!r} 不在白名单内")
    # 参数类型与范围校验
    if name in ("click", "type"):
        action["x"] = int(action.get("x", 0))
        action["y"] = int(action.get("y", 0))
        if name == "type":
            action["text"] = str(action.get("text", ""))
            action["submit"] = bool(action.get("submit", False))
    elif name == "scroll":
        action["dx"] = int(action.get("dx", 0))
        action["dy"] = int(action.get("dy", 0))
    elif name == "wait":
        action["ms"] = max(0, min(10000, int(action.get("ms", 500))))
    elif name == "set_engine":
        action["engine"] = str(action.get("engine", "")).strip()
    elif name == "add_bookmark":
        action["url"] = str(action.get("url", "")).strip()
        action["title"] = str(action.get("title", "") or action["url"])
    elif name == "new_tab":
        action["url"] = str(action.get("url", "")).strip()
    elif name in ("qrcode", "sms_input"):
        action["found"] = bool(action.get("found", True))
    return action
