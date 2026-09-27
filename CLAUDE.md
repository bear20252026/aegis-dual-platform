# CLAUDE.md — 项目协作指南（AI 助手 / 开发者共用）

本文件让 AI 助手（Claude Code / AtomCode 等）与人类开发者共享一致的上下文、命令与规范，避免"零全局意识"导致的错误改动。**任何 AI 辅助开发前请先通读本文件。**

## 项目一句话

Aegis 双端安全浏览器：Windows（C#/.NET 10 + 原生 WebView2——唯一正典栈）+ Android（Kotlin + Compose + System WebView），隐私与安全优先。

**Windows 终局口径（ADR-009；M1-M4 已全部落地——取代「迁移中」悬置）**：
- **C#/.NET 10（`windows/`）= 唯一 Windows 正典栈与唯一发布制品**（发布链
  单轨——PyInstaller 包已移除）；迁移路线图 M1-M4 完成，parity 清单
  （`docs/product/feature-parity-checklist.md`）代码项 100% 勾验；
- **`legacy/windows-pywebview/` = 只读归档**：**功能与安全修复一律不在该栈
  进行**；P0 安全缺陷仅经安全披露通道评估（ADR-009 D4 冻结纪律的归档终态）；
- `legacy/` 下的 Qt 与 `legacy/ui/` 为已归档死代码，禁止 import。

## 关键命令（必须先跑）

```bash
# —— Windows 正典栈（C#/.NET 10，ADR-009）——
cd windows
dotnet build src/Aegis.Windows.App/Aegis.Windows.App.csproj   # 0 警告 0 错误
dotnet test tests/Aegis.Windows.Core.Tests                    # 核心套件全绿
dotnet test tests/Aegis.Windows.Broker.Tests                  # Broker 套件全绿

# —— Rust 策略核心 ——
cd core/rust-policy-core
cargo test && cargo clippy --all-targets && cargo fmt --check  # 全绿+0 警告

# —— 契约/版本门禁（仓库根）——
python validate_release.py             # AST/JSON/XML 静态验证（版本校验在 scripts/verify_versions.py）
python scripts/verify_versions.py      # 版本单源一致性
python contracts/codegen/verify_bridge_guard.py   # Bridge 守卫单一事实源（改动守卫 JS 后必跑——ADR-007）
python scripts/verify_cross_end_lists.py          # 跨端清单对账（引擎/壁纸）
# SP-163（2026-09-26 审计）：node 21+ glob 展开（引号防 shell 抢先展开，
# Windows 本地与 CI 一致）——新增测试文件入目录即入门禁
node --test "tests/ui-regression/*.test.mjs"      # UI 回归
node shared/shell/snake.test.js                   # 贪吃蛇逻辑回归
python -m pytest tests/python/ -q                 # 发布链离线单测

# —— Android 端（需 Android SDK；四模块命令与 android-quality.yml 一致
#    ——WB-116 对齐 CI：app/broker/webview-adapter/contracts）——
cd android
./gradlew.bat :app:ktlintCheck :broker:ktlintCheck :webview-adapter:ktlintCheck :contracts:ktlintCheck
./gradlew.bat :app:detekt :broker:detekt :webview-adapter:detekt :contracts:detekt
./gradlew.bat :app:lintDebug
./gradlew.bat :broker:testDebugUnitTest :app:testDebugUnitTest :webview-adapter:testDebugUnitTest

# —— legacy 归档栈（只读冻结；仅 P0 安全披露通道评估，见 ADR-009 D4）——
# selftest_*.py 仅属该归档栈 P0 通道（WB-118）——正典栈不使用
cd legacy/windows-pywebview
ruff check . --exclude legacy           # SP-164：豁免清单已入本目录 ruff.toml 单源
bandit -r app/ -q --skip B110,B404,B603,B607
mypy main_webview.py app/                # 全量目录口径（42 源文件 0 错误）
```

## 架构红线（改动前必须确认）

1. **Windows 正典栈是 `windows/src/Aegis.Windows.App`（C#/.NET 10 + WPF + WebView2，
   ADR-009 终局）**。`legacy/windows-pywebview/` 与 `legacy/ui/` 是只读归档：
   功能与安全修复一律不在该栈进行，P0 安全缺陷仅经安全披露通道评估
   （ADR-009 D4 冻结纪律），活跃代码**禁止** import 归档栈。
