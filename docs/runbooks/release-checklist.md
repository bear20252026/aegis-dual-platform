# 发布准备 Runbook（正式发布检查清单——release-checklist.md）

> 依据：蓝图阶段 E（发布链独立重建——逐工件闭合 fail-closed）+ release.yml
> （v* 标签触发——受保护 Environment）+ release/runbooks/security-release.md
> （安全发布流程）——正式发布前检查清单（供用户执行——记录——发布门禁）。

## 一、受保护环境配置（GitHub——用户操作）

- [ ] release 环境已建（Settings → Environments——已建）
- [ ] 部署规则（v* 标签触发已限死——"所有都允许"已选——可接受）
- [ ] 可选：Required reviewers（付费功能——免费账号无——可跳过——不设）

## 二、质量门禁（发布前——CI 全绿）

- [ ] Windows 构建 + 测试（contracts.yml windows-contract-build 构建+两套件单测；
  release-windows.yml build/verify 发布期复验——WB-123，2026-09-26 审计：
  原误挂 ci.yml，ci.yml 仅 UI 回归）
- [ ] Android 质量门禁（android-quality——ktlint/detekt；WB-031，审计 2026-09-23
  清单·W5 批更新：早期"远端失败待定位"已结案——A5/A6 批（8f3e889 等）完成
  4 模块 ktlint+detekt+单测+lintDebug 全绿收敛，现按常规门禁执行——失败即阻断）
- [ ] Contracts 契约测试（contracts.yml——新 CI 分层）
- [ ] Core-Rust cargo 门禁（core-rust.yml——fmt/clippy/test/audit）
- [ ] Agent 红队测试（agent-redteam.yml——redteam_test + redteam_e2e）
- [ ] Supply-Chain 依赖审计（supply-chain.yml——pip-audit/cargo audit/SBOM）
- [ ] Release 门禁（release.yml——构建 + 签名 + 逐工件闭合验证）

## 三、发布链独立验证（阶段 E——release/ 独立验证产品）

- [ ] verify_manifest（更新清单——签名阈值/防回滚/过期——P0-04 契约统一）
- [ ] verify_artifact_set（逐工件闭合——双向集合相等——缺失/哈希不符/未列明拒绝）
- [ ] verify_provenance（逐工件 gh attestation verify——固定 signer 身份）
- [ ] generate_sbom（CycloneDX——随制品存档——证据包）

## 四、发布步骤

> WB-067（审计 2026-09-23 清单·W5 批）：发布标签占位符化——示例以
> shared/version.properties / shared/release.json 当前版本为准，不再硬编码
> 已过期的 v1.0.0。

1. 质量门禁全绿 + 受保护环境配置完成
2. `git tag -a <release-tag> && git push origin <release-tag>`（如 `v2.2.0`/
   `v2.2.0-beta.N`——与 version.properties 一致；显式推标签——git push 不推标签的坑）
3. release.yml 触发（v* 标签——6 job：pin-check / release-windows /
   release-android / release-core / verify-gate / publish——失败闭合——
   无 || true/截断验证；WB-123，2026-09-26 审计更正——原误记 5 job）
4. 发布产物（Windows C#/Inno Setup 安装包 + Android APK + Rust policy DLL + SHA256SUMS.json + SBOM + provenance）
5. 证据包归档（签名/哈希/SBOM 摘要——security-release runbook——张显达实践）
6. 灰度（1% → 10% → 全量——停止条件：错误率超限即停）

## 五、回滚

- 保留上一版制品与签名（防回滚计数器——BAUER——版本单调 SemVer）
- 发布失败/事故 → `release/runbooks/security-release.md`（安全发布流程——已落地）；
  WB-068（审计 2026-09-23 清单·W5 批）：蓝图所列 incident-response runbook
  **尚未落地**（docs/runbooks 现仅 device-validation/release-checklist/
  windows-run-guide 三件）——落地前安全事件按 SECURITY.md 报告流程与
  security-release runbook 处置，本清单不指向不存在的文档
