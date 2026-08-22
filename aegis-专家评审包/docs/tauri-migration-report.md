# Tauri 迁移调研报告（tauri-migration-report）

> 调研日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> 信源：中英双语（Tauri 官方文档/基准库、GitHub 项目、Reddit/HN、掘金、实测对比）
> 问题：Aegis（pywebview+WebView2 双端壳浏览器）是否值得迁移到 Tauri？

---

## 〇、结论速览

**不建议立即整体迁移。** Tauri 在包体积/内存/启动/权限模型上显著优于 pywebview，但其浏览器生态仍处实验期（Verso 已停滞、无生产级成功案例），且 Aegis 已投入的 Python 安全纵深（白名单双关口/统一拦截管线/凭据治理，25 文件 4571 行）需在 Rust 全量重做，回归风险高。**建议：保持现状 + 零成本借鉴 Tauri 理念 + 设定生态成熟触发条件。**

## 一、Tauri 2.0 官方与实测数据（核实）

| 指标 | pywebview（Python 打包） | Tauri 2.0 | 信源 |
|---|---|---|---|
| 安装包体积 | 50-200MB（PyInstaller 实测 200MB） | **~5MB**（4.8-5.2MB 实测） | r/learnpython；johal.in 2026-04 |
| 空闲内存 | 较高（GIL+解释器） | **42MB**（vs Electron 187MB） | johal.in Markdown 编辑器实测 |
| 冷启动 | 需解压解释器 | **320ms**（vs Electron 1800ms） | johal.in |
| 输入延迟 | — | 12ms（vs Electron 38ms） | johal.in |
| 权限模型 | 桥接层自建白名单 | **ACL 默认拒绝所有插件命令** + scope（deny 优先） | v2.tauri.app/zh-cn 官方文档 |
| 跨平台 | Python+Kotlin 双套 | Rust 核心 5 平台（Win/macOS/Linux/Android/iOS） | Tauri 官方 |

**注意**：Tauri 官方已明确"不再做与 Electron 的官方对比"（tauri-apps/tauri issue #14851，避免引战），上表为第三方实测（johal.in 2026-04-30）与官方基准库（tauri-apps/benchmark_results）。

## 二、Tauri 浏览器生态（核实结论：整体实验期）

| 项目 | 状态（2026-08-15 核实） | 判定 |
|---|---|---|
| **Verso**（Tauri 官方+Servo 引擎） | ✅ **已正式停止维护**（仓库归档：Servo 更新过快+人力资金有限；Tauri 转而探索 Servo 为可选渲染引擎 tauri-runtime-verso，讨论 #15235） | ❌ 不参考 |
| **CNTRL Browser**（Demon-Die + Omnikon-Org） | Tauri v2 + SolidJS；三级 AI 路由（Ollama/Gemini/Groq/OpenAI 兼容）；**Phase 1-3 完成、4-7 未完成**（半成品） | 🟡 架构借鉴（WASM 沙箱/Keychain/意图解析理念） |
| **Adaptive Browser**（★344） | Tauri v2 + React；API 驱动 UI（ui-manifest.json 动态构建界面）+ YAML 偏好分层；2026-03 创建活跃 | 🟡 理念借鉴（对应 Aegis R2 schema 方向） |
| **MCP Browser** | Tauri + Rust + 内置 MCP server（每页注入桥接脚本，agent 经 MCP 操作页面） | 🟡 与 Aegis mcp.py 理念同源 |
| **Ferrum / Agentic / donutbrowser / Minimal macOS** | 2025-2026 早期/低活跃 | ⚪ 观察 |

**结论**：**无生产级、广泛好评的 Tauri 浏览器成功案例**——生态整体处于"实验探索期"，直接照搬为时过早。

## 三、社区与媒体报道（国内外）

