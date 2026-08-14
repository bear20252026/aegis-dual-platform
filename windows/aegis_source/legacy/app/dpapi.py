# -*- coding: utf-8 -*-
"""dpapi.py —— Windows DPAPI 数据保护（P1-5）。

在 Windows 上用 CryptProtectData/CryptUnprotectData 把敏感字节（如 Fernet
密钥）绑定到当前用户账户：密文离开本机/其他账户即无法解密，
密钥材料不再"裸存"。非 Windows 平台返回 None，调用方自行降级。

注：本机沙箱为 Linux，此模块经单元级注入测试验证逻辑；
Windows 真机路径使用微软文档标准 CryptProtectData 调用序列。
"""

import sys


def is_available() -> bool:
    return sys.platform == "win32"


def protect(data: bytes, entropy: bytes = b"") -> bytes:
    """DPAPI 加密；失败或非 Windows 返回 None。"""
    if not is_available():
        return None
    try:
        import ctypes
        import ctypes.wintypes as wt

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wt.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        blob_in = DATA_BLOB(len(data),
                            ctypes.create_string_buffer(data, len(data)))
        blob_ent = DATA_BLOB(len(entropy),
                             ctypes.create_string_buffer(entropy, len(entropy))) \
            if entropy else DATA_BLOB(0, None)
        blob_out = DATA_BLOB()

        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), "Aegis", ctypes.byref(blob_ent),
            None, None, 0x01, ctypes.byref(blob_out))  # 0x01 = 当前用户
        if not ok:
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return None


def unprotect(data: bytes, entropy: bytes = b"") -> bytes:
    """DPAPI 解密；失败返回 None。"""
    if not is_available():
        return None
    try:
        import ctypes
        import ctypes.wintypes as wt

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wt.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        blob_in = DATA_BLOB(len(data),
                            ctypes.create_string_buffer(data, len(data)))
        blob_ent = DATA_BLOB(len(entropy),
                             ctypes.create_string_buffer(entropy, len(entropy))) \
            if entropy else DATA_BLOB(0, None)
        blob_out = DATA_BLOB()

        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, ctypes.byref(blob_ent),
            None, None, 0x01, ctypes.byref(blob_out))
        if not ok:
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return None
