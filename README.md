# Aegis 双端安全浏览器

Aegis 是一款**双平台安全浏览器**：Windows 端基于 C#/.NET 10 LTS + 原生 WebView2
（阶段 C——最小安全壳），Android 端基于 Kotlin + Jetpack Compose + AndroidX WebKit
（阶段 D）。以**边界驱动架构**为核心设计目标：共享安全契约（contracts）+ capability
broker（唯一副作用点）——从"补丁驱动开发"走向"边界驱动架构"（蓝图最终路线）。

> 许可证：MIT（详见 [LICENSE](LICENSE)）｜ 安全边界见 [SECURITY.md](SECURITY.md)

> **Windows 双栈现状（ADR-007）**：目标发布栈为 C#/.NET 10（`windows/`）；
> 当前全部浏览器功能（标签/书签/历史/导入/会话恢复）由**现役 Python 功能栈**
> `legacy/windows-pywebview/` 承载（目录名 `legacy` 为 Qt 迁移期历史遗留，
> 语义为「迁移中」而非「废弃」）。详见
> [ADR-007](docs/adr/ADR-007-canonical-stack-and-single-source-guards.md)。

## 架构（蓝图目标树——阶段 A-G 落地后）

```
contracts/  唯一安全协议事实来源（schemas/vectors/codegen——六类对象冻结；
            bridge_guard.template.js 为三端守卫 JS 单一事实源——ADR-007）
core/       Rust 纯策略核心（canonicalization + Ed25519 阈值验证——无 I/O）
windows/    C#/.NET 10 + 原生 WebView2（App/Chrome/WebView/Broker——能力代理）
android/    Kotlin/Compose（broker/webview-adapter/chrome-ui——状态机）
agent/      Agent/MCP 逐项复开（action-catalog——红队 fixtures——测试优先）
release/    发布链独立验证产品（逐工件闭合——fail-closed）
docs/       ADR/threat-model/runbooks/product（蓝图目标树）
.github/    CI 分层门禁（contracts/windows/android/core-rust/agent-redteam/
            supply-chain/release——8 个；ADR-007 起门禁全量常跑——无 paths 过滤）
```

**三个信任域**（ADR-002/003）：远程网页域（无 native bridge）/本地 chrome UI 域
（固定 origin）/Capability broker 域（唯一副作用点——Default Deny）。

## 构建方法

- **Windows 目标栈**（windows/src/Aegis.Windows.App）：`dotnet build`（.NET 10.0.302——0 警告）
- **Windows 现役功能栈**（legacy/windows-pywebview）：
  `python main_webview.py`（运行）；门禁：`python ../../validate_release.py` +
  `ruff check . --exclude legacy --ignore RUF001,RUF003,E501,TRY300,TRY003,TRY301,RUF021,E402,I001` +
  `bandit -r app/ -q --skip B110,B404,B603,B607` + `mypy main_webview.py app/` +
  5 个自检（`selftest_*.py`——已入 CI）
- **Rust 核心**（core/rust-policy-core）：`cargo test`（vectors 差分全绿）
- **契约代码生成**（contracts/codegen）：`python generate_csharp.py / generate_kotlin.py`
  （从 schemas 生成 C#/Kotlin 模型——不平行 Schema）+ `verify_contract_compatibility.py`
  + `verify_bridge_guard.py`（守卫 JS 单一事实源校验——ADR-007）
- **Agent 红队**（agent/tests）：`python redteam_test.py / redteam_e2e_test.py`

## 蓝图状态（aegis_future_development_and_target_source_tree.md）

- 阶段 A（ADR 五个决策）✅ → B（contracts）✅ → C（Windows 壳）✅ → D（Android）✅ →
  E（发布链）✅ → F（Rust 核心）✅ → G（Agent 复开）✅
- 发布门禁七门禁闭合 ✅（CI 分层 8 个，ADR-007 起全量常跑）｜ 文档树补全 ✅
- ~~Android 质量门禁 远端 ktlint 定位~~ ✅（2026-08-30 修复：ktlint KDoc 解析 bug
  规避 + .kts 风格修复 + detekt 存量基线化——CI 首次全绿）
- 剩余（需真实设备/用户操作）：真机验证（device-validation.md）｜
  正式发布（release-checklist.md——受保护环境 + 门禁全绿后 tag）

## 安全

见 [SECURITY.md](SECURITY.md)（三信任域边界/漏洞报告/危险 API 审查清单/依赖发布安全）。
