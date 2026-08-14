# KNOWLEDGE_BASE.md — 架构决策与工程知识沉淀

本文件记录 Aegis 的关键架构决策、踩坑记录与设计理由，作为团队与 AI 助手的"长期记忆"。**新增决策请追加并注明日期**；改动既有决策前先读本文。

## 1. 技术路线决策

### D1：Windows 只走 WebView2 路线（2026-08-14）
- **决策**：Windows 仅面向 WebView2 Evergreen Runtime，不再维护 macOS 后端与 NSIS 安装脚本。
- **理由**：内核安全更新由微软维护（借力），壳层聚焦差异化功能；MSIX + App Installer 承担更新。
- **影响**：QtWebEngine 旧栈已归档至 `windows/aegis_source/legacy/`，活跃代码禁止引用。

### D2：Android 首引擎为 System WebView（2026-08-14）
- **决策**：Kotlin/Compose + Android System WebView；`BrowserEngine` 锁定安全边界。
- **理由**：零内核维护成本；后续可在保留 `BrowserEngine` 边界的前提下评估 GeckoView。
- **边界清单**：http/https 唯一协议；禁文件访问、内容访问、file URL 跨域、混合内容；非 DEBUG 禁 WebView 调试。

### D3：先代码后构建（2026-08-14）
- **决策**：遵循"先完成代码与发布配置，后安装工具并构建验证"。
- **理由**：政府项目严谨性——代码与配置先行审阅，工具链就绪后统一构建验证。

## 2. 架构决策

### D4：单文件单职责 + 行数红线（2026-08-14）
- 新文件 ≤ 300 行（目标 100-200）；改造后 ≤ 500 行；触 500 行即拆。
- 依据：S1 拆分 `main_webview.py`（763 行 → 薄入口 + shell_toolbar/nav_queue/api_bridge）的收益验证。

### D5：导航线程队列（NavQueue）防死锁（2026-08-14）
- **问题**：js_api 回调在 pywebview HTTP 服务线程运行；若同步调用 load_url/evaluate_js，winforms 后端 Invoke 到 UI 线程并阻塞等待 → 互相等待死锁（"搜索后页面不跳转/冻结"）。
- **方案**：所有窗口操作投递到独立导航线程串行执行；单操作带 6s 超时（防 evaluate_js 的 semaphore 无限阻塞）；看门狗监控线程健康并自动重启。
- **红线**：js_api 方法绝不同步执行窗口操作。

### D6：js_api 白名单防递归注入死锁（2026-08-14）
- **问题**：pywebview 注入 js_api 时用 `dir(obj)` 递归扫描，window 对象树含循环引用 → 无限递归（crash 报告 834 层铁证）。
- **方案**：`Api.__dir__` 只暴露 `_JS_EXPOSED` 白名单；新增 JS 方法必须同步加入白名单。

### D7：统一安全关口（safe_url）（2026-08-14）
- 所有导航入口（IPC/会话/书签/历史/拨号/命令行/地址栏）加载 URL 前必须过 `app/security.py::safe_url()`。
- 白名单：http/https；about/内部伪协议仅壳层自身流程放行；file:/javascript:/vbscript:/chrome: 一律拒绝。

## 3. 踩坑记录

### P1：validate_release.py 硬编码路径（H1）
- 原打包机残留 `Path('/home/ubuntu/aegis_dual_platform')` → Windows 上必然失败。
- 修复：`Path(__file__).resolve().parent`。**勿改回绝对路径**。

### P2：nav_queue lambda 捕获循环变量（B023）
- `lambda w=w, arg=arg` 在 for 循环中捕获变量 → mypy B023 + 语义风险。
- 修复：`functools.partial` + 模块级显式类型函数 `_load_url_op`。

### P3：Android WebView 双实例（M1）
- 原 MainActivity `BrowserEngine(view).configure()` 与 `BrowserEngine(view).load()` 各 new 一个实例。
- 修复：`SecureWebViewFactory` 统一"创建 + 安全配置"。

### P4：标签 `pinned` 字段缺失（2026-08-15）
- `new_tab` 创建的标签缺 `pinned` 键，快照中普通标签无此字段 → 渲染/类型不一致。
- 修复：所有标签统一 `{"pinned": False}`；`_tabs` 类型注解改为 `list[dict[str, Any]]`。

### P5：本机工具链注意
- `python` 命令可能被 Microsoft Store 别名拦截 → 用 `py` 或显式路径（本机：`C:\Users\17296\AppData\Local\Programs\Python\Python314`）。
- Git Bash 的 `/tmp` 与 Python 路径不一致 → 别让 Python 读 Git Bash 的 /tmp 文件。

## 4. 2026 工具链（已集成）

| 工具 | 版本 | 用途 | 关键点 |
|---|---|---|---|
| ruff | 0.16.3 | Lint + 格式 | 项目自带 ruff.toml（豁免 BLE001/S110，安全设计要求） |
| bandit | 1.9.4 | 安全扫描 | Medium/High 必须为 0；B110 与 S110 同源，属设计豁免 |
| mypy | 2.3.0 | 类型检查 | 需 `types-pywin32`（security.py 的 pywin32 桩） |
| ktlint/detekt | 1.8.0/1.23.8 | Kotlin（待 Gradle 环境） | Android 完整检查需 Android Studio |

## 5. 版本与发布

- `shared/version.properties` 是双端版本**单一来源**；`scripts/sync_versions.py` 同步声明。
- 当前基线：v0.3.0（标签增强 + Chrome/Edge 导入向导）；发布流程：提交 → 打标签 → `gh release create`。
- GitHub 仓库：`bear20252026/aegis-dual-platform`（私有）；CI 已在 `.github/workflows/ci.yml` 配置。

## 6. 待办与方向（源自壳浏览器研读，2026-08-15）

| 编号 | 方向 | 借鉴来源 | 状态 |
|---|---|---|---|
| R1 | 快捷键默认表独立 + 用户可配置 | min `defaultKeybindings` | 待实施 |
| R2 | js_api 生成 OpenAPI/JSON Schema | steel/ShardBrowser | 待实施 |
| R3 | computer_use 接入 MCP | ShardBrowser `mcp_setup.rs` | 待评估 |
| R4 | 标签状态分层（tab/task/windowSync） | min `tabState/` | 待实施 |
| R5 | WebView2 WebExtension 生态调研 | electron-browser-shell | 待调研 |
| R6 | 本文档体系 | FreeDom | ✅ 本次 |
| R7 | 可选指纹/隐身（默认关） | ShardBrowser/Cloak | 待评估 |
| R8 | 阅读模式（视图/决策分离） | min `readerView` | 待实施 |
