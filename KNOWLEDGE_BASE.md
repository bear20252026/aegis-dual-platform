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

## 9. Tauri 迁移调研结论（2026-08-15，详见 docs/tauri-migration-report.md）

### 9.1 核实事实
- **Tauri 2.0 实测**（johal.in 2026-04）：安装包 ~5MB（vs pywebview PyInstaller 实测 200MB）、空闲内存 42MB、冷启动 320ms、输入延迟 12ms；ACL 权限模型默认拒绝 + scope deny 优先（官方中文文档）；Tauri 官方已不再做与 Electron 的官方对比。
- **浏览器生态 = 实验期**：Verso 已正式停滞（仓库归档，Servo 更新过快+人力有限；Tauri 转探索 Servo 可选渲染）；CNTRL（Tauri v2+SolidJS 三级 AI 路由，Phase 1-3/7 半成品）；Adaptive（★344 API 驱动 UI）；MCP Browser（Tauri 内置 MCP server）；**无生产级 Tauri 浏览器成功案例**。
- **社区**：r/learnpython 打包 200MB 是 pywebview 痛点；HN ActivityWatch 迁 Tauri（跨平台打包驱动）；掘金 6 问题选型框架（C 端轻量→Tauri、内部工具→pywebview/Electron）；**关键案例 Tune PR #7（pywebview→Tauri 2.x + Python sidecar，前端不变仅换桥）——Sidecar 平滑过渡已验证可行**。

### 9.2 结论（理性评估）
- **不建议立即整体迁移**：Tauri 浏览器生态实验期（无生产级案例）+ Aegis Python 安全纵深（25 文件 4571 行 + 统一拦截管线 + 凭据治理）需 Rust 全量重做（回归风险）+ 团队 Rust 成本。
- **架构理念同源**：Tauri 也是"壳"（系统 WebView），迁移是换壳语言非换架构；Aegis 已具备等价物（js_api 白名单≈ACL、NavQueue≈异步消息驱动、mcp.py≈MCP Browser）。
- **路径**：立即零成本借鉴（ACL deny 优先复核白名单、CNTRL WASM 沙箱理念、Adaptive API 驱动）；中期若生态出现生产级案例/CNTRL 完成/团队 Rust 就绪 → **Sidecar 平滑过渡**（Tune 案例）；长期维持 Python+pywebview 栈持续吸收理念。

### 9.3 大胆求索深化（2026-08-15 补充调研，详见报告第七节）
- **pytauri（★1410/v0.8.0/2026-08-14 活跃）= 中期首选备选**：pyo3 桥 + standalone 模式（主线程 Python+Tauri）——**全部 Python 业务保留仅换壳**，比 sidecar 更平滑（同进程无通信开销）；风险：pyo3 异步勿跨 FFI 边界（HN 讨论）。
- **立即四项**（零成本）：① ACL deny 优先复核 Aegis 白名单（黑名单命中须优先于白名单放行）；② `_apply_request_policy` 补 deny 语义自检；③ WASM 沙箱理念评估（CNTRL：WASI 受限 syscall + JS Worker 沙箱）；④ DataZen 实证借鉴（Tauri+AI+MCP <10MB，2026-08-07）。
- **中期 PoC 三关**：体积/内存/启动实测 vs 现有 pywebview 基线，不过关不迁移（路径 A=sidecar/Tune 案例、路径 B=pytauri）。
- **生态观察**：Tauri 2.11.5（2026-07）移动端多窗口+IPC 死锁修复；DataZen/Code Déjà Vu 类 Tauri AI 工具实证积累。

### 9.4 第二轮调研结论（2026-08-15，详见 docs/tauri-migration-report-2.md）
- **Tauri 状态**：v2.11.5（2026-07-01）★110213；pytauri ★1410/v0.8.0 活跃，README：几乎不写 Rust、**pytauri-wheel 全 Python 免编译器**、无 IPC 开销（Pyo3 直连）、明确"替代 pywebview"目标、可集成 nicegui/gradio/FastAPI。
- **收益 vs 风险（多信源实测）**：体积 128→5MB（-96%）、内存 49MB/实例（-72%）、启动 1.5s→500ms（LOL 工具/生产案例/基准交叉验证）；**最大风险=系统 WebView 三引擎渲染不一致**（Noi 案例 2023 Tauri→Electron 隐藏大坑：授权弹窗/文件下载/远程页拦截/API 少；2026 重试 v2 再失望→"工具可用、平台慎用"）。
- **结论**：**整体迁移（Rust 全量重写）风险 > 收益**（渲染一致性 + 安全纵深重建回归）；**部分重构（pytauri/Sidecar 保留 Python 业务）收益 > 风险**（pytauri 免 Rust + 无 IPC 开销 + Aegis 壳 UI 简单渲染风险可控）。
- **分步走路径**：① ACL deny 复核（零风险本周）→ ② pytauri 演示预研 → ③ pytauri-wheel PoC 三关实测 → ④ 按层分模块迁移（smoodit 经验：Aegis 分层清晰已具备）→ ⑤ 三关达标才迁移，否则季度复核维持。

