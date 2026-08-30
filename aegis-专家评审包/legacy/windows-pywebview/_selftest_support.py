"""_selftest_support.py —— selftest 脚本共享支撑（M-6：消除五处复制的 check 样板）。

仅 selftest 脚本使用；不在 app/ 包内——避免被 PyInstaller
collect_submodules("app") 收进发布包。
"""
from typing import List

failures: List[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    """断言登记：失败记入 failures（脚本末尾统一判定退出码）。"""
    if not cond:
        failures.append(f"{name}: {detail}" if detail else name)
