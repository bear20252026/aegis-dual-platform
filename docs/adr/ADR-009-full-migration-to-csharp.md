# ADR-009：全功能迁移至 C#——单一正典栈终局裁决 + 迁移路线图

> 状态：已接受（2026-09-04，owner 拍板）；**执行状态：M1-M4 全部落地
> （2026-09-05——M4 真机验收待发布走查）**，终局口径见 README/CLAUDE.md｜ 关联：ADR-001（Windows 宿主）、ADR-002（broker）、ADR-007（双栈语义收敛——本 ADR 取代其 D1 的「迁移中」悬置态）、ADR-008（Rust 单一裁决源）
> 决策依据：2026-09-04 全面审计（`docs/quality-reports/full-audit-2026-09-04.md`）+ 修复批次 1-4 实证（`fix-log-2026-09-04.md`）

## 背景

ADR-001 选定 C#/.NET 10 为 Windows 宿主正典方向（宿主控制粒度/线程模型/发布面的
实质优势——全部经批次 1-4 实证确认）；ADR-007 面对现实把功能栈语义悬置为
「迁移中」。悬置的代价经四轮修复实证：每个安全修复两侧各写一份且语义漂移
（下载：Python=提示 / C#=拒绝）、发布链双轨（两个 Windows 制品）、`legacy/`
命名与事实颠倒、C# 侧功能鸿沟 ≈ 一个完整浏览器（约 7,000 行 + shell UI）
且无里程碑无度量。

**owner 决策（2026-09-04）：执行 ADR-001 原愿景至终点——全部功能迁移至 C#，
Python 栈冻结退役。本 ADR 即迁移的正式授权与执行计划。**

## 决策

### D1：终局裁决

- **C#/.NET 10 + 原生 WebView2 = 唯一 Windows 正典栈**（发布期唯一分发载体）；
- **Python 栈（`legacy/windows-pywebview/`）进入冻结期**：本 ADR 接受之日起
  **只修 P0/P1 安全缺陷，不加任何新功能**；M4 完成后整体归档（只读）；
- 目录名暂不改（CI/打包脚本/评审包路径依赖——改名作为 M4 收尾的独立 PR，
  归档时随语义一并落定）。

### D2：目标架构（C# 栈分层——三信任域在原生宿主的完整落位）

```
windows/src/Aegis.Windows.App/
├── Broker/                    # 【保留·已高质量】策略层——唯一副作用点
│   ├── BrowserPolicyBroker.cs / OriginPolicy.cs / Decision.cs
│   ├── NativePolicyCoreBridge.cs / NativePolicyCoreGate.cs（Rust FFI）
│   ├── Audit/ AuthorizedAction.cs Approval/ KillSwitch.cs
│   └──                        # 待办：KillSwitch/ApprovalManager 接线（审计遗留）
├── Contracts/Generated/       # 【保留】代码生成物（CI regenerate+diff 门禁）
├── Core/                      # 【新建】领域服务层——无 UI 依赖，全部可单测
│   ├── Tabs/                  # TabManager / Tab / SessionStore（每标签一 WebView 实例）
│   ├── Bookmarks/             # BookmarkStore(SQLite) / Chrome·Edge 导入器 / toggle
│   ├── History/               # HistoryStore + FTS5（含查看/清除——补齐 Python 缺口）
│   ├── Downloads/             # DownloadManager + DownloadPolicy（原生红利：完整下载 UI）
│   ├── Security/              # ThreatFeedUpdater / safe_url 校验 / per-origin 策略
│   ├── Settings/              # AppSettings——强类型，杜绝影子配置（每个字段必须有消费者）
│   └── SearchEngines.cs       # 与 Android SearchEngines 同语义单源
├── WebView/                   # 【扩展】HostWebView 每标签一实例
│   ├── HostWebView.cs         # 导航/新窗口/下载/权限 全经 broker（批次1 C1 已立门禁）
│   ├── WebView2Hardening.cs   # 批次1加固束原生直写：AreHostObjectsAllowed/ESM/
│   │                          #   ProcessFailed/AddScriptToExecuteOnDocumentCreated
│   │                          #   （原生 API 全可达——pywebview 天花板全部消失）
│   └── FingerprintShield.cs   # 指纹防护管道（文档创建前注入——FIX-1 原生形态）
├── Chrome/                    # 【重写】原生 WPF chrome——与页面 DOM 彻底隔离
│   ├── MainWindow.xaml        # 标签条(原生)/地址栏(焦点/选中/联想)/进度条/收藏☆
│   ├── NewTabPage/           # start.html 单源复用（SetVirtualHostNameToFolderMapping）
│   ├── ErrorPage/ DownloadUI/ SettingsUI/   # 原生错误页/下载面板/设置界面
│   └── ImportWizard/          # Chrome/Edge 导入向导（原生对话框）
└── Diagnostics/               # 审计落盘（有界）/性能基线
```

**关键架构决策**：
1. **每标签一 WebView 实例**（对齐 Android 模型）——替代 Python 单 WebView +
   JS 标签条注入，天然解决切标签丢状态/标签标题不更新两类审计缺陷；