## 10. 2026 Rust 桌面架构全景（2026-08-15，详见 docs/rust-desktop-landscape-2026.md）

### 10.1 Rust 是否 2026 新选（权威信源）
- **是"新选之一"但非唯一**：Rust GUI 已从"早期"进入"可用"阶段（Wren 2026-03：egui 即时模式最火/Dioxus React 风格/Iced Elm 架构/Xilem 未就绪）；**Tauri 2 成 Web 栈跨平台新默认**（Vanja 2026-05，106k★）；egui 1300万+ 下载（技术栈 2026-04 流行度：egui > Tauri > Dioxus 2.5w★ > Iced 1.9w★）；中文支持 Tauri 第一（码客说 2026-04 五维度）。

### 10.2 Tauri 之外选择（横向对比）
- **纯 Rust GUI 均不适合浏览器壳**：egui（工具风）、Iced（渲染受限）、Slint（嵌入式）、**GPUI（唯一一线用户=Zed；Longbridge 迁入需自建 60+ 组件库=无开箱组件）**、Xilem（未生产就绪）——渲染/组件生态不足。
- **非 Rust 壳**：Wails 3（Go，12.3MB/70MB/0.5s，v3 内置 WebEngine Core Blink，无移动端）；NeutralinoJS（2-5MB 极轻但能力/生态受限）；Electron 34（渲染一致但 150MB+ 重量级）；**pywebview（Aegis 现状）= Python 壳浏览器最优**。
- **结论**：Tauri（或 pytauri）仍是 Rust 生态中壳浏览器最匹配；Aegis 现状（pywebview）已处"Python 生态+壳浏览器"最优位置，无需为换而换；若求 Rust 收益走 pytauri 部分重构（分步走见 9.4）。

## 11. pytauri 部分重构技术路线（2026-08-15，详见 docs/pytauri-migration-technical-plan.md）

### 11.1 三条路线选型（官方文档+examples 源码+Tune 源码核实）
- **B. pytauri-wheel（全 Python）= 主路线**：免 Rust 编译器（`pip install "pytauri-wheel == 0.8.*"` 预编译 wheel）、Pyo3 直连（无 IPC 开销）、**Windows Tier 1**（作者主环境 Win10=Aegis 目标）、wheel+sdist 分发、Cython 源码保护、examples/tauri-app-wheel 完整。
- **A. standalone = 备选**：需 Rust 编译器 + python-build-standalone 捆绑（pyembed/PYTAURI_STANDALONE/PYO3_PYTHON/RUSTFLAGS rpath/install_name 补丁/tauri build bundle-release），产出独立可执行（内网免 Python 运行时）；触发条件=政府内网需独立可执行。
- **C. sidecar = 不推荐**：JSON-RPC 进程通信改造成本高于 B（NavQueue 语义需重构）；仅 wheel 平台覆盖问题才回退（Tune 案例 src-tauri/src/sidecar.rs 为参考）。

### 11.2 Aegis 落地要点
- Tauri.toml（frontendDist=start.html + [[app.windows]]）+ capabilities（ipc 权限≈现 js_api 白名单映射）+ main.py 改桥层（webview.create_window→pytauri 窗口 API）
- 分步：①ACL deny 复核→②跑通 examples/tauri-app-wheel（已确认可跑）→③pytauri-wheel PoC 最小壳（三关实测）→④分模块迁移（壳→桥→安全）→⑤达标才迁移
- 已克隆源码：D:/abrowser/research/pytauri（examples 三个）+ D:/abrowser/research/Tune（sidecar.rs）

