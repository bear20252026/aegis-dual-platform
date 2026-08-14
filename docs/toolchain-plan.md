# Aegis 工具链适配建议（toolchain-plan）

> 编制日期：2026-08-15 ｜ 交叉核验版（2026-08-15 复核，纳入新增证实的工具）
> 级别：国家项目 / 专家级
> 依据：中英双语联网调研（2025-08 – 2026-08，GitHub/官方/权威技术站/DEV 社区）+ gh 逐一核实
> 目标：从候选工具中筛选最适合 Aegis（双端同源壳浏览器）的组合，分阶段落地

---

## 〇、候选工具核实总表（2026-08-15 交叉核验版）

### Python 端

| 工具 | 仓库 | 核实 | 状态/活跃度 | 定位 |
|---|---|---|---|---|
| pylyzer | mtshiba/pylyzer | ✅ 真实 | ★2860 / 2026-08-10 | Rust 静态分析器（快 100 倍宣称） |
| pyrefact | OlleLindgren/pyrefact | ✅ 真实 | PyPI v100 / MIT | 规则驱动自动重构 |
| python-code-quality | rhiza-fr/py-cq | ✅ 真实 | PyPI 名 python-code-quality，CLI=`cq` | 11 工具聚合评分 + LLM prompt + CI gate |
| pyscn | ludo-technologies/pyscn | ✅ 真实 | ★1017 / PyPI 1.25.0 (2026-07-01) | Go+tree-sitter：CFG 死代码/克隆/CBO/圈复杂度 + HTML/A-F + MCP + GitHub Bot |
| PyRustor | loonghao/PyRustor | ✅ 已证实 | ★7 / 2026-01-30 | Rust 编写，基于 Ruff 解析器（星少） |
| Refactron | Refactron-ai/Refactron_lib | ✅ 已证实 | ★6 / 2026-05-14 | 官方组织 Refactron-ai（星少） |

### Android 端

| 工具 | 仓库 | 核实 | 状态 | 定位 |
|---|---|---|---|---|
| ktlint | ktlint/ktlint | ✅ 真实 | ★6732 / 1.8.0 / 2026-08-14 | Kotlin 风格强制 + 自动修复 |
| detekt | detekt/detekt | ✅ 真实 | ★7027 / v1.23.8 / 2026-08-14 | Kotlin 代码异味/复杂度 + 基线文件 |
| Qodana | JetBrains/qodana-cli（★238，Go）+ qodana-action（★308） | ✅ 已证实 CLI | 2026-08-14 活跃 | JetBrains CI 质量平台（商业；CLI/Action 开源） |
| Android Lint | AOSP tools/base | ✅ 已用 | AGP 9.3.1 lintDebug 通过 | Kotlin/Java/XML 正确性/性能/安全 |

### pywebview 专用 + AI 审查 + 跨端

