# 发布威胁模型（release-threat-model.md）

> 依据：蓝图 docs/threat-model/release-threat-model + 阶段 E（release/ 独立验证
> 产品——逐工件闭合 fail-closed）+ 全球调研（gh attestation verify 官方逐工件/
> slsa-verifier/张显达失败即阻断证据包/BAUER cosign 签名与防回滚）。

## 威胁面（发布/供应链）

| 威胁 | 缓解（已落地——阶段 E + P0-04/05/06） |
|---|---|
| 供应链投毒（依赖/工具链） | supply-chain.yml（pip-audit/cargo audit/SBOM）+ requirements-lock/Cargo.lock 锁定 |
| 签名伪造/阈值不足 | cosign keyless（certificate-identity 固定）+ 阈值签名（TUF——verify_manifest——重复 keyid 只计一次） |
| 工件缺失/哈希不符/未列明 | verify_artifact_set（逐工件闭合——双向集合相等——fail-closed） |
| provenance 缺失/伪造 | verify_provenance（gh attestation verify 逐工件——固定 signer 身份） |
| 版本回滚 | 防回滚（SemVer 单调——P0-04）+ 防回滚计数器（BAUER） |
| 验证跳过/截断（|| true/head -200） | 发布门禁（无截断扫描/无忽略失败/无人工覆盖——阶段 E + P0-06） |

## 完成标准（蓝图阶段 E）

- 任何未列明/缺失/哈希不符/签名不符/回滚/无 SBOM/无 provenance/工具失败 → 终止发布
- release.yml 对全部失败闭合（不允许跳过或截断验证）
