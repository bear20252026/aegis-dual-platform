# CLAUDE.md — 项目协作指南（AI 助手 / 开发者共用）

本文件让 AI 助手（Claude Code / AtomCode 等）与人类开发者共享一致的上下文、命令与规范，避免"零全局意识"导致的错误改动。**任何 AI 辅助开发前请先通读本文件。**

## 项目一句话

Aegis 双端安全浏览器：Windows（C#/.NET 10 + 原生 WebView2——唯一正典栈）+ Android（Kotlin + Compose + System WebView），隐私与安全优先。

**Windows 终局口径（ADR-009；M1-M4 已全部落地——取代「迁移中」悬置）**：
- **C#/.NET 10（`windows/`）= 唯一 Windows 正典栈与唯一发布制品**（发布链
  单轨——PyInstaller 包已移除）；迁移路线图 M1-M4 完成，parity 清单
  （`docs/product/feature-parity-checklist.md`）代码项**除 1 项外**全部勾验——未落地项
  = WebView2 `NewBrowserVersionAvailable` Runtime 更新事件处理（无 `RuntimeUpdater.cs`，
  第八轮 B8 登记；「100%」曾是需要用户裁决的口径，现按实树更正）；
- **`legacy/windows-pywebview/` = 只读归档**：**功能与安全修复一律不在该栈
  进行**；P0 安全缺陷仅经安全披露通道评估（ADR-009 D4 冻结纪律的归档终态）；
- `legacy/` 下的 Qt 与 `legacy/ui/` 为已归档死代码，禁止 import。

## 验证纪律（云端单源——2026-10-03 起，最高优先级）

1. **本地只编辑，云端做检验**：本地环境仅用于代码编辑与 `git diff` 自查；
   **禁止在本地运行任何构建/测试/lint/SAST/验证命令**（dotnet build/test、
   cargo test/clippy、gradlew、node --test、pytest、ruff、bandit、
   validate_release/verify_* 等一律不跑）。下方「关键命令」仅作 CI 口径参考。
2. **每一轮修改都上云端**：改动完成即推送 GitHub（audit 分支 → PR），
   由 GitHub Actions 全套门禁验证；**Actions 结果是唯一通过依据**。
3. **红灯迭代**：CI 红灯 → 修复 → 再次推送（下一轮），直至全绿才可合并；
   合并前必须全部 pull_request workflow 绿（contracts / ci / core-rust /
   android-quality / supply-chain 等）。

## 关键命令（CI 同口径参考——按验证纪律本地不执行）

