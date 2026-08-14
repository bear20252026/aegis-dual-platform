# -*- coding: utf-8 -*-
"""ai_client.py —— 本地/兼容 OpenAI 的 AI 调用客户端（纯逻辑，可单测）。

统一服务于：
- 文本翻译（单条 / 批量双语对照）
- 网页总结
- 网页问答

设计原则（与项目 P0 规则一致）：
- 默认指向本地 AI App（Ollama / LM Studio 等）的 OpenAI 兼容端点：
  免费、本地运行、无需 API Key。
- 接口格式兼容 OpenAI /v1/chat/completions，因此也能切到任何兼容服务
  （如本地 Qwen 通过 Ollama 暴露的端点、或 Kimi/Moonshot 云端兼容端点）。
- 不引入额外依赖，仅用标准库 urllib；核心函数可离线单测。
"""

import json
import os
import re
import urllib.request
import urllib.error

_SYSTEM_TRANSLATE = (
    "你是一个翻译助手。只输出译文，不要解释、不要附加任何额外文字。"
    "保留原文的格式、换行与专有名词（专有名词可保留英文原文）。"
)

_SYSTEM_TRANSLATE_MANY = (
    "你是一个翻译助手。下面会给一组带编号的短文本，请逐条翻译。"
    "严格按照输入编号输出，每行格式为 \"编号. 译文\"，编号与译文之间用点分隔。"
    "不要合并行、不要添加序号以外的解释、不要漏行。"
)

_SYSTEM_SUMMARY = (
    "你是一个网页内容摘要助手。请用简体中文对给定的网页正文做简洁摘要，"
    "用 3-6 条要点列出核心信息，不要多余寒暄与解释。"
)

_SYSTEM_QA = (
    "你是网页问答助手。只根据下面提供的网页正文回答用户问题；"
    "若正文里找不到答案，如实说明\"正文中未提及\"。不要编造。"
)

# --------------------------------------------------------------------------- #
# 云端供应商密钥管理（本地 Ollama 无需密钥；DeepSeek/Kimi 等云端需 Bearer 密钥）
# 优先读环境变量，其次读 ~/.config/aegis/<provider>_key 文件（与 IMA 凭证同风格）。
# --------------------------------------------------------------------------- #
_AEGIS_CFG = os.path.join(os.path.expanduser("~"), ".config", "aegis")
_ENV_BY_PROVIDER = {
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "custom": "CUSTOM_API_KEY",
}


def _cred_path(provider: str) -> str:
    return os.path.join(_AEGIS_CFG, f"{provider}.key")


def load_api_key(provider: str) -> str:
    """读取某供应商的 API Key：环境变量优先，其次本地凭证文件。"""
    env = _ENV_BY_PROVIDER.get(provider)
    if env and os.environ.get(env):
        return os.environ[env].strip()
    p = _cred_path(provider)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""
    return ""


def save_api_key(provider: str, key: str) -> None:
    """把某供应商的 API Key 存到本地凭证文件。

    v2.1.2 修复：写入后收紧文件权限（POSIX 0600 / Windows 仅当前用户），
    与 sync.key 等凭证文件同策略，避免同机其他账户可读密钥。
    """
    key = (key or "").strip()
    os.makedirs(_AEGIS_CFG, exist_ok=True)
    with open(_cred_path(provider), "w", encoding="utf-8") as f:
        f.write(key)
    try:
        from .security import harden_perms
        harden_perms(_cred_path(provider))
    except Exception:
        pass


