"""atomic_write.py —— PY-278（2026-10-02 审计）：原子文本写单源。

背景：sync_versions（csproj 正则替换 / release.json 重写）与
write_checksum_json（SHA256SUMS.json 生成）此前直接 write_text——进程在
写入中途被杀（CI 取消/断电）会留下半截文件：版本声明写坏半个 csproj、
摘要清单写坏半个 JSON，且无任何原子性兜底。消费方（verify_versions /
verify_checksum_json）读到半截文件只报解析失败，无法区分「写入中断」
与「源文件损坏」。

实现：同目录 tempfile.mkstemp 临时文件 + os.replace 原子改名——读者要么
看到旧全文、要么看到新全文，永不读到半截（同目录保证与目标同卷，rename
原子）。显式 newline="n" 形参默认 LF（与 PY-232/PY-268 行尾锁定口径一致，
Windows 默认翻译 CRLF 是漂移源）。失败路径清理临时残骸（不遗留 .tmp）。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str, newline: str = "\n") -> None:
    """原子写 UTF-8 文本到 path（同目录临时文件 + os.replace）。

    - newline 默认 LF（见模块 docstring；调用方显式传 None 可恢复平台
      默认翻译，目前无此需求）；
    - 目标父目录须已存在（调用方各自 mkdir——本函数不隐式建目录，
      避免把路径拼写错误静默变成新目录树）；
    - 写入或改名失败时删除临时文件后重抛（不留半截残骸）。
    """
    # PY-278：mkstemp 同目录前缀+后缀——异常现场可辨认归属；O_EXCL 语义
    # 不覆盖既有临时文件
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        # 失败清理残骸后重抛（os.replace 已成功时 tmp 不存在——missing_ok
        # 兜底；不吞异常类型——调用方的 RuntimeError 语义不受影响。
        # ruff BLE001 不豁免：清理后无条件 raise 的 handler 不属盲捕）
        tmp.unlink(missing_ok=True)
        raise
