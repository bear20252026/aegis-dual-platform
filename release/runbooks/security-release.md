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

> **SP-136（审计 2026-09-23 清单·SP1 批）签名双轨说明**：上面是**密钥轨道**
> （key-based cosign sign-blob——签 `.sig`/`.cert` 分离文件，适用于本地
> 发布验签）；**keyless 轨道**由 GitHub Actions OIDC 承担——workflow 内
> `gh attestation` 产出/验证 provenance（身份绑定 `--signer-workflow`，见
> 第二节第 3 步），无需管理长期密钥。两条轨道并存：制品签名走密钥轨道，
> 溯源（provenance）走 keyless 轨道——任一缺失都按门禁拒绝。

## 二、发布验证（独立验证产品——fail-closed——任何失败终止发布）

```bash
# 0) 制品签名验证（cosign verify-blob——对应第一节密钥轨道签名，SP-032 补）
cosign verify-blob --key <key.pub> --signature <f>.sig --certificate <f>.cert <f>

# 1) 更新清单验证（签名阈值/防回滚/过期——P0-04 契约统一；min_version 传
#    已发布最低版本，如 2.2.0——低于它即判回滚拒绝）
release/tools/verify_manifest/verify_manifest.py <manifest.json> <trusted_keys.json> <min_version>

# 2) 逐工件闭合验证（双向集合相等——缺失/哈希不符/未列明拒绝）
release/tools/verify_artifact_set/verify_artifact_set.py dist <manifest.json>

# 3) provenance 逐工件验证（gh attestation verify——固定 signer 身份）
release/tools/verify_provenance/verify_provenance.py dist <owner> <signer_workflow>

# 4) SBOM 签名验证（SBOM 与制品同一密钥轨道——SP-033 补承载命令）
cosign verify-blob --key <key.pub> --signature <sbom.cdx.json>.sig <sbom.cdx.json>
```

- 任何工具返回非零 → **终止发布**（不允许 `|| true`、截断 head -200、跳过验证）
- SBOM 缺失/未签名 → 拒绝（CycloneDX 随制品存档——张显达；验证承载即上
  述第 4 步命令——签名不符同样终止发布）

## 三、发布后（证据包 + 回滚）

1. 签名/哈希/SBOM 摘要写入发布记录（证据包——张显达——审计可追溯）
2. 回滚保留上一版制品与签名（防回滚计数器——BAUER——版本单调 SemVer）
3. 灰度 1% → 10% → 全量（停止条件：错误率/签名校验失败率超限即停）
   —— **SP-080（审计 2026-09-23 清单·SP1 批）**：灰度当前**无自动化承载**，
   由发布负责人在 GitHub Release 可见性/分发渠道侧**手动**执行并记录
   （每档位停留与指标快照写入发布记录——证据包可追溯）。

## 四、告警与门禁

- 签名校验失败/哈希异常 → 立即告警并生成工单（异常告警——张显达）
- 发布门禁（蓝图）：任何未列明/缺失/哈希不符/签名不符/回滚/无 SBOM/无
  provenance/工具失败 → 终止发布（不允许跳过或截断验证）
