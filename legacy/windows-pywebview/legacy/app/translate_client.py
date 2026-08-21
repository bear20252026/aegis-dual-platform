"""translate_client.py —— 本地/在线翻译客户端（OpenAI 兼容接口，纯逻辑可测）。

设计原则：
- 默认指向本地 AI App（Ollama / LM Studio 等）的 OpenAI 兼容端点：
  免费、本地运行、无需 API Key。
- 接口格式兼容 OpenAI /v1/chat/completions，因此也能切到任何兼容服务。
- 不引入额外依赖，仅用标准库 urllib；核心函数可离线单测。
"""

import json
import urllib.error
import urllib.request

_SYSTEM = (
    "你是一个翻译助手。只输出译文，不要解释、不要附加任何额外文字。"
    "保留原文的格式、换行与专有名词（专有名词可保留英文原文）。"
)


def build_payload(text: str, model: str, target: str) -> dict:
    """构造 OpenAI 兼容的 chat/completions 请求体。"""
    prompt = f"请把以下内容翻译为{target}：\n\n{text}"
    return {
        "model": model or "",
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "stream": False,
    }


def parse_reply(raw: str) -> str:
    """从 OpenAI 兼容响应 JSON 中提取译文；失败返回空串。"""
    try:
        data = json.loads(raw)
        return data["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError, TypeError):
        return ""


def translate(text: str, endpoint: str, model: str, target: str,
              timeout: float = 30.0) -> str:
    """同步翻译。成功返回译文；失败/超时返回空串（由调用方提示）。"""
    if not text or not endpoint:
        return ""
    payload = build_payload(text, model, target)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=data, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return parse_reply(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return ""