2. **Chrome 全原生 WPF**——浏览器 UI 与页面 DOM 彻底隔离（ADR-003 的彻底版）：
   地址栏/收藏/菜单/标签条不再是注入 JS，XSS 面结构性消除；
3. **start.html 保持跨端单源**（Windows/Android 共用），经虚拟主机映射加载；
4. **数据层统一 SQLite**（Microsoft.Data.Sqlite + FTS5）——书签/历史/会话；
5. **AppSettings 强类型 + CI 诚实性门禁**——声明字段必须有消费者（对齐
   Android SearchEngines 同语义单源原则）。

### D3：迁移路线图（绞杀者模式——每里程碑有硬验收）

> 顺序原则：先骨架（可用性达标）→ 数据闭环 → 功能补齐 → 收尾退役。
> 每里程碑完成 = parity 清单逐项勾验（`docs/product/feature-parity-checklist.md`）
> + 全部门禁绿 + 真机可用性验收。

**M1 骨架可用（目标 2.2.0-beta.1）——达到「能日常浏览」**
- 多标签（新建/关闭/切换/拖拽排序；每标签独立 WebView 与会话）
- 地址栏原生交互（focus 选中/Enter 导航/加载进度条）
- 会话保存与恢复（启动自动 + 手动）
- 加固束全量原生接线（批次1清单逐项：NewWindowRequested 门禁/DownloadStarting
  经 broker/功能收紧/ESM/ProcessFailed/文档创建前注入）
- 威胁黑名单接线（订阅刷新 + 导航门禁 + 审计）
- 验收：用 C# 版连续真实浏览 1 小时（含视频/多标签/重启恢复）无阻断

**M2 数据闭环（2.2.0-beta.2）**
- 书签全量：SQLite 存储/宫格/收藏☆/Chrome·Edge 导入向导
- 历史全量：FTS5 搜索/最常访问/查看/清除（**超越** Python 栈——补齐只写不清缺口）
- 搜索引擎切换（四引擎，偏好持久化）

**M3 功能补齐（2.2.0-beta.3）**
- **下载管理器**（B 路线第一笔红利：原生 DownloadStarting→进度/暂停/安全确认 UI——
  Python 栈因 pywebview 天花板明确不支持的特性，此处原生实现）
- 新标签页（start.html 虚拟主机加载 + 书签宫格/会话恢复/导入入口接线）
- 源码查看器 / 壁纸 / 几何画板 / 贪吃蛇
- 指纹防护管道全量（FingerprintShield）

**M4 收尾退役（2.2.0 正式）**
- 设置界面（原生 SettingsUI——Python 栈 30+ 影子配置在此兑现或清除）
- KillSwitch/ApprovalManager 接线（审计遗留清零）
- Python 栈归档：目录只读、发布链移除 PyInstaller 包、README/CLAUDE.md 终版口径、
  （可选）`git mv` 目录正名
- 验收：parity 清单 100%，发布链单一 Windows 制品

### D4：迁移纪律（防「机制建了没接线」历史病灶复发）

1. **安全 parity 强制同步**：每迁一个功能，其安全门禁（broker 决策/safe_url/
   审计/加固）必须在同一 PR 接线——parity 清单含安全列，缺一不验收；
2. **Python 栈冻结纪律**：接受日起只修 P0/P1 安全缺陷（修复须同步评估 C# 侧
   是否同样存在），功能 PR 一律拒绝；
3. **每里程碑一个 PR 序列 + CHANGELOG 条目**，禁止「模糊推进」（四轮修复的
   成功经验：层次/原文件/验证/界限全部落文档）；
4. **跨端一致性机器持续运转**：golden 向量机制（批次 4 打样）覆盖到的语义
   （URL 归一化/搜索引擎表/canonicalization），C# 实现必须消费同一向量。

### D5：度量的诚实边界

- 每里程碑的真实完成以**真机可用性验收**为准（M1 的 1 小时连续浏览等），
  CI 绿是必要非充分条件——四轮修复证明「单测全绿但真机挂死」可能发生；
- 迁移期版本号：C# 产物以 `2.2.0-beta.N` 发布（用户可装可试），PyInstaller
  包继续为 stable 渠道直至 M4；
- 本 ADR 不设定具体日历日期——里程碑以交付节奏推进，但**顺序与验收标准
  不可协商**（避免重蹈「迁移无限期悬置」）。

## 后果

- 正面：宿主控制粒度全量兑现（下载管理器等 pywebview 不可实现的特性原生落地）；
  chrome 与页面 DOM 彻底隔离；发布链单轨；语义与事实重归一致；
- 代价：迁移期双维护税持续（Python 只修安全可显著压缩）；约 10,000 行 C#
  新增——以 M1→M4 分期消化，每期独立可用；
- 风险：迁移期 Python 栈冻结可能引入用户摩擦（新功能只在 beta 渠道）——
  接受，这正是迁移的压力来源（有压力才不会重蹈无限期悬置）；
- 取代关系：本 ADR D1 取代 ADR-007 D1 的「迁移中」语义；ADR-001 的方向
  在本 ADR 获得完整的执行计划与验收标准。
