# Tauri 重构第二轮调研报告（tauri-migration-report-2）

> 调研日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> 方法：多方交叉验证（权威文档/官方站/技术站/GitHub/开源项目/媒体报道，中英双语）
> 问题：Tauri 重构风险如何？收益抵得上风险吗？分步走先走哪几步？部分重构可行吗？

---

## 〇、结论速览

**收益抵得上风险——但仅在"部分重构"前提下。** 整体迁移（Rust 全量重写）风险 > 收益（Noi 案例的渲染一致性教训 + 安全纵深重建回归风险）；而 **pytauri 的重大发现**（几乎不用写 Rust、pytauri-wheel 全 Python 免编译器、无 IPC 开销、明确"替代 pywebview"目标）使"保留全部 Python 业务 + 换 Tauri 壳"成为**收益显著大于风险**的可行路径。

## 一、Tauri 当前状态（权威核实）

| 项 | 数据 |
|---|---|
| 最新版本 | **tauri-v2.11.5**（2026-07-01） |
| 仓库活跃度 | **★110213**，2026-08-15 更新 |
| 移动端 | 2.11 多窗口（iOS scenes/Android Activity embedding）+ IPC 死锁修复 |
| 官方基准 | tauri-apps/benchmark_results（hyperfine 测启动/二进制/内存） |
| **pytauri** | ★1410 / v0.8.0 / 2026-08-14 活跃；README：几乎不写 Rust、**pytauri-wheel 全 Python**、无 IPC 开销（Pyo3 直连）、支持 asyncio/trio/anyio、自动生成 TS 类型、可集成 nicegui/gradio/FastAPI、**明确目标"成为 pywebview 替代品"** |

## 二、风险调研（多信源）

### 2.1 系统 WebView 不确定性（最大风险）
- **三引擎不一致**（Reddit r/tauri + r/rust）：测试 WebView2/WKWebView/WebKitGTK 三个渲染引擎而非一个 Chromium——CSS/JS API 跨平台差异
- **老 WebView 不更新**：系统自带 6-7 年旧 WebView 问题；Linux Ubuntu 20.04 WebKitGTK 依赖
- **桥接限制**：同步调用不可行（wry #454）；serialization/memcopy 桥开销
- **SoloDevStack 诚实评测**（2026-07-23）：web-native 边界不宽容；"再建一次 100% 选 Electron"（社区用户）

### 2.2 真实迁移失败案例（Noi，掘金 2026-07-24）
- 2023-12 正式 Tauri→Electron："隐藏大坑"=系统 WebView 兼容性问题（授权弹窗/文件下载/远程页拦截/API 少）
- 2026 重试 Tauri v2（tauri::webview 新 API）→ 再失望（快捷键失效/文档不反映变化/示例少/Issue 无回复）
- 结论："工具可用、平台慎用"；Electron 适合平台型应用，Tauri 适合小型专一工具；**Web UI 展示、复杂交互应谨慎**

### 2.3 重构成本
- Rust 重写 Aegis 25 文件 4571 行 + Android 组件；安全纵深（白名单/统一拦截管线/凭据治理）全量重建回归风险
- 团队 Rust 学习曲线（掘金共识：重编译 30s+ 起步，AI 也救不了节奏）

## 三、收益量化（多信源交叉验证）

| 信源 | 体积 | 内存 | 启动 |
|---|---|---|---|
| johal.in 基准（2026-04-30） | Tauri 4.8-5.2MB vs Electron 148-162MB | 42MB vs 187MB | 320ms vs 1800ms |
| **LOL 战绩工具实测**（钛刻 2026-06-07） | **128MB→5.01MB（-96%）** | 306→241MB | 1.5s→500ms |
| 生产案例（Tauri 2.1，12 个月） | 14MB（-83%） | 49MB/实例（-72%） | CI 3.8min（-65%） |
| SSH 客户端（DEV 2026-05-29） | 8MB vs 120MB+ | 50MB vs 200MB+ | 1.5s vs 5s+ |
| pywebview 打包（issue #353） | PyInstaller 实测 80-90MB（纯净 venv base 10-15MB） | — | — |

