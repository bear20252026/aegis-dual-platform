# Aegis Browser 专家评审包
# 生成时间: 2026-08-30 20:45 UTC
# 版本: 2.1.7
# 提交: 3a68c45 (fix(windows): ship wizard images beside iss (runner could not resolve ../legacy path))

## 包含内容（由 scripts/build_review_package.py 从规范源码自动生成）
- 源代码: Rust policy-core + Android + Windows Python + C# + contracts + shared 约束
- 文档: 安全审计报告 + 架构设计 + 开源浏览器调研 + 安全测试指南 + 红蓝对抗审计 + 审查记录
- CI/CD: GitHub Actions workflow（.github/workflows）
- 校验清单: manifest.json（每文件 SHA-256 / 体积）——评审包与规范源码同步的唯一来源

> 本目录为**生成物**，请勿手工编辑。手工编辑会被 `scripts/build_review_package.py --check`
> 在 Release 流水线拦截。改动请落地到规范源码（根目录 core/android/windows/legacy/contracts/shared/docs），
> 再运行 `python scripts/build_review_package.py --build` 重建。

## 安装包（构建产物，发布到 GitHub Release，不进源码树）
- Windows: AegisBrowser-Setup-2.1.6.exe (Inno Setup)
- Android: app-debug.apk (Gradle debug签名)

## SHA-256 校验值（安装包历史记录；源码校验见 manifest.json）
- AegisBrowser-Setup-2.1.6.exe: e213f4c9fd6f018aefb4ad3fee6571dabd105c72e773bbee0d64b2f603309b3a
- app-debug.apk: 0ba5e35476c674d065f330e7b69ea4404d59ac3d0920dd5ff5a7bc8bc710735c

## 架构概述
- 单路径数据流: Adapter -> Broker -> Decision -> Executor -> BrowserEvent -> BrowserSessionState -> ChromeUI
- 五项不变量: INV-01~05 全部满足
- 指纹防护管道: 9阶段独立可组合 (红蓝对抗加固版v3)
- 模块化: 单文件<=500行, 单文件单职责
- 代码体积优化: util.rs统一工具函数 + JsInjectable trait减少样板

## 最新改进 (6357b17) — 安全加固 + 评审包生成化
1. **bridge 守卫改为「调用方来源 allowlist」**（`core/rust-policy-core/src/bridge_guard.rs`）：
   由「目标域」改为按调用发起方 `window.location.origin` 判定，仅当页面自身 hostname 在
   allowlist 内才允许调用原生桥；拦截通道从仅 `fetch` 扩展为 `fetch` / `XMLHttpRequest` /
   `sendBeacon` / `WebSocket` 四种，Android 端（`SecureWebViewFactory.kt`）同步补齐。
2. **修复 Android 端 fail-open 漏洞**：旧 `BRIDGE_GUARD_JS` 模板的
   `const ALLOWED_HOSTS = "a","b";` 是语法错误，导致守卫实际空操作（默认放行）。
   已改为 `[$allowedHostsJson]` 数组展开，语义与 Rust 完全一致。
3. **非码本上限（fail-closed）**：`consume_nonce`/`BrowserPolicyBroker` 增加
   `MAX_CONSUMED_NONCES = 50_000` 上限（Rust 与 C# 对等），**永不淘汰旧非码**，只拒绝超限，
   防止状态无限膨胀。
4. **移除死字段** `SessionContext.policy_version`（校验用 broker 当前版本，字段从不被读取）。
5. **评审包生成化（本目录）**：`scripts/build_review_package.py` 从规范源码自动组装本包，
   消除手工复制的陈旧快照；Release 流水线用 `--check` 保证与源码同步。

## 历史改进记录 (e66d36e)
- 提取共享工具函数: hex_digit/extract_hostname/extract_host 统一到 util.rs
- JsInjectable trait: 统一JS注入接口 + JsPipeline管线组合 + js_iife!宏
- 消除3处重复代码: session_state/security_policy/adblock/space_routing

## 红蓝对抗安全加固 (97b2ef8)
- 红方攻击: 原型链检测/WebRTC IP泄露/AudioContext/Battery/Network/CSS字体枚举/时序攻击
- 蓝方修复: Object.getOwnPropertyDescriptor覆盖/RTCPeerConnection移除/API屏蔽/字体枚举防护/时序归一化

## 专家评审要点
1. 架构合理性: INV-01~05 是否满足?
2. 模块化: 是否做到单文件单职责?
3. 安全性: 红蓝对抗加固是否有效?
4. 代码质量: 是否有功能杂糅/代码异味?
5. 与2026行业标准对比: 与Clearcote/Brave/Mullvad的差距?
6. 代码体积: 是否存在冗余? 工具函数是否重复?