| 工具 | 仓库 | 核实 | 状态 | 定位 |
|---|---|---|---|---|
| pywebview 调试 | npm `webview-devtools-mcp`（ilharp/webview-devtools-mcp） | ✅ 已证实 | 基于 chrome-devtools-mcp+chii | target.js 注入连接 MCP：截图/DOM/console/脚本/WebMCP；**注：npm 包名与用户所列 pywebview-devtools-mcp 略有出入** |
| ChatDBG | plasma-umass/ChatDBG | ✅ 真实 | PyPI v1.0.1 | AI 调试集成 pdb/lldb/gdb（`why` 问根因） |
| Open Code Review | alibaba/open-code-review | ✅ 真实 | 2026-07-01 加 MCP (#212) | 规则引擎 + LLM 双引擎，行级评审 |
| diffray | strelov1/diffray | ✅ 真实 | ★23 / 2026-07-26 / npm i -g diffray | 终端多智能体审查 CLI |
| mobile-repo-doctor | npm 包 + Mavoryl/mobile-repo-doctor-action | ✅ 已证实 | 160+/118 检查 / 2026-03 起活跃 | 0-100 健康分 + A-F + 四轴（Size/Speed/Stability/Hygiene）+ **全本地无遥测** |
| Skylos | duriantaco/skylos | ✅ 已证实 | ★537 / 2026-08-14 / 官网 skylos.dev | 开源 PR 扫描器（死代码/安全/机密/质量退化） |
| Valknut | sibyllinesoft/valknut（nathanricedev 镜像不存在） | ✅ 真实 | ★67 / Rust / 2026-08-12 | 结构启发式 + AST 复杂度 + 文档审计 + MCP |

## 一、筛选原则（国家项目视角）

1. **真实 + 活跃**：仅采纳已核实存在且近期更新的工具（Evergreen 2 周节奏下更需活跃维护）
2. **互补不重叠**：Aegis 已有 ruff/bandit/mypy + AGP lintDebug——新工具须补缺口而非重复
3. **CI 可集成 + 离线可用**：政府内网环境优先本地/自托管能力
4. **风险可控**：AI 工具仅辅助（人工复核），自动改码工具慎用

## 二、采纳组合（分阶段）

| 阶段 | 工具 | 落地动作 | 价值 |
|---|---|---|---|
| 🔴 P0 基础防线（立即） | **ktlint 1.8.0 + detekt v1.23.8** | Android 端接入 Gradle 插件；detekt 首跑生成基线；接入 CI（compat.yml 或新 job） | 补上 Android 风格/异味检查（当前仅 AGP lint） |
| 🟡 P1 深度架构（每周） | **pyscn**（★1017） | `pyscn analyze .` 产 HTML/A-F 报告；CI 每周跑；可选 GitHub Bot 自动 PR 审查 | Python 架构层监控（循环依赖/死代码/耦合），服务"结构审计"目标 |
| 🟢 P2 AI 辅助（PR 流程） | **alibaba/open-code-review（OCR）** | 本地 CLI 审查 PR diff；规则引擎先行、LLM 可选（内网无 LLM 时退纯规则） | 大厂验证的行级评审，辅助人工 |
| 🔵 P3 专项调试（疑难） | **pywebview-mcp** + **ChatDBG** | 疑难场景启动 pywebview-mcp（Launch/Attach）；ChatDBG 用于 pdb 问答根因 | 直接服务 pywebview+WebView2 调试痛点 |

## 三、观察/可选（按需评估）

| 工具 | 评估点 | 触发条件 |
|---|---|---|
| pylyzer | 与 mypy 重叠；若 Python 库膨胀可用其加速 | 代码量显著增长时 |
| python-code-quality/py-cq | 11 工具聚合评分；可作 CI 门禁补充（但 ruff/bandit/mypy 已覆盖主体） | 需要统一评分看板时 |
| Qodana | 商业平台；JetBrains 生态一致；需评估内网部署/许可 | 有 JetBrains 许可时 |
| Valknut / diffray | 与 pyscn/OCR 功能重叠；星少 | pyscn/OCR 不满足时备选 |

## 四、不采纳（交叉核验后修正）

- **PyRustor**（★7）/ **Refactron**（★6）：已证实存在但星极少、社区小，风险收益比低 → 观察不采纳
- **pyrefact**：自动改码风险高，国家项目慎用（如需，仅按 diff 人工复核后小范围试）
- **nathanricedev/valknut**：镜像不存在（主仓库 sibyllinesoft/valknut 为准）

## 五、交叉核验后的采纳组合微调

交叉核验新增两项候选评估（此前未证实）：

| 工具 | 交叉核验发现 | 采纳判定 |
|---|---|---|
| **mobile-repo-doctor** | 160+ 检查、0-100 分+A-F、四轴、**全本地无遥测**（政府内网友好）、GitHub Action 现成 | 🟡 **提升为 P1 候选**：与 pyscn 互补（移动端健康扫描 + Python 架构），CI 门禁（fail-on: high/score-below-70） |
| **Skylos**（★537） | 开源 PR 扫描器（死代码/安全/机密/质量退化），2026-08-14 活跃 | 🟢 P2 候选：与 OCR 并列（OCR 侧重 LLM 行级评审，Skylos 侧重确定性扫描），可二选一或并行 |

**最终采纳组合（交叉核验版）**：
- 🔴 P0：**ktlint + detekt**（Android 风格/异味，立即）
- 🟡 P1：**pyscn**（Python 架构，每周）+ **mobile-repo-doctor**（移动端健康，CI 门禁）
- 🟢 P2：**Open Code Review（OCR）** + **Skylos**（PR 扫描，规则确定性优先）
- 🔵 P3：**webview-devtools-mcp**（pywebview+WebView2 疑难调试，target.js 注入零改源码）+ **ChatDBG**（pdb 问答）
- ⚪ 观察：pylyzer / py-cq / Qodana / Valknut / diffray / PyRustor / Refactron

## 六、落地顺序与文件映射

```
P0: android/app/build.gradle.kts 加 ktlint/detekt 插件
    → ktlint 0 错误 / detekt 基线生成
    → .github/workflows 增加 android-quality job
P1: CI 每周 pyscn analyze . → docs/quality-reports/ 归档
P2: 本地 OCR 配置（~/.opencodereview/config.json，MCP 白名单）
P3: 疑难时启动 pywebview-mcp（无需改应用源码）
```

## 七、约束

- 所有新增工具进 CI 前先本地验证；不破坏现有 ruff/mypy/bandit/selftest 门禁
- AI 工具（OCR/ChatDBG）仅辅助、结果人工复核，不自动合入
- 新工具版本锁定（pip/gradle 版本固定），内网离线可复现
