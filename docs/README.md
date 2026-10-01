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

## docs/audit/（历史审计归档 + 现行台账）

- **现行台账（活跃）**：`full-audit-2026-09-23-1000-items.md`（1115 项主台账）、
  `full-audit-2026-09-26-229-items.md`（第二轮 229 项报告）、
  `full-audit-2026-10-01-241-items.md`（第三轮 241 项——WB-175，2026-10-01
  审计补列：本轮六区新鲜扫描，P1×4 / P2×23 / P3×214）
- **历史归档（2026-08 双栈期，带时代横幅）**：audit-report / audit-2026 /
  audit-full-rescan-2026-09-01 / audit-search / code-audit / architecture-audit×2 /
  open-source-browser-audit×3 / security-audit-red-blue / privacy-defaults /
  dependency-audit / expert-audit-report / expert-review / apple-design-analysis

## 历史调研（原地保留 + 时代横幅，不作为现行依据）

tauri-migration-report×2、pytauri-×2、rust-desktop-landscape-2026、
tech-evolution-plan、optimization-plan、source-study-report、
browser-ecosystem-research、threat-feed-mirror-plan、obfuscation-isolation-design、
code-structure-review-2026、final-development-checklist、toolchain-plan 等——
横幅注明被取代口径（SP-060/110..123）。