def _chat(endpoint: str, payload: dict, timeout: float = 60.0,
         api_key: str = None) -> str:
    """POST 到 OpenAI 兼容端点，返回原始响应文本；失败返回空串。

    api_key 非空时附带 ``Authorization: Bearer`` 头（云端服务如 DeepSeek 需要）。
    """
    if not endpoint:
        return ""
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(
        endpoint, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return ""


def parse_reply(raw: str) -> str:
    """从 OpenAI 兼容响应 JSON 中提取 message content；失败返回空串。"""
    try:
        data = json.loads(raw)
        return data["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError, TypeError):
        return ""


def _system_by_lang(target: str) -> str:
    return _SYSTEM_TRANSLATE_MANY + f"\n目标语言：{target}。"


def translate(text: str, endpoint: str, model: str, target: str,
              timeout: float = 30.0, api_key: str = None) -> str:
    """单条翻译（兼容旧接口）。成功返回译文；失败返回空串。"""
    if not text or not endpoint:
        return ""
    prompt = f"请把以下内容翻译为{target}：\n\n{text}"
    payload = {
        "model": model or "",
        "messages": [
            {"role": "system", "content": _SYSTEM_TRANSLATE},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "stream": False,
    }
    return parse_reply(_chat(endpoint, payload, timeout, api_key))


def _parse_numbered(raw: str, n: int):
    """解析 '1. 译文' 形式的编号输出，返回长度 n 的译文列表（1..n 对齐）。"""
    raw = (raw or "").strip()
    out = {}
    buf = {}
    cur = None
    pat = re.compile(r"^\s*(\d{1,4})[.、)]\s?(.*)$")
    for line in raw.split("\n"):
        m = pat.match(line)
        if m:
            if cur is not None:
                out[cur] = buf[cur].strip()
            cur = int(m.group(1))
            buf[cur] = m.group(2)
        else:
            if cur is not None:
                buf[cur] += "\n" + line
    if cur is not None:
        out[cur] = buf[cur].strip()
    return [out.get(i, "") for i in range(1, n + 1)]


def translate_many(texts: list, endpoint: str, model: str, target: str,
                   timeout: float = 60.0, chunk: int = 25,
                   api_key: str = None) -> list:
    """批量翻译（双语对照用）。texts 为字符串列表，返回等长译文列表。

    每 chunk 条合成一个编号 prompt，一次请求完成，显著降低本地 AI 调用次数。
    """
    if not texts or not endpoint:
        return [""] * len(texts)
    result = []
    for i in range(0, len(texts), chunk):
        group = texts[i:i + chunk]
        prompt = "下面每条带编号文本请逐条翻译：\n"
        for idx, t in enumerate(group, 1):
            prompt += f"{idx}. {t}\n"
        payload = {
            "model": model or "",
            "messages": [
                {"role": "system", "content": _system_by_lang(target)},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "stream": False,
        }
        raw = _chat(endpoint, payload, timeout, api_key)
        trs = _parse_numbered(parse_reply(raw), len(group))
        # 解析失败（空）时整组回退为逐条单翻，保证有产出
        if not any(trs):
            # v2.1.2 修复：回退逐条翻译同样要带上 api_key，
            # 云端供应商（DeepSeek/Kimi）此前在回退路径上必然 401。
            trs = [translate(t, endpoint, model, target, timeout,
                             api_key=api_key) for t in group]
        result.extend(trs)
    return result


def summarize(text: str, endpoint: str, model: str,
             lang: str = "中文", timeout: float = 90.0,
             api_key: str = None) -> str:
    """总结网页正文。返回摘要文本；失败返回空串。"""
    if not text or not endpoint:
        return ""
    payload = {
        "model": model or "",
        "messages": [
            {"role": "system", "content": _SYSTEM_SUMMARY},
            {"role": "user", "content": (text or "")[:12000]},
        ],
        "temperature": 0.4,
        "stream": False,
    }
    return parse_reply(_chat(endpoint, payload, timeout, api_key))


def ask(question: str, context: str, endpoint: str, model: str,
        timeout: float = 90.0, api_key: str = None) -> str:
    """基于网页正文回答用户问题。返回回答；失败返回空串。"""
    if not question or not endpoint:
        return ""
    user = ("网页正文：\n" + (context or "")[:12000]
            + "\n\n用户问题：" + question)
    payload = {
        "model": model or "",
        "messages": [
            {"role": "system", "content": _SYSTEM_QA},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
        "stream": False,
    }
    return parse_reply(_chat(endpoint, payload, timeout, api_key))
