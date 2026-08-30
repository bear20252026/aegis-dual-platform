# ADR-007：单一正典栈 + 守卫脚本单一事实源 + 门禁全量常跑

> 状态：已接受（2026-08-30）｜ 关联：ADR-001（Windows 宿主）、ADR-002（capability broker）、ADR-003（无远程 native bridge）
> 背景审查：2026-08-30 全库架构复审（PR #7 期间发现的三处系统性风险）

## 背景

复审暴露三个「架构设计与工程现实脱节」的问题：

1. **双栈正典不清**：README 声称 Windows 端为 C#/.NET 10，CLAUDE.md 声称正式入口是
   `legacy/windows-pywebview/main_webview.py`——两份权威文档指向不同的"正式栈"；
   活跃功能栈住在 `legacy/` 目录（命名与事实颠倒）；
2. **守卫脚本手工对等**：Bridge 守卫 JS 在 Rust 与 Kotlin 各自维护一份模板，
   已实际产生漂移（Kotlin 侧缺失 REQUIRE_HTTPS 段）——此前一次漂移
   （`const ALLOWED_HOSTS = "a","b"` 语法错误）曾导致整个守卫 fail-open；
3. **门禁按路径触发 = 不设防**：android-quality / contracts / core-rust /
   agent-redteam / supply-chain 五个 workflow 均带 `paths:` 过滤，未被触碰的
   子树门禁不跑——ktlint 门禁在 master 上长期 FAIL 却无人发现（直到 2026-08-30
   android/** 变更首次触发才暴露：ktlint 1.8.0 KDoc 解析 bug + 存量风格问题）。

## 决策

### D1：单一正典栈（目录不动，语义收敛）

- **目标发布栈 = C#/.NET 10 + 原生 WebView2**（`windows/`，ADR-001 方向不变）——
  发布期唯一分发载体；
- **现役功能栈 = Python + pywebview**（`legacy/windows-pywebview/`）——
  当前全部浏览器功能（标签/书签/历史/导入/会话恢复）的真实载体；
  目录名 `legacy` 为历史遗留（Qt 迁移期命名），**语义重定义为
  「现役 Python 功能栈（向 C# 迁移中）」**，目录不改（CI/脚本/评审包路径
  依赖此路径，改名风险大于收益）；
- `legacy/windows-pywebview/legacy/`（Qt）与 `legacy/ui/` 为**已归档死代码**，
  禁止从活跃代码 import（与既有红线一致）；
- README / CLAUDE.md 按本 ADR 对齐，消除"正式栈"双标。

**迁移规则**：新功能在 pywebview 栈落地时，凡涉及安全边界（导航/桥/权限）
必须以「可平移到 C# Broker」的形态实现；纯功能可先落地。

### D2：守卫脚本单一事实源（contracts 原则延伸）

- 规范模板唯一存于 `contracts/schemas/bridge_guard.template.js`
  （占位符：`__AEGIS_HOSTS__` / `__AEGIS_REQUIRE_HTTPS__`）；
- **Rust**：`bridge_guard.rs` 经 `include_str!` 编译期嵌入规范文件——消费即事实；
- **Kotlin**：内嵌副本 + 占位符插值，由
  `contracts/codegen/verify_bridge_guard.py` 做归一化逐行比对；
- **C#**：无注入 JS（走 WebView2 Settings 收紧），不在本门禁范围；
- CI（contracts.yml）运行 verify 门禁——**守卫漂移在合入前失败**，
  fail-open 类 bug（手工拷贝的产物）结构性消除；
- 规则：改动守卫语义 = 只改规范模板 + 同步 Kotlin 副本 + verify 全绿。

### D3：门禁全量常跑（区分门禁型与构建型）

- **门禁型 workflow**（android-quality / contracts / core-rust / agent-redteam /
  supply-chain / ci）移除全部 `paths:` 过滤——每次 push/PR 全量执行；
  理由：`paths:` 过滤的省时收益 << 漏检成本（ktlint 长期 FAIL 未被发现即实证）；
- **构建型 workflow**（native-policy-artifacts / release-*）保留触发过滤
  ——它们产生产物而非判定质量，按需触发合理；
- **自检入 CI**：CLAUDE.md 要求的 5 个离线自检（session_store / api_bridge /
  s1 集成 / shell_toolbar / tab_state）加入 ci.yml python-checks——
  自检与实现不一致（master 曾双 FAIL）在合入前暴露。

## 后果

- 正：权威文档不再自相矛盾；守卫漂移由 CI 结构性拦截；门禁盲区消除；
- 负：CI 分钟数上升（每次 PR 全量 14+ check）——安全性优先，接受；
- 后续：pywebview → C# 功能迁移仍按发布期路线推进（W-02/R-04 承诺不变），
  本 ADR 只收敛「哪个是正典」的口径，不改变迁移节奏。
