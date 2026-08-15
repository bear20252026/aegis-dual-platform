# B1 混淆隔离架构设计（obfuscation-isolation-design）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> final-development-checklist B1（混淆隔离架构——用户核心关切：混淆与
> 源码完全隔离、随时可去掉、模块化架构）
> 依据：全球调研（中英全覆盖）——PyArmor 官方（master-obf 分支隔离/
> restrict_module=0/--obf-code=0）+ Nuitka 官方（--module 模块编译）+
> CSDN 分离结构（核心 Nuitka + 其余 PyArmor + 源码备份）+ PyArmor 中文
> 文档（RFT/BCC 模式/模块级代码清理）

---

## 〇、核心原则（用户要求）

1. **混淆与源码完全隔离**——发布产物（dist/master-obf 分支）与源码（src/master）物理分离
2. **随时可去掉混淆**——发布不用混淆工具即回纯源码分发（可逆保证）
3. **开发零影响**——开发流程（源码解释运行 + 门禁）不变；混淆/编译全在发布流水线内

## 一、架构（双分支隔离）

```
开发分支 master（现状不变）：源码解释运行 + 全绿门禁（selftest/ruff/mypy/bandit）
发布分支 master-obf（独立，混淆产物隔离）：
  ├─ 核心敏感模块（security/credential_guard/threat_feed/mcp）
  │   → Nuitka --module 编译（.pyd——编译级保护，难以反编译）
  ├─ 其余模块（api_bridge/shell_toolbar/nav_queue 等）
  │   → PyArmor 混淆（--enable-rft 源级 + --exclude 核心，避免双重处理）
  ├─ dist/ 产物目录与 src/ 源码物理隔离
  ├─ 原始源码备份（构建前快照——可逆保证）
  └─ build_release.py（两步自动化构建脚本）
可逆保证：master-obf 分支丢弃/重建即回纯源码分发（开发分支永远源码）
```

## 二、模块保护分级（Aegis 语境）

| 模块 | 级别 | 方式 |
|---|---|---|
| security / credential_guard / threat_feed / mcp | 🔴 核心（安全逻辑/凭据/威胁数据/Agent 桥） | **Nuitka 编译**（.pyd） |
| api_bridge / shell_adapter / nav_queue / shell_toolbar 等 | 🟡 业务 | PyArmor 混淆（--enable-rft） |
| config / paths / 静态资源 | 🟢 低敏 | 按需（可混淆/可不混淆） |

## 三、构建流程（build_release.py，两步自动化）

```bash
# 步骤 1：Nuitka 编译核心敏感模块
python -m nuitka --module app/security.py --output-dir=dist/core
python -m nuitka --module app/credential_guard.py --output-dir=dist/core
python -m nuitka --module app/threat_feed.py --output-dir=dist/core
python -m nuitka --module app/mcp.py --output-dir=dist/core

# 步骤 2：PyArmor 混淆其余模块（--exclude 核心，避免双重处理）
pyarmor gen --enable-rft --exclude "app/security" --exclude "app/credential_guard" \
  --exclude "app/threat_feed" --exclude "app/mcp" \
  -O dist/obfuscated app/ main_webview.py

# 集成：dist/ 组装（核心 .pyd + 混淆脚本 + sys.path 配置）
# 可逆：master-obf 分支可整体丢弃，重建即回源码分发
```

## 四、关键配置（调研确认）

| 配置 | 依据 |
|---|---|
| PyArmor `restrict_module=0` | 与 Nuitka/第三方库兼容（PyArmor 官方 2.10） |
| PyArmor `--obf-code=0`（RFT 模式） | 源级转换不破坏代码对象结构（第三方库兼容） |
| Nuitka `--include-package`（必要时） | 包嵌入（动态导入场景） |
| 非 trial 版 PyArmor | Nuitka 组合需 v9.0.8+（unauthorized use 修复） |
| 构建前源码快照 | CSDN 实践（保留原始源码备份——可逆保证） |

## 五、验证与门禁（不改变开发流程）

1. **开发零影响验证**：master 分支全程源码（门禁全绿）——混淆/编译仅 master-obf 发布流程
2. **可逆性验证**：master-obf 分支可丢弃（git branch -D master-obf 即回源码分发）——随时可去
3. **构建产物验证**：dist/ 运行 smoke-test + 全量回归（发布前）
4. **签名配合**（B2）：混淆/编译产物 + sigstore/代码签名（防 AV 误报 + 完整性）

## 六、结论

B1 混淆隔离架构满足用户核心关切：**混淆与源码完全隔离（双分支）+ 随时可去（分支可丢弃）+ 模块化（核心 Nuitka 编译/其余 PyArmor 混淆）+ 开发零影响（混淆全在发布流水线）**——设计先行完毕，待发布期实施（不触碰开发分支）。