### 11.3 补充调研（2026-08-15 第三轮）
- **pytauri-wheel 0.8.0 平台覆盖（PyPI 核实）**：Windows win_amd64（cp39-cp313）+ win_arm64（cp311-cp313）、macosx 13/14、manylinux_2_35；**⚠️ cp314 wheel=0——Aegis 本机 Python 3.14 无预编译 wheel**（会回退 sdist 源码编译=违背免 Rust 初衷）→ **解决方案：用本机已有 CPython 3.12.13（cp312-win_amd64 wheel 存在）或 3.13**。
- **pytauri 生态状态**：★1381、v0.8.0（2025-09-02）、80 releases、5 contributors（主维护 WSH032）、Apache-2.0、Last push 2026-06-08；create-pytauri-app 脚手架（0.6+ 推荐，uv+copier）；启动语义（Discussion #172：Python 主线程+Tauri 同线程、asyncio 子线程、async 勿跨 FFI 边界）。
- **分发成本提醒**（Life OS 类实践）：桌面分发=代码签名+notarization+开发者账号+跨平台 CI 矩阵（"boring half"）；政府内网分发可评估免签名路径，但 Windows 侧需考虑。
- **中文专门评测稀缺**（pytauri 较新），以官方文档+GitHub+源码为准。

### 11.4 pytauri 停滞状态核实（2026-08-15 第四轮，重要）
- **⚠️ 停滞确认（深度核实）**：PyPI pytauri/pytauri-wheel 最新均 0.8.0（2025-09-02），**此后近 11 个月无新版本、无新代码提交**（最近 commit 2025-09-10 仅依赖更新）；releases 全为 0.8.0 线；无活跃开发分支。作者 README 明示"难以在没有社区激励下维护"。
- **替代项目**：**pyloid**（★516，"Electron for Python"，Builder/Tray/Store 内置，跨平台）= 潜在 B 替代（需核渲染内核/体积）；**tauri-plugin-python**（★159，2026-06-20 活跃，Rust 主导+PyO3/RustPython）= 与 pytauri 互补非替代（需写 Rust）；**PyWry**（★93，2026-02 新，**底层依赖 PyTauri**）= pytauri 停滞会波及，不能作替代。
- **评估调整（禁止被困原则落地）**：① 版本策略改"**长期 3.12.13**"（生命周期至 2028-10，不再等待上游补 cp314）；② 季度复核升级**双目标**（pytauri 是否复苏 / pyloid 是否成熟）；③ PoC 已验证可用（0.8.0 可安装可构建），B 路线当下收益结论不变，远期演进重新定位。

### 11.5 pyloid 与 tauri-plugin-python 深度调研（2026-08-15 第五轮）
- **pyloid（★516/更新 2026-07-27/v0.27.1-beta 活跃）**：渲染内核=**PySide6.QtWebEngine（Chromium）**（browser_window.py QWebEngineView）；依赖 pyside6 6.9.2、python >=3.9,<3.14；功能全（Builder/Tray/Store/Timer/Monitor/线程安全 RPC）；**⚠️ 体积大（Qt WebEngine ~100MB+）内存高（作者 issue #3 + pythonguis 技术站确认）**——与 Aegis"轻量壳"目标相悖，**不构成 B 有效替代**（Aegis 现状 pywebview 体积/内存反而优于它）；降级观察项（仅未来需 Chromium 渲染一致性时评估）。
- **tauri-plugin-python（★161/更新 2026-07-29/v0.3.9 活跃）**：架构=Rust 插件（Cargo.toml `default = ["venv","pyo3"]`，可选 `rustpython`）；PyO3 默认（完整 CPython 兼容需 libpython）vs RustPython（免目标机 Python 但 stdlib 受限非完整 Python）；安全模型（runPython/register 默认禁用）；**Rust 主导路线**（README 明示"想全 Python 开发请看 pytauri"）——**不替代 B**（违背免 Rust 初衷）。
- **评估结论**：**B 路线（pytauri-wheel）仍是最优**（免 Rust + 系统 WebView 轻量 + PoC 已验证）；pyloid/tauri-plugin-python 均不构成有效替代，pyloid 降观察。

### 11.6 Python 桌面壳全景调研（2026-08-15 第六轮：热门框架定位盘点）
- **热门 Python 框架（★ 均远超 pytauri）定位全不同**：Textual ★36936（TUI 终端）、Reflex ★28788（Web 全栈编译 React）、NiceGUI ★15970（Vue/Quasar+FastAPI，native mode 边缘相关）、Flet ★16401（**Flutter 自绘渲染**非系统 WebView）、imgui_bundle ★1342（即时 GUI）；中文四层选型体系多站转载（阿里云/掘金/DEV/火山引擎 2026-04：原型层 Streamlit/Gradio、轻量层 NiceGUI/Flet、工程化层 Reflex、重型层 PySide6/DearPyGui）。
- **核心结论**：不是"只有 py"，而是 **"pytauri 的定位（免 Rust + 系统 WebView + 浏览器壳）没有竞争者"**——更热门的框架定位是 Web 应用/TUI/Flutter 自绘（解决"Python 写 UI"，非"系统 WebView 壳"）；更"壳"的 pyloid 渲染内核相悖（QtWebEngine 重量级）；tauri-plugin-python 需 Rust。**B 路线仍唯一匹配；pytauri 停滞时 Aegis 有现成退路（pywebview 现状）**；观察项 NiceGUI native mode / pyloid。