2. **单文件单职责**：新文件 ≤ 300 行；改造后 ≤ 500 行。不为拆而拆，也不堆职责。
3. **URL 安全关口**：所有导航入口（地址栏/会话恢复/书签/历史/NTP 快捷入口/命令行）
   加载前必须经 `windows/src/Aegis.Windows.App/Core/UrlSafety.cs` 校验，并经
   `Broker/BrowserPolicyBroker.cs` 的 `EvaluateNavigation` → Rust 策略核心裁决
   （fail-closed——ADR-008）；Android 端对应 AegisWebViewClient → Broker 状态机。
   （WB-101，2026-09-26 审计——原归档栈 safe_url 表述废止）
4. **JS 暴露面收敛**：暴露给页面 JS 的桥能力仅限受信虚拟主机——`NtpAssets.IsTopLevelNtpDocument`
   顶层文档门禁（帧内嵌复用即拒）+ `Chrome/Ntp/NtpBridgeFactory.cs` 白名单服务登记；
   远程页面上 WebMessage 被宿主按来源关闭。新增桥方法必须经 Factory 显式登记，
   禁止动态反射暴露。（WB-101，2026-09-26 审计——原归档栈 _JS_EXPOSED 表述废止）
5. **导航/窗口操作走 WebView2 原生事件模型**：一切导航取消/放行必须挂在
   NavigationStarting / FrameNavigationStarting / NewWindowRequested 事件经
   Broker 真实取消（`WebView/HostWebView.cs` + `WebView/NavigationConfirmationGate.cs`），
   UI 线程（Dispatcher）串行——禁止绕过事件模型的跨线程 load/executeScript。
   （WB-101，2026-09-26 审计——原归档栈 NavQueue 表述废止）
6. **Android 安全配置**：每个 WebView 必须经 `SecureWebViewFactory` 创建（复用 BrowserEngine 安全边界）。
7. **凭据红线**：绝不把 token/密钥/证书/key.properties/.jks 写进代码或提交；安全敏感信息仅私密渠道传递。

## 代码检查清单（提交前自查）

- [ ] 改动所涉技术栈的正典门禁全过（WB-118，2026-09-26 审计——按端选择）：
  - C#：`dotnet build`（0 警告）+ `dotnet test` 两套件全绿
  - Rust：`cargo test && cargo clippy --all-targets && cargo fmt --check` 全绿
  - Android：四模块 ktlint + detekt + 单测 + `:app:lintDebug`（与 android-quality.yml 一致）
  - shared/shell：`node --test`（显式文件清单）+ `node shared/shell/snake.test.js` 全绿
  - scripts/contracts/release：`python validate_release.py` + `python scripts/verify_versions.py`
    + `python -m pytest tests/python/ -q`
- [ ] `selftest_*.py` 仅适用 legacy 归档栈 P0 评估通道（正典栈新增逻辑写对应端的
  C#/Kotlin/Node/pytest 测试——WB-118）
- [ ] 遵守单文件单职责与行数红线
- [ ] 涉及 URL/密码/下载/权限时说明了安全考虑
- [ ] 更新了 CHANGELOG.md
- [ ] 遵循 Conventional Commits（feat/fix/refactor/docs/chore/security）

## 常用文件地图

| 路径 | 职责 |
|---|---|
| `windows/src/Aegis.Windows.App/` | **Windows 正典栈**（Chrome UI / Core 数据层 / Broker 安全层 / WebView 封装） |
| `windows/tests/` | C# 两测试套件（Core.Tests / Broker.Tests） |
| `core/rust-policy-core/` | Rust 策略核心（唯一裁决源——ADR-008；FFI/C ABI/UniFFI） |
| `android/app/src/main/java/com/aegis/browser/` | Android 端（TabManager/SecureWebViewFactory/BrowserEngine） |
| `android/broker/` + `android/webview-adapter/` | Android 授权 Broker 与导航状态机 |
| `contracts/` | 契约单源（schemas/vectors/policy + codegen 生成器） |
| `shared/` | 双端单源（version.properties/release.json/shell 首页资产） |
| `docs/audit/` | 全仓审计报告（2026-09-07 200 项、2026-09-23 1115 项） |
| `legacy/windows-pywebview/` | 只读归档栈（ADR-009——禁止活跃改动，见红线 #1） |

## 常见陷阱

- `validate_release.py` 用相对路径定位项目根，**不要**改回硬编码绝对路径。
- `python` 命令在本机可能被 Store 别名拦截：用 `py` 或显式 Python 路径。
- Windows 上 Git Bash 的 `/tmp` 与 Python 路径不一致：别让 Python 读 Git Bash 的 /tmp 文件。
- 快捷键/JS 注入改动后必须跑 `selftest_shell_toolbar.py`——**仅限 legacy 归档栈
  P0 评估通道**（WB-118，2026-09-26 审计）；正典栈等价改动跑 C# 两套件 +
  `node --test` UI 回归。
