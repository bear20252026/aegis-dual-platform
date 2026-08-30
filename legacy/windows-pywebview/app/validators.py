"""validators.py —— JS API 参数类型校验工具（单一事实源）。

从 api_bridge.py 收敛（M-1：api_bridge↔tab_ops 循环依赖破除——
tab_ops 反向引 api_bridge 取 _to_nonneg_int 属环依赖，双端改引本模块）。
pywebview 传参可能是字符串/浮点/畸形值，统一在此收敛类型转换，
避免各方法重复 try/except 且行为不一致。
"""
from typing import Any


def to_int(value: Any, default: Any = None) -> Any:
    """安全转 int；失败返回 default。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_nonneg_int(value: Any, default: Any = None) -> Any:
    """转 int 且要求非负；否则返回 default（索引类参数专用）。"""
    n = to_int(value, None)
    if n is None or n < 0:
        return default
    return n


def to_str(value: Any, default: Any = None) -> Any:
    """确认是 str；None→default，非 str→default（文本类参数专用）。"""
    if value is None:
        return default
    return value if isinstance(value, str) else default


def host_of(url: str) -> str:
    """提取小写主机名（去尾部点）；URL 校验层通用——M-1 收敛三处重复提取。"""
    from urllib.parse import urlparse

    return (urlparse(url).hostname or "").lower().rstrip(".")