### 11.7 Flet 深度调研 + 壳项目盘点（2026-08-15 第七轮）
- **Flet（★16579/v0.86.5/最近 commit 2026-08-14 非常活跃）**：渲染=**Flutter 自绘**（编译的 Flutter 桌面客户端二进制，PR #6309 从 wheel 移 GitHub Releases 按需下载）；**⚠️ 体积知名痛点**（flet pack 77.8MB/flet build 100MB+/v0.25.2 打包 80.2MB，issue #4620/#3048 多用户反馈；社区建议旧版 v0.19.0 11-17.7MB）；**不推荐作为 Aegis 壳/替代**（Flutter 自绘非系统 WebView，无法承载任意网页渲染 + 安全纵深；体积与轻量目标相悖；仅观察其活跃社区模式）。
- **pywebview（Aegis 现状库）**：★5950/v6.2.1（2026-04-15）/月下载 158 万（PyRank 确认 Actively Maintained）——**Aegis 现状库非常健康**（比 pytauri 活跃得多），退路坚实。
- **cefpython（★3234/更新 2026-08-10）**：捆绑 Chromium（Electron 式）；**社区确认已弃维护**（issue #673：仅支持到 Python 3.11，"pywebview 是最好的替代"；PR #691 加 CEF147/Python 3.10-3.14 未合并）——不选。

## 12. 2026 全面审计结论（2026-08-15，详见 docs/audit-2026.md）

### 12.1 综合评级 A（架构合规/安全/代码/功能边界四维）
- **架构合规（2026 最推荐）**：混合原生壳 + 异步消息驱动（NavQueue）+ 壳抽象可插拔 + ESM per-origin + PQC 底层继承 + Agent 白名单（mcp 7 工具）——**高度合规，无重大偏离**。
- **安全**：✅ 无注入面（eval 封装+硬编码脚本）、无路径遍历（asset_scheme 白名单+穿越防护）、subprocess 受控（参数列表+shell=False）、凭据治理（.gitignore+环境变量）。
- **代码逐行**：✅ shell_adapter 240 行逐行精读无逻辑 bug（_make_wrapper 工厂闭包绑定正确）；api_bridge 下标访问均为结构固定数据；nav_queue 三层防死锁（timeout 0.5s+6s 超时+RLock）。
- **功能边界**：✅ js_api 白名单 27 个全部有效（无缺失无多余）；错误处理 15 处 except 返回安全值；9 处 _lock 覆盖写操作；空状态安全返回。
- **观察项（非 bug）**：🟡 _tabs_snapshot 锁外只读（无并发写冲突证据）、105 处静默降级（设计性，KNOWLEDGE_BASE B110 记录）；🟢 CI 转绿待确认（PyInstaller 修复已推送 e2fc3ba）。

## 13. 开源项目精读借鉴（2026-08-15：Tune + qutebrowser）

### 13.1 Tune（pywebview→Tauri sidecar 生产案例，src-tauri/src/sidecar.rs 精读）
- **CREATE_NO_WINDOW**（sidecar.rs:80，Windows 隐藏后端控制台窗口）——**未来 C 路线（sidecar）设计要点**：Aegis 若走 sidecar，后端进程必须隐藏控制台窗口（当前壳抽象无 sidecar 进程，纯记录零风险）。
- **JSON-RPC id 匹配分发**（reader thread 响应/事件分发）——Aegis js_api 事件桥（on_loaded/request_sent）理念已对应 ✅。
- **sidecar_log 可观测性**——Aegis 已有 log_event（crash_reporter）✅ 对应（威胁拦截已加 log_event）。

### 13.2 qutebrowser（★11641，2014 至今，GPL-3.0，Python+QtWebEngine 成熟键盘浏览器）
- **"重活放 C++ 层 + GIL 释放"**（FAQ 明确）——Aegis NavQueue 已有同理念（窗口操作串行化到导航线程）✅。
- **安全更新模型**（QtWebEngine patch 回移安全修复）——Aegis WebView2 **Evergreen 2 周节奏更优** ✅。
- **键盘驱动深度**（vim-like + hints 模式）——Aegis 已有快捷键（R1 借鉴 min）；qutebrowser 11k★ 验证"Python 浏览器+键盘驱动"大规模可行——**hints 模式可作未来增强评估**（不改变功能，先记录）。
- **结论**：Tune/qutebrowser 核心经验 Aegis 多数已对应落地（NavQueue/log_event/Evergreen）——印证 Aegis 架构选择正确；新增借鉴点已记录（CREATE_NO_WINDOW + hints 模式，均零风险待评估）。

