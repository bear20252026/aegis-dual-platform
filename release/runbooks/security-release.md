# 安全发布 Runbook（阶段 E——release/runbooks/security-release.md）

> 依据：蓝图阶段 E（发布链独立重建——逐工件闭合 fail-closed）+ 全球调研
> （gh attestation verify 官方逐工件验证/slsa-verifier/张显达失败即阻断证据包/
> BAUER cosign 签名与防回滚）——发布验证器不是 CI 可选脚本，是独立验证产品。

## 一、发布前（构建产物就绪）

1. `release/tools/generate_sbom/generate_sbom.py <manifest> <sbom.cdx.json>`
   —— 从 manifest 工件枚举生成 CycloneDX SBOM（随制品存档）
2. cosign 签名全部制品（signing-policy.yaml）：
   - `cosign sign-blob --key <key> --output-signature <f>.sig --output-certificate <f>.cert <f>`
   - SBOM 分离签名 + `sha256sum` 生成 SHA256SUMS

## 二、发布验证（独立验证产品——fail-closed——任何失败终止发布）

```bash
# 1) 更新清单验证（签名阈值/防回滚/过期——P0-04 契约统一）
release/tools/verify_manifest/verify_manifest.py <manifest.json> <trusted_keys.json> <min_version>

# 2) 逐工件闭合验证（双向集合相等——缺失/哈希不符/未列明拒绝）
release/tools/verify_artifact_set/verify_artifact_set.py dist <manifest.json>

# 3) provenance 逐工件验证（gh attestation verify——固定 signer 身份）
release/tools/verify_provenance/verify_provenance.py dist <owner> <signer_workflow>
```

- 任何工具返回非零 → **终止发布**（不允许 `|| true`、截断 head -200、跳过验证）
- SBOM 缺失/未签名 → 拒绝（CycloneDX 随制品存档——张显达）

## 三、发布后（证据包 + 回滚）

1. 签名/哈希/SBOM 摘要写入发布记录（证据包——张显达——审计可追溯）
2. 回滚保留上一版制品与签名（防回滚计数器——BAUER——版本单调 SemVer）
3. 灰度 1% → 10% → 全量（停止条件：错误率/签名校验失败率超限即停）

## 四、告警与门禁

- 签名校验失败/哈希异常 → 立即告警并生成工单（异常告警——张显达）
- 发布门禁（蓝图）：任何未列明/缺失/哈希不符/签名不符/回滚/无 SBOM/无
  provenance/工具失败 → 终止发布（不允许跳过或截断验证）
