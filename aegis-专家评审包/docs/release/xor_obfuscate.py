#!/usr/bin/env python
"""xor_obfuscate.py —— 发布期 XOR 常量加固工具（第一项实施）。

发布期实施产物（docs/release/——不触碰开发分支）。
基于全球调研（wearecommunity.io XOR 实战指南 + Nuitka Commercial data-hiding
文档对照 + oxorany 理念）：
- Nuitka 免费版常量数据未混淆（strings 可提取——issue #556）；
- XOR 对称加密 + 密钥嵌入编译代码（Nuitka 编译后难以提取）——
  免费替代 Nuitka Commercial data-hiding 插件；
- Aegis 敏感常量建议环境变量（已实现——凭据外部化）；本工具用于
  保护代码内必须存在的常量/数据文件（发布期加密）。

用法（发布期）：
    python docs/release/xor_obfuscate.py encrypt <file>          # 加密数据文件 → .enc
    python docs/release/xor_obfuscate.py decrypt <file.enc>      # 解密（运行期加载）
    # 密钥嵌入：发布脚本将 _KEY 常量写入 Nuitka 编译模块（编译后难提取）
"""

import base64
import sys
from pathlib import Path

# 32 字节密钥（发布期生成/轮换；嵌入 Nuitka 编译模块——编译后难以提取；
# 注意：本文件仅为发布期工具，密钥应在发布环境生成并嵌入编译产物）
_KEY = b"aegis-xor-32byte-key-2026!!"  # 占位——发布流程生成/轮换
_EXT = ".enc"


def xor_transform(data: bytes) -> bytes:
    """XOR 变换（对称——同函数加解密），密钥循环。"""
    key = _KEY
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def encrypt_file(path: Path) -> Path:
    """加密数据文件 → <name>.enc（base64 编码输出）。"""
    out = path.with_suffix(path.suffix + _EXT)
    out.write_bytes(base64.b64encode(xor_transform(path.read_bytes())))
    print(f"==> 已加密: {path} → {out}")
    return out


def decrypt_file(path: Path) -> bytes:
    """解密 .enc 文件（运行期加载——嵌入编译模块的 _KEY 解密）。"""
    return xor_transform(base64.b64decode(path.read_bytes()))


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    cmd, target = sys.argv[1], Path(sys.argv[2])
    if cmd == "encrypt":
        encrypt_file(target)
    elif cmd == "decrypt":
        data = decrypt_file(target)
        print(f"==> 已解密: {target}（{len(data)} 字节）")
        sys.stdout.buffer.write(data)
    else:
        print(f"未知命令: {cmd}（可选 encrypt/decrypt）")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
