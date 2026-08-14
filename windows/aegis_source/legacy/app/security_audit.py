# -*- coding: utf-8 -*-
"""security_audit.py —— R7 结构化安全审计日志（JSON Lines，本地）。

事件类型（枚举）：
  ipc_denied / sb_blocked / cert_denied / cert_override /
  l3_credential_access / download_danger_confirmed / update_rejected
每条记录：时间戳 / 事件 / 目标域名（不含完整 URL 路径）/ 决策。
- 不采集浏览 URL 全文（隐私优先）；
- 不上传任何数据；
- 保留 90 天后由调用方滚动清理（滚动逻辑随调用点维护）。
"""

import json
import os
import time

# 事件类型常量
IPC_DENIED = "ipc_denied"
SB_BLOCKED = "sb_blocked"
CERT_DENIED = "cert_denied"
CERT_OVERRIDE = "cert_override"
L3_CREDENTIAL_ACCESS = "l3_credential_access"
DOWNLOAD_DANGER_CONFIRMED = "download_danger_confirmed"
UPDATE_REJECTED = "update_rejected"


def _log_path(data_dir: str) -> str:
    return os.path.join(data_dir, "logs", "security.jsonl")


# v2.1.2 修复：审计日志此前无任何滚动——文档承诺"保留 90 天后滚动清理"
# 但滚动逻辑从未实现，日志会随使用时长无限增长。现做体积上限滚动：
# 超过 _MAX_BYTES 时轮转为 .1（覆盖上一轮），保持本地占用有界。
_MAX_BYTES = 1 << 20  # 1 MB


def _rotate_if_needed(path: str):
    try:
        if os.path.getsize(path) > _MAX_BYTES:
            old = path + ".1"
            if os.path.exists(old):
                os.remove(old)
            os.replace(path, old)
    except OSError:
        pass


def audit(data_dir: str, event: str, domain: str = "", decision: str = ""):
    """追加一条安全审计记录；失败静默（审计不得影响主流程）。"""
    if not data_dir:
        return
    try:
        os.makedirs(os.path.join(data_dir, "logs"), exist_ok=True)
        path = _log_path(data_dir)
        _rotate_if_needed(path)
        rec = {"ts": int(time.time()), "event": event,
               "domain": (domain or "")[:255], "decision": (decision or "")[:64]}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def recent(data_dir: str, n: int = 20) -> list:
    """读取最近 n 条审计记录（供安全仪表盘展示，本地）。"""
    if not data_dir:
        return []
    try:
        if not os.path.exists(_log_path(data_dir)):
            return []
        with open(_log_path(data_dir), "r", encoding="utf-8") as f:
            lines = f.readlines()
        out = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
    except Exception:
        return []
