# docs/ 索引（SP-127，审计 2026-09-23 清单·SP1 批）

> 本目录此前散落 15+ 份带日期的历史报告（SP-059/124/125/126）——已归置
> `docs/audit/`；调研期文档加时代横幅（SP-060/110..123）。现行口径入口：
> [architecture-overview.md](architecture-overview.md) ｜ [ADR-009](adr/ADR-009-full-migration-to-csharp.md) ｜ [CLAUDE.md](../CLAUDE.md)。

## 现行口径（活跃维护）

| 文件/目录 | 内容 |
|---|---|
| [architecture-overview.md](architecture-overview.md) | 架构全景（单源 UI 树/分层/信任域） |
| [adr/](adr/README.md) | 架构决策记录（ADR-001..009 + 索引） |
| [product/](product/) | 功能 parity 清单、supported-features |
| [runbooks/](runbooks/) | device-validation / release-checklist |
| [release/](release/) | 发布链设计、AegisSetup-CSharp.iss、runbooks（security-release） |
| [threat-model/](threat-model/) | 信任边界（按端分列） |
| [compat-baselines/](compat-baselines/) | 兼容基线（CI 生成、artifact 存档） |
| [quality-reports/](quality-reports/) | 静态质量工具报告（pyscn/skylos/valknut） |
| [audit/](audit/) | **全部历史审计报告 + 两轮总台账**（见下） |
| [KNOWN_DEFECTS](../tests/KNOWN_DEFECTS.md)→[../tests/](../tests/) | 已知缺陷库与测试分层 |

## docs/audit/（历史审计归档 + 现行台账）

- **现行台账（活跃）**：`full-audit-2026-09-23-1000-items.md`（1115 项主台账）、
  `full-audit-2026-09-26-229-items.md`（第二轮 229 项报告）
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