```bash
# —— Windows 正典栈（C#/.NET 10，ADR-009）——
cd windows
dotnet build src/Aegis.Windows.App/Aegis.Windows.App.csproj -r win-x64 -p:RestoreLockedMode=true   # 0 警告 0 错误——SP-220/S-03：-r 与 NuGet 锁一致，锁模式防改写
dotnet test tests/Aegis.Windows.Core.Tests -r win-x64 -p:RestoreLockedMode=true    # 核心套件全绿
dotnet test tests/Aegis.Windows.Broker.Tests -r win-x64 -p:RestoreLockedMode=true  # Broker 套件全绿

# —— Rust 策略核心 ——
cd core/rust-policy-core
# SP-183（2026-10-01 审计）：clippy 口径与 CI（core-rust/release-core）统一——
# --all-features --all-targets -D warnings（测试/bench 目标同受检）
cargo test --locked --all-features && cargo clippy --locked --all-features --all-targets -- -D warnings && cargo fmt --check  # 全绿+0 警告——与 core-rust.yml 逐字同口径（SP-183/S-06）

# —— 契约/版本门禁（仓库根）——
python validate_release.py             # AST/JSON/XML 静态验证（版本校验在 scripts/verify_versions.py）
python scripts/verify_versions.py      # 版本单源一致性
python contracts/codegen/verify_bridge_guard.py   # Bridge 守卫单一事实源（改动守卫 JS 后必跑——ADR-007）
python scripts/verify_cross_end_lists.py          # 跨端清单对账（引擎/壁纸）
# —— 文档/CI 形态门禁（第八轮 B1/B8 接入 contract-source-of-truth）——
python scripts/check_workflow_shells.py           # workflow 步骤 shell 与退出码口径
python scripts/check_doc_claims.py                # 文档计数声明与实树对账（「N workflow」类陈述）
python scripts/check_markdown_links.py            # Markdown 相对链接死链 fail-closed
python scripts/check_markdown_tables.py           # Markdown 表格逐行列数与表头一致（R8-DOC-19）
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
# SP-185（2026-10-01 审计）：bandit 豁免清单单源 bandit.yaml（PY-156）——
# 行内 --skip 双源删除，与 legacy-python-guard.yml CI 同口径
bandit -c bandit.yaml -r app/ -q
# SP-186（2026-10-01 审计）：mypy 改裸调用（mypy.ini 单源——文件清单/排除项
# 均在配置内；手写清单已漂移漏 crash_reporter.py 等）
mypy                                     # 全量目录口径（mypy.ini 单源，0 错误）
# SP-245（2026-10-01 审计）：活跃树 SAST 在根目录跑 bandit（配置根级
# bandit.yaml 单源；-ll = Medium/High 门禁）——CI 同口径
cd ../..
bandit -c bandit.yaml -r scripts release contracts agent -ll -q
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

- [ ] 遵守「验证纪律」：本地零检验，推送后 GitHub Actions 对应门禁全绿（红灯修复后再推）：
  - C#：`dotnet build`（0 警告）+ `dotnet test` 两套件全绿
  - Rust：`cargo test && cargo clippy --all-features --all-targets -- -D warnings
    && cargo fmt --check` 全绿（SP-183 统一口径）
  - Android：四模块 ktlint + detekt + 单测 + `:app:lintDebug`（与 android-quality.yml 一致）
  - shared/shell：`node --test`（目录 glob——SP-163，新增测试文件入目录即入门禁）
    + `node shared/shell/snake.test.js` 全绿（SP-187：不再称"显式文件清单"）
  - scripts/contracts/release：`python validate_release.py` + `python scripts/verify_versions.py`
    + `python -m pytest tests/python/ -q`
- [ ] `selftest_*.py` 仅适用 legacy 归档栈 P0 评估通道（正典栈新增逻辑写对应端的
  C#/Kotlin/Node/pytest 测试——WB-118）
- [ ] agent/catalog 改动过红队门禁：`python -m pytest agent/tests -q` +
  `python contracts/codegen/verify_agent_catalog.py`（SP-191——与 agent-redteam.yml 同口径）
- [ ] 依赖/锁文件改动过供应链门禁：requirements-ci.txt 重锁后本地
  `pip install --require-hashes -r requirements-ci.txt` 可装 + `pip-audit`
  干净（SP-191——与 supply-chain.yml 同口径）
- [ ] 遵守单文件单职责与行数红线
- [ ] 涉及 URL/密码/下载/权限时说明了安全考虑
- [ ] 更新了 CHANGELOG.md
- [ ] 遵循 Conventional Commits（feat/fix/refactor/docs/chore/security）

## 常用文件地图

| 路径 | 职责 |
|---|---|
| `windows/src/Aegis.Windows.App/` | **Windows 正典栈**（Chrome UI / Core 数据层 / Broker 安全层 / WebView 封装） |
| `windows/tests/` | C# 两测试套件（Core.Tests / Broker.Tests） |
| `core/rust-policy-core/` | Rust 策略核心（**导航**裁决单源——ADR-008；FFI/C ABI/UniFFI。范围限定：能力评估层 `policy.evaluate`/`capability.validate` 未接入 FFI 通路，核心自述 H-7——能力裁决仍在各端托管 Broker） |
| `android/app/src/main/java/com/aegis/browser/` | Android 端（TabManager/SecureWebViewFactory/BrowserEngine） |
| `android/broker/` + `android/webview-adapter/` | Android 授权 Broker 与导航状态机 |
| `contracts/` | 契约单源（schemas/vectors/policy + codegen 生成器） |
| `shared/` | 双端单源（version.properties/release.json/shell 首页资产） |
| `docs/audit/` | 全仓审计报告（2026-09-07 200 项、2026-09-23 1115 项、2026-09-26 229 项、2026-10-01 241 项、2026-10-02 217 项、2026-10-03 第六轮、2026-10-04 第七轮与第八轮——附机器可读 CSV 索引供下轮自动去重，I-23 / R8-DOC-15） |
| `legacy/windows-pywebview/` | 只读归档栈（ADR-009——禁止活跃改动，见红线 #1） |

## 常见陷阱

- `validate_release.py` 用相对路径定位项目根，**不要**改回硬编码绝对路径。
- `python` 命令在本机可能被 Store 别名拦截：用 `py` 或显式 Python 路径。
- Windows 上 Git Bash 的 `/tmp` 与 Python 路径不一致：别让 Python 读 Git Bash 的 /tmp 文件。
- 快捷键/JS 注入改动后必须跑 `selftest_shell_toolbar.py`——**仅限 legacy 归档栈
  P0 评估通道**（WB-118，2026-09-26 审计）；正典栈等价改动跑 C# 两套件 +
  `node --test` UI 回归。