### 国外（Reddit/HN）
- **r/learnpython 2026-04**：开发者因 Rust 初学放弃 Tauri 选 pywebview；但 PyInstaller 打包 **200MB** 是 pywebview 明显痛点
- **HN（pytauri 讨论）**：ActivityWatch 团队从 Python+Qt 迁 Tauri（跨平台打包是 PyInstaller 最大痛点）；核心权衡 = 系统 WebView 无捆绑 Chromium 的**渲染一致性** vs 体积/内存
- **关键案例 Tune PR #7（2026-04-28）**：**pywebview+pystray+PyInstaller → Tauri 2.x + Python sidecar**（JSON-RPC stdin/stdout），前端不变仅桥从 pywebview.api 换 Tauri invoke/listen——**"解决 WebView2 init 抖动根因"**——Aegis 同类迁移的最直接参考（Sidecar 平滑过渡已验证可行）

### 国内（掘金 2026-02 WebView 全景对比）
- Tauri = "产品级交付"（脚手架/打包/签名/权限模型/插件体系系统化），代价 Rust 学习曲线 + 前后端边界设计成本
- pywebview = "把 WebView 变成 Python GUI 容器"，Python 业务快/AI 集成顺滑，挑战是打包分发/多平台一致性/复杂桌面能力自补
- 6 问题选型框架：产品级交付 vs 内部工具；体积冷启动 vs 渲染一致性；后端语言是否承担安全边界
- 社区判断："C 端轻量工具 → Tauri；内部工具 → pywebview/Electron"；"Tauri 取代 Electron 的前提是 Rust 成为前端标配（5 年内不会）"

## 四、Aegis 迁移成本收益矩阵（理性评估）

### 收益（若迁移）
1. 包体积 50-200MB → ~5MB（政府内网部署下载快）
2. 内存/启动/延迟显著改善（42MB/320ms/12ms 实测）
3. ACL 默认拒绝权限模型（比自建白名单更系统化）
4. Rust 核心五平台复用（若未来扩展 macOS/Linux/iOS）

### 成本与风险（决策主导项）
| 项 | 详情 |
|---|---|
| **业务重写** | api_bridge/nav_queue/security 等 25 文件 4571 行 + Android Kotlin 10 组件全量 Rust 重写 |
| **安全纵深重建** | 白名单双关口/统一拦截管线（_apply_request_policy）/凭据治理/Esm per-origin 均需 Rust 重做——**回归风险** vs 当前已审计 A- 全绿状态 |
| **生态实验期** | 无生产级 Tauri 浏览器案例；Verso 停滞证明"Rust 内核+WebView 壳"路线仍不成熟 |
| **团队成本** | Rust 学习曲线（AI 辅助仍慢于 JS/Python，编译 30s+ 起步——掘金观点） |
| **政府项目约束** | 当前 30 提交、全量验证全绿、KNOWLEDGE_BASE 8 节知识沉淀——重写将丢弃或需迁移全部 |

### 关键判断
- **架构理念同源**：Tauri 也是"壳"（系统 WebView），与 Aegis 双端同源壳**本质一致**——迁移是"换壳语言"而非"换架构"，收益主要在工程指标（体积/内存）而非架构层面
- **Aegis 已具备 Tauri 的核心优势点**：js_api 白名单 ≈ ACL 默认拒绝理念；NavQueue ≈ 异步消息驱动；mcp.py ≈ MCP Browser 同理念——**Tauri 的亮点 Aegis 已在 Python 栈实现了等价物**
- **Tune 案例启示**：若未来确实要迁，**Sidecar 模式**（Tauri 壳 + Python 业务侧车）是最平滑路径（前端不变、业务保留、仅壳层换），非全量重写

## 五、建议（理性结论）

1. **立即（零成本借鉴）**：
   - Tauri ACL"默认拒绝 + scope deny 优先"理念 → 复核 Aegis js_api 白名单与威胁拦截的 deny 优先级（FreeDom 已提白名单覆盖黑名单，Tauri scope deny 优先可对照）
   - CNTRL WASM 插件沙箱 → 对应第 8 节 Wasm 插件新方向（远期）
   - Adaptive API 驱动 UI → R2 schema 标准化已做 mcp 部分（可扩展）
2. **中期（跟踪条件）**：Tauri 浏览器生态出现生产级成功案例 / CNTRL 完成 Phase 4-7 / 团队 Rust 能力具备 → 再评估 **Sidecar 平滑过渡**（Tune 已验证可行）
3. **长期（保持）**：Aegis 维持 Python+pywebview 栈（已成熟全绿），持续吸收 Tauri 生态理念而非迁移