**注**：pywebview 纯净 base 10-15MB 与 Tauri ~5MB 差距小于 Electron 对比；Aegis 实际打包会因依赖（PySide6 运行依赖等）偏大。

## 四、分步/部分重构实践（真实案例）

| 案例 | 路径 | 关键经验 |
|---|---|---|
| **Tune PR #7**（2026-04-28） | pywebview→Tauri 2.x + Python sidecar（JSON-RPC stdin/stdout） | 前端不变仅换桥（pywebview.api→invoke/listen）；数据格式保留；解决 WebView2 init 抖动 |
| **smoodit**（DEV 2026-01-24） | Electron→Tauri + FastAPI sidecar + Ollama sidecar | 2 个月完成；**成功关键=原型期 UI/领域逻辑分离**（Aegis 分层清晰已具备） |
| **5 Phase 迁移指南** | 后端不动→Sidecar 生命周期→Tauri Commands（1-2 天）→前端更新（1 天）→构建配置 | 分步可逆，每步可验证 |
| **pytauri 双模式** | standalone（主线程 Python+Tauri）/ wheel（全 Python 免 Rust） | **几乎不写 Rust**；无 IPC 开销（Pyo3 直连，非 sidecar 进程通信） |

## 五、综合评估：收益 vs 风险

### 整体迁移（Rust 全量重写）：❌ 风险 > 收益
- 渲染一致性（Noi 教训）+ 安全纵深重建回归风险 + 团队成本——**不值得**

### 部分重构（pytauri/Sidecar 保留 Python 业务）：✅ 收益 > 风险
- 收益：体积/打包/签名/权限模型/更新器（Tauri 产品级交付）+ 保留全部 Python 安全纵深（零回归风险）
- 风险收敛：不重写业务 → 渲染一致性风险仅限壳页面（Aegis 壳 UI 简单，风险可控）；pytauri 无 IPC 开销
- pytauri 风险：独立社区项目（非 Tauri 官方背书）；pyo3 异步勿跨 FFI 边界

## 六、分步走路径（部分重构，大胆求索+小心验证）

| 步骤 | 动作 | 验证门禁 |
|---|---|---|
| **第 1 步**（零风险，本周） | ACL deny 优先复核白名单 + 威胁拦截 deny 语义自检 | 自检通过 |
| **第 2 步**（预研） | 跑 pytauri `examples/tauri-app` + `tauri-app-wheel`（全 Python）演示 | 演示跑通 |
| **第 3 步**（PoC） | pytauri-wheel 搭 Aegis 最小壳（窗口+导航），Python 业务原样挂载 | **PoC 三关实测**（体积/内存/启动 vs pywebview 基线） |
| **第 4 步**（分模块） | 按层逐步迁（壳→桥→安全模块），smoodit 经验（Aegis 分层清晰） | 每模块自检+回归 |
| **第 5 步**（决策） | 三关达标 + 渲染风险可控 → 迁移；否则维持（季度复核） | 季度复核记录 |

## 七、信源清单（第二轮）

- 权威：github.com/tauri-apps/tauri（v2.11.5/★110213）、pytauri/pytauri（★1410/v0.8.0）、v2.tauri.app/develop/sidecar、tauri-apps/benchmark_results、pytauri.github.io（build-sdist/wheel）
- 技术站：johal.in（基准+6 个月回顾）、SoloDevStack（2026-07-23 诚实评测）、DEV（SSH 客户端/smoodit）、钛刻 TCTI.cn（LOL 工具实测）
- 社区：Reddit r/tauri + r/rust（系统 WebView 风险）、掘金（Noi 案例 2026-07-24 + 全景对比）
- 案例：mauriceboe/Tune PR #7、kination/smoodit（DEV）
- GitHub issue：r0x0r/pywebview #353（打包体积）、tauri-apps/wry #454（同步调用不可行）