## 14. FreeDom 四层沙箱精读（2026-08-15，src/os_sandbox.c 14933 字节）

### 14.1 四层实现（Linux 原生机制，逐层精读）
- **第一层 seccomp-bpf**：`os_allowed` 白名单 30 个 syscall（read/write/mmap/mprotect/futex/clock_gettime 等）；**io_uring/process_vm_readv/bpf/userfaultfd 等旁路原语按构造拒绝**（注释："denylist could forget them"——白名单优于黑名单）。
- **第二层 W^X**：`os_prot_allowed`——mmap/mprotect 一律拒绝 PROT_EXEC（可执行内存请求被拒）。
- **第三层 Landlock**（os_sandbox.c:227 起）：landlock_create_ruleset/add_rule syscall 封装（文件系统访问控制）。
- **第四层 命名空间**：`os_namespace_flags` = CLONE_NEWUSER|NEWNET|NEWIPC|NEWUTS；`os_isolate_namespaces` 用 unshare()，EPERM/EINVAL/ENOSYS 优雅降级（seccomp 仍强制边界）。
- **反 dump**：`os_no_dump`（prctl undumpable + no core，防凭据外泄）。
- **调用链**：tab.c:1363-1366（fork 子进程→触碰内容前 os_isolate_namespaces+os_no_dump+os_harden→TAB_READY）+ renderer.c:29-30（os_no_dump+os_harden→_exit(90)）；worker 无网络父进程双管道代理。

### 14.2 对 Aegis（Windows WebView2）借鉴结论
- **代码不可移植**（Linux 机制），但**设计哲学高度同构**：白名单（js_api/URL 已同哲学）、分层纵深（Aegis 多层防御同哲学）、**W^X ↔ ESM 禁 JIT**（WebView 层等价物）、进程隔离（WebView2 多进程由内核提供，底层更强）、优雅降级（Aegis 静默降级同哲学）。
- **新增可借鉴点**：反 dump 的"**内存凭据不落地**"理念——Aegis 凭据治理（.gitignore+环境变量）的强化方向（零风险记录待评估）。

## 15. brave adblock 引擎调研（2026-08-15，Rust 引擎源码精读）

### 15.1 引擎结构（components/brave_shields/core/common/adblock/rs/src/）
- **URL 匹配**（engine.rs）：`matches()` → `check_network_request_subset`（`Request::preparsed` 六维上下文：URL/hostname/initiator/request_type/third_party/method + `previously_matched_rule`/`force_check_exceptions` 参数）。
- **规则结构**（filter_set.rs）：`FilterSet` 包装 adblock crate 的 InnerFilterSet + `add_filter_list`/`add_filter_list_with_permissions`（批量规则 + 权限）。
- **规则解析**（convert.rs）：InnerBlockerResult/RegexManagerDiscardPolicy 等调试转换。
- **资源过滤**（resource_storage.rs）：`BraveCoreResourceStorage` 包装 `InMemoryResourceStorage` + 资源 JSON 解析/克隆/扩展（被拦请求回 1×1 透明图存根）。
- **cxx FFI**：Rust 引擎 + cxx crate 桥（Cargo.toml/BUILD.gn），C++ 侧调用高性能匹配。

### 15.2 对 Aegis 威胁拦截借鉴结论
- 🟡 **六维请求上下文匹配**（preparsed Request）——Aegis 目前 host 级（host_is_blocked）；可评估扩展资源类型/第三方判断提升拦截精确性（区分文档/子资源请求）。
- ✅ **例外/主规则分层**（previously_matched_rule + force_check_exceptions）——Aegis 已 deny 优先同哲学；可强化"例外强制检查"语义。
- 🟡 FilterSet 批量规则带权限元数据——threat_feed 规则集加载可借鉴（规则源可信度分级）。
- ⚠️ **资源存根替换**（1×1 透明图）——受 WebView2 限制（pywebview 6.x request_sent 仅改头不能改响应），记录为拦截语义增强方向（导航层已兜底）。
- ✅ Rust 高性能匹配（cxx FFI）——Aegis 用 set 查找已高效（小规则集）。
