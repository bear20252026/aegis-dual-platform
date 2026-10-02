# docs/ 索引（SP-127，审计 2026-09-23 清单·SP1 批）

> 本目录此前散落 15+ 份带日期的历史报告（SP-059/124/125/126）——已归置
> `docs/audit/`；调研期文档加时代横幅（SP-060/110..123）。现行口径入口：
> [architecture-overview.md](architecture-overview.md) ｜ [ADR-009](adr/ADR-009-full-migration-to-csharp.md) ｜ [CLAUDE.md](../CLAUDE.md)。

## 现行口径（活跃维护）

| 文件/目录 | 内容 |
|---|---|
| [architecture-overview.md](architecture-overview.md) | 架构全景（单源 UI 树/分层/信任域） |
| [adr/](adr/README.md) | 架构决策记录（ADR-001..009 + 索引） |
| [product/](product/) | 功能 parity 清单、supported-features、隐私默认值 |
| [runbooks/](runbooks/) | device-validation / release-checklist / windows-run-guide（WB-162，2026-10-01 审计补列——原行漏列 windows-run-guide） |
| [release/](release/) | AegisSetup-CSharp.iss（Inno Setup 安装脚本，版本运行时注入）、b4-enable-notes（带时代横幅）、agent-sitemap.example.json、安装器素材（WB-161，2026-10-01 审计对齐实物——发布链设计见上级 [release-workflow-design.md](release-workflow-design.md)，security-release runbook 在仓库根 `release/runbooks/security-release.md`，均不在本目录） |
| [threat-model/](threat-model/) | 信任边界（按端分列） |
| [compat-baselines/](compat-baselines/) | 兼容基线（CI 生成、artifact 存档） |
| [quality-reports/](quality-reports/) | 2026-08-14/15 双栈期工具扫描快照（pyscn / skylos / valknut / repo-health / hotspottriage——旧扫描机绝对路径已失效，仅溯源）+ full-audit-2026-09-04（带历史横幅）+ fix-log（WB-162，2026-10-01 审计改述——原行仅列三工具名，未注明快照性质与其余内容） |
| [audit/](audit/) | **全部历史审计报告 + 历轮总台账**（见下） |
| [KNOWN_DEFECTS](../tests/KNOWN_DEFECTS.md)→[../tests/](../tests/) | 已知缺陷库与测试分层 |
| [KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md) | 工程知识库（经验教训/工具链/发布口径台账——WB-200，2026-10-02 审计补行：现行表此前漏列本文档） |
| 设计文档组（WB-200 补行——此前失联未索引） | [code-signing-design.md](code-signing-design.md)（代码签名）｜[ffi-architecture-design.md](ffi-architecture-design.md)（FFI 架构）｜[inv05-delivery-chain-design.md](inv05-delivery-chain-design.md)（交付链）｜[release-workflow-design.md](release-workflow-design.md)（发布链设计）｜[threat-context-design.md](threat-context-design.md)（威胁上下文）｜[refactor-final-route.md](refactor-final-route.md)（重构终局路线） |

## docs/audit/（历史审计归档 + 现行台账）

- **现行台账（活跃）**：`full-audit-2026-09-23-1000-items.md`（1115 项主台账）、
  `full-audit-2026-09-26-229-items.md`（第二轮 229 项报告）、
  `full-audit-2026-10-01-241-items.md`（第三轮 241 项——WB-175，2026-10-01
  审计补列：本轮六区新鲜扫描，P1×4 / P2×23 / P3×214）
- **历史归档（2026-08 双栈期，带时代横幅）**：audit-report / audit-2026 /
  audit-full-rescan-2026-09-01 / audit-search / code-audit / architecture-audit×2 /
  open-source-browser-audit×3 / security-audit-red-blue / privacy-defaults /
  dependency-audit / expert-audit-report / expert-review / apple-design-analysis
- **历史全仓审计（WB-199，2026-10-02 审计补列——本清单此前漏列该轮）**：
  `full-audit-2026-09-07-200-items.md`（首轮 200 项全仓审计，已闭环）

## 历史调研（原地保留 + 时代横幅，不作为现行依据）

tauri-migration-report×2、pytauri-×2、rust-desktop-landscape-2026、
tech-evolution-plan、optimization-plan、source-study-report、
browser-ecosystem-research、threat-feed-mirror-plan、obfuscation-isolation-design、
code-structure-review-2026、final-development-checklist、toolchain-plan——
横幅注明被取代口径（SP-060/110..123）；其余失联调研/评审件一并点名
（WB-200，2026-10-02 审计）：code-quality-assessment、pytauri-capabilities-mapping、
pytauri-migration-technical-plan、review-and-hardening-2026-08-28、
security-testing-guide、uniffi-integration-technical-plan。
