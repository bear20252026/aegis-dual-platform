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

### P6：bandit 豁免规则（2026-08-15，CI 口径一致）
- bandit 对 **Low 严重性**告警也返回非零退出码（CI 严格门禁按退出码判定），
  而此前本地验证只看 `Medium:/High:` 行数误报"通过"——教训：**验证必须检查退出码**。
- 豁免清单（ci.yml bandit 步骤 `--skip B110,B404,B603,B607`）：
  - **B110** try_except_pass：静默降级是安全设计（与 S110 同源）；
  - **B404/B603/B607** subprocess：均为**参数列表 + shell=False** 的受控调用
    （`security.py` icacls / `webview2_probe.py` tasklist），无命令注入面。
- 新增 subprocess 调用时需复核：参数列表 + shell=False + 固定命令名，方可沿用豁免。

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

## 7. 开源浏览器审计结论（2026-08-15，详见 docs/open-source-browser-audit.md）

### 7.1 六项目审计要点（精简）
- **FreeDom**（C11 纯 C）：可信父进程+每标签 re-exec worker；**四层沙箱**（seccomp-bpf 白名单/W^X/Landlock/每 tab 命名空间）；worker 无 socket 全部请求父进程代理**重放完整策略**；策略为**纯函数 fail-closed**（17 个 libFuzzer harness 直接测试）；TLS1.3+后量子、JS 默认关按域 allowlist。
- **brave**（Chromium 增量）：Rust adblock 引擎+cxx FFI；**统一请求回调链**（site_hacks→AdBlockTP→CSP→重定向，块→1×1 stub→头改写）；**per-site 确定性 farbling**（FarbleKey：站点 token+PRNG 生成全部指纹值）；ContentSettings 全局默认+per-site 覆盖。
- **ShardBrowser**（Tauri2 壳+独立 Chromium）：API 回环绑定+**JWT 即时轮换吊销**；**临时 profile 关闭自删+启动 purge 残留**；CDP `--remote-debugging-port=0` 自动取端口。⚠️ 反面：csp:null/任意文件读/`--remote-allow-origins=*`/cookie 密钥硬编码。
- **CloakBrowser**：⚠️ **仓库无内核源码**（Vite 脚手架+预编译二进制，反指纹 C++ 补丁不可验证）；理念：拟人输入 humanize/二进制自更新。
- **electron-browser-shell**：极简标签浏览器+Chrome 扩展支持（理念参考）。
- **browser-shell**：浏览器内 Linux VM（v86+Plan9），Cache Storage 状态缓存（概念参考）。

### 7.2 可借鉴点（对 Aegis 下一步，按优先级）
- 🔴 **A-立即**：
  1. **统一请求拦截管线**（brave）：扩展 `request_sent`（main_webview `_apply_dnt_header`）为 DNT→威胁拦截→1×1 stub 统一回调链，一次请求走全量策略；
  2. **纯策略函数 fail-closed+可单测**（FreeDom）：收敛 `safe_url`/威胁决策为单一可单测 Python 策略模块（现分散 security/threat_feed/url_utils）。
- 🟡 **B-中期**：
  3. per-site 确定性 farbling（brave FarbleKey）→ `fingerprint.py` 改确定性模式；
  4. 白名单覆盖黑名单 hosts 风格（FreeDom）→ threat_feed 明确白名单优先语义；
  5. 临时 profile 自删+purge（ShardBrowser）→ Android TabManager 挂起清理。
- ⚪ **C-参考**：组件自更新（CloakBrowser，Aegis 已有 watch_runtime_update）、扩展支持、VM 缓存。

### 7.3 进一步开发建议
1. 下一开发批次：A 级两项（统一拦截管线 + 策略收敛），均映射现有代码改动可控；
2. B 级评估：fingerprint 确定性化/白名单优先/Android 清理；
3. ShardBrowser 4 处安全风险**已全部被 Aegis 现有设计规避**（验证纵深有效性）；CDP 若开启必须回环+鉴权；
4. 跟踪：FreeDom 沙箱（若需更严格隔离）、brave shields 迭代（WebView2 无对应则记录）。

## 8. 2026 浏览器架构趋势审计（2026-08-15，中英双语权威信源核实）

### 8.1 趋势一：去 WebView 化反思（微软实证 + 学术支撑）
- **微软 Copilot 反面实证**（Windows Latest/Windows Report 2026-04）：新 Copilot 内置完整 Edge fork（WebView2 容器渲染 web.copilot.com），**RAM 500MB-1GB vs 原生 WinUI <100MB**——套壳内存代价的实锤；印证"初始 UI/重 UI 不用 WebView2"。
- **ACM SIGMETRICS 2026 "Shiny Objects"**（UVA，cs.virginia.edu/venkat）：对象级 Chromium 内存特征（僵尸对象/内存污染/分配热区）——为内存优化提供理论支撑。
- **混合架构共识**：WebView2 官方（Microsoft Learn）确认"原生壳+WebView 画板"混合模式 + WebMessage 异步通信为推荐。

### 8.2 趋势二：Agent 原生浏览器兴起
- **Cloudflare Kitesurf**（2026-08-06 发布，官方博客+TechCrunch）：**无 Chromium**，V8 isolate + Rust→Wasm（Blitz 渲染+Stylo CSS+Boa JS）；CPU 3.1-3.8×/内存 4.7-7× 低于 Chromium；每页视为不可信输入、SandboxOutbound 唯一网络出口；215K+ WPT；CDP 兼容；将开源。
- **北大 WAB**（ACM WWW 2026 Companion）：Wasm 克服 Agent 浏览器"三堵墙"（内存/网络/安全）。
- **Agent 安全威胁**：IEEE S&P 2026 "Site Isolation is Dead"（IPC 通道攻击面：提示注入+LLM 数据外泄，2 开源浏览器+7 扩展全中招）；WAAA!（arXiv 2026-05：20 种攻击分类，同源策略被 agent 中介绕过）。

### 8.3 趋势三：安全架构革命
- **PQC 已默认落地**：Chrome 131+/Brave 1.73.86+/Edge/Firefox 132+ **默认 X25519MLKEM768**（Kyber 混合）——WebView2 底层继承，Aegis 零成本；Chrome MTCs 量子抗性证书（Phase 3 Q3 2027 CQRS）；PQ-TLS 测量无延迟增加（arXiv 2607.29005）。

### 8.4 混合原生壳+异步消息驱动（落地核实）
- **Helium**（imputnet/helium 0.11.7.1）：⚠️ 核实为 Chromium 系（AppImage 147MB），**非"7.6MB 极致轻量"**（该说法不可证实）；极致轻量参考 Kitesurf 思路。
- **Servo/servoshell**（0.0.6/2026-03-31，Rust 引擎）真实。
- **WebView2 官方**：ScenarioWebMessage 异步通信 + ContentLoading RemoveHostObjectFromScript + 非提权宿主最佳实践——与 Aegis NavQueue 模式同构。

### 8.5 对 Aegis 适用性结论
- ✅ **已满足（零动作）**：混合壳架构（pywebview 原生壳+WebView 内容）、异步消息驱动（NavQueue 即此模式）、初始 UI 轻页、PQC 底层继承、性能基线监控。
- 🟡 **评估**：混合原生壳进一步分离（地址栏/书签原生化，受 pywebview 约束）；Helium 7.6MB 信息已纠正。
- 🔵 **新方向**：Agent 友好 API 标准化（mcp.py 雏形扩展 js_api schema）；Agent 安全防护（MCP 接入注意通道隔离+工具最小权限，OWASP Agent Cheat Sheet）；Wasm 插件沙箱（远期，北大 WAB 思路）。