## 六、信源清单

- Tauri 官方：v2.tauri.app/zh-cn/security + /reference/acl（权限模型）、tauri-apps/benchmark_results（官方基准）、github.com/tauri-apps/tauri issue #14851（官方对比态度）、discussion #15235（Servo 探索）
- 实测：johal.in（Tauri 2.0 vs Electron 30 Markdown 编辑器，2026-04-30）
- 生态：github.com/versotile-org/verso（停滞声明）、Demon-Die/CNTRL、Omnikon-Org/CNTRL、jonnonz1/adaptive-browser、MauricioPerera/mcp-browser
- 社区：Reddit r/Python + r/learnpython（2025-08/2026-04）、HN item 45512962（pytauri）、掘金 7605128056485953551（WebView 全景对比 2026-02）
- 案例：github.com/mauriceboe/Tune PR #7（pywebview→Tauri sidecar 迁移）

---

## 七、深化：大胆求索路径（2026-08-15 补充调研）

> 补充信源：pytauri（★1410/v0.8.0/2026-08-14 活跃）、Tauri 官方 sidecar 文档（v2.tauri.app/develop/sidecar 2026-06）、Tauri 2.11.5（2026-07 移动端多窗口）、DataZen（2026-08-07 <10MB AI+MCP 实证）、掘金 Electron vs Tauri 2026-05

### 7.1 关键新发现：pytauri（大胆求索的核心备选）

- **pytauri/pytauri ★1410 / v0.8.0（2025-09-02）/ 2026-08-14 活跃**：Tauri 的 Python 绑定（pyo3 桥）
- **standalone 模式**：`fn main` 主线程启动 Python 解释器 + Tauri（tauri-cli 分发 libpython）——**全部 Python 业务保留，仅换壳为 Tauri**（比 sidecar 更平滑：同进程、无进程通信开销）
- **风险（HN 讨论）**：pyo3 异步生态不成熟——async 勿跨 FFI 边界（IPC 特例已单独支持）
- **验证入口**：examples/tauri-app 演示可跑（官方仓库）

### 7.2 三方面路径详细动作（大胆求索、小心验证）

**🔵 立即（零成本借鉴，本周可启动）**
1. ACL"deny 优先"复核 Aegis 白名单：黑名单命中须优先于白名单放行（对照 Tauri scope deny 优先 + FreeDom 白名单覆盖黑名单语义）
2. 威胁请求头标记强化：`_apply_request_policy` 已落地，补 deny 语义自检
3. WASM 沙箱理念评估（CNTRL：WASI 受限 syscall + JS Web Worker 沙箱 fetch 移除/无动态 import/env 注入 secrets）→ 对应第 8 节 Wasm 插件新方向
4. DataZen 实证借鉴（Tauri v2 + AI + MCP <10MB）→ Aegis mcp.py Agent 友好对照

**🟡 中期（条件满足时启动，Sidecar 或 pytauri）**
- 条件：生态出现生产级 Tauri 浏览器案例 / CNTRL 完成 Phase 4-7 / 团队 Rust 就绪
- 路径 A：**Tauri sidecar**（官方文档：externalBin+target-triple、shell:allow-execute、Command.sidecar；Tune 案例已验证 pywebview→sidecar 平滑，前端不变仅换桥）
- 路径 B（首选备选）：**pytauri**（Python 业务全保留换 Tauri 壳，同进程无通信开销）
- 验证：**PoC 三关实测**（体积/内存/启动 vs 现有 pywebview 基线）不过关不迁移

**⚪ 长期（持续进行）**
- 维持 Python+pywebview 栈（30 提交/审计 A-/全绿验证/安全纵深已沉淀）
- 每季度复核 Tauri 生态（CNTRL 完成度/生产级案例/DataZen 类实证积累）
- 移动端观察：Tauri 2.11.5 移动端多窗口 + iOS/Android IPC 死锁修复（Aegis Android 端 Kotlin 原生可借鉴经验）
