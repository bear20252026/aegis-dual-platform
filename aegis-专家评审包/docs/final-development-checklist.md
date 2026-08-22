# Aegis 最终版开发项目清单（final-development-checklist）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> 汇总：两份专家审计意见（"锦上添花"5 条 + "终极堡垒"4 行动项）
> + 全球调研（混淆隔离方案：PyArmor master-obf 分支/CSDN 分离结构）
> + 我的想法（模块化混淆隔离架构——用户核心关切：混淆与源码完全隔离）
> 原则：开发阶段不做对开发不利的事——开发/发布严格分离，混淆随时可去

---

## 〇、分级总览

| 级 | 定位 | 项数 | 开发影响 |
|---|---|---|---|
| **A 开发期** | 零影响，可立即/近期做 | 7 项 | 零 |
| **B 发布期** | 隔离架构（发布流程内） | 4 项 | 零（开发保持源码） |
| **C 观察** | 前瞻跟踪 | 3 项 | 零 |

## 一、A 级：开发期优化项（零影响，按优先级）

| # | 项 | 来源 | 说明 |
|---|---|---|---|
| A1 | **Android System WebView 版本检查** | 专家①② | 提示/强制更新（CVE-2026-12438 沙箱逃逸、CVE-2026-11295 提权） |
| A2 | **消息来源验证**（Source 属性） | 专家② | 处理 WebView2 消息前检查 Source——防 spoofing（CVE-2026-33118） |
| A3 | **ESM API 核对** | 专家② | EnhancedSecurityModeState（2026-05 API 更新）——Aegis 已在用 ✅ 确认 |
| A4 | **按来源动态 CoreWebView2Settings** | 专家①② | 非信任站点禁用 AreHostObjectsAllowed/IsWebMessageEnabled 等 |
| A5 | **Agent 细粒度控制**（mcp） | 专家①② | 工具调用审计/数据范围/防提示词注入（ceLLMate 理念） |
| A6 | **浏览器沙箱定位文档化** | 专家① | "安全沙箱"叙事（浏览器即边界） |
| A7 | **OpenSSF pyscg 对照** | 专家② | Python 安全编码金标准（2026-05 首版）逐条对照 |

## 二、B 级：发布期加固项（隔离架构，开发零影响）

| # | 项 | 来源 | 说明 |
|---|---|---|---|
| B1 | **混淆隔离架构** | 专家①（PyArmor/Nuitka）+ 调研 + 我的想法 | 见下节（用户核心关切） |
| B2 | **代码签名** | 专家①② | 行业标准/防 AV 误报（2026 强制要求） |
| B3 | **依赖审计 + SBOM** | 专家② + 调研 | pywebview 6 项低优先级建议；SBOM 持续监控 |
| B4 | **独立 release workflow** | 调研 | 发布/部署独立 workflow + 产物保留策略 |

### B1 混淆隔离架构（模块化、随时可去、开发零影响）

```
开发分支 master（现状不变）：源码解释运行 + 全绿门禁
发布流程（独立 release 分支/CI 步骤）：
  ├─ 核心敏感模块（security/credential_guard/mcp）→ Nuitka 编译 .pyd
  ├─ 其余模块 → PyArmor 混淆（--exclude 核心，RFT 模式适配）
  ├─ dist/ 产物与 src/ 隔离 + 原始源码备份（可逆）
  └─ B2 代码签名（防 AV 误报）
可逆保证：发布不用混淆即回源码分发（master-obf 分支丢弃即可）
```

**隔离依据（全球调研）**：
- 英文（PyArmor 官方 2.9 CI）：master-obf 分支方案——混淆存独立分支，源码分支不变
- 中文（CSDN 2026-03）：分离项目结构（Nuitka 核心 + PyArmor 其余 + 构建脚本自动化 + 源码备份）
- 组合性：PyArmor 混淆后脚本可再被 Nuitka 编译（restrict_module=0，v9.0.8+ 修复授权）

## 三、C 级：观察项（前瞻跟踪）

| # | 项 | 来源 |
|---|---|---|
| C1 | SRI（静态资源完整性） | 专家② |
| C2 | ceLLMate 式 Agent 沙箱框架 | 专家② |
| C3 | Edge 进程隔离策略（OriginKeyedProcessesEnabled/ProcessIsolationEnabled） | 专家② |

## 四、执行纪律（政府级）

1. **A 级**：逐项设计先行 → 零风险门禁 → 全量回归 → 推送
2. **B 级**：发布流程独立（release 分支/CI）——**开发主分支永远源码**（混淆可逆保证）
3. **C 级**：季度复核跟踪
4. 每项落地后更新 KNOWLEDGE_BASE（项目记忆）

## 五、信源清单（全球覆盖）

- PyArmor 官方文档（2.9 CI Pipeline / 2.10 Third-Party）——master-obf 隔离方案
- Nuitka 官方（★15087，2026-08-14 活跃）
- DEV Community（2026-06-01：PyArmor vs Nuitka 实践指南）
- CSDN 文库（2026-03-13：PyArmor+Nuitka 组合技术指南——分离结构）
- AtomGit/GitCode（PyArmor+Nuitka 授权兼容）
- 专家意见①②（浏览器即边界/终极堡垒）
