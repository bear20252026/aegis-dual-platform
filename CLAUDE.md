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
node --test tests/ui-regression/*.test.mjs        # 单源首页 UI 回归
python -m pytest tests/python/ -q                 # 发布链离线单测

# —— Android 端（需 Android SDK）——
cd android
./gradlew.bat :app:testDebugUnitTest :webview-adapter:testDebugUnitTest
./gradlew.bat :app:ktlintCheck :app:detekt        # CI 以 ktlint/detekt 为准

# —— legacy 归档栈（只读冻结；仅 P0 安全披露通道评估，见 ADR-009 D4）——
cd legacy/windows-pywebview
ruff check . --exclude legacy --ignore RUF001,RUF003,E501,TRY300,TRY003,TRY301,RUF021,E402,I001
bandit -r app/ -q --skip B110,B404,B603,B607
mypy main_webview.py app/                # 全量目录口径（42 源文件 0 错误）
```

## 架构红线（改动前必须确认）

1. **Windows 正典栈是 `windows/src/Aegis.Windows.App`（C#/.NET 10 + WPF + WebView2，
   ADR-009 终局）**。`legacy/windows-pywebview/` 与 `legacy/ui/` 是只读归档：
   功能与安全修复一律不在该栈进行，P0 安全缺陷仅经安全披露通道评估
   （ADR-009 D4 冻结纪律），活跃代码**禁止** import 归档栈。
2. **单文件单职责**：新文件 ≤ 300 行；改造后 ≤ 500 行。不为拆而拆，也不堆职责。
3. **URL 安全关口**：所有导航入口（IPC/会话/书签/历史/拨号/命令行/地址栏）加载 URL 前必须经 `app/security.py` 的 `safe_url()`。
4. **js_api 白名单**：暴露给 JS 的方法必须加入 `app/api_bridge.py` 的 `_JS_EXPOSED`（防 pywebview 递归注入死锁）。
5. **窗口操作走 NavQueue**：js_api 回调线程**绝不**同步调用 load_url/evaluate_js，必须投递到 `app/nav_queue.py`。
6. **Android 安全配置**：每个 WebView 必须经 `SecureWebViewFactory` 创建（复用 BrowserEngine 安全边界）。
7. **凭据红线**：绝不把 token/密钥/证书/key.properties/.jks 写进代码或提交；安全敏感信息仅私密渠道传递。

## 代码检查清单（提交前自查）

- [ ] validate_release / ruff / bandit / mypy 全过（mypy 口径与 ci.yml 一致：mypy main_webview.py app/）
- [ ] 遵守单文件单职责与行数红线
- [ ] 涉及 URL/密码/下载/权限时说明了安全考虑
- [ ] 新增逻辑有对应自检（selftest_*.py）
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
- 快捷键/JS 注入改动后必须跑 `selftest_shell_toolbar.py`（校验占位符替换与 JSON 转义）。
