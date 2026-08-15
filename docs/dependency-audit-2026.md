# Aegis 依赖审计 + SBOM 报告（dependency-audit-2026）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> B 级下一阶段（B3：依赖审计 + SBOM）——先全球调研后落地

## 一、调研依据（全球多平台）
- 英文：PyPI 官方（PEP 740 签名 attestation/Sigstore keyless）+ Safeguard 指南（Trusted Publishing/SBOM/依赖 hash 固定 + build/publish 分离）
- 中文：张显达（锁文件完整哈希/重现构建/SBOM CycloneDX 随制品存档/部署侧签名强校验）
- 开源工具（均已核实活跃）：pip-audit ★1345（依赖漏洞审计）/cyclonedx-python-lib ★114（SBOM 生成）/sigstore-python ★334（签名验证）

## 二、依赖审计结果（pip-audit，requirements.txt）

**✅ No known vulnerabilities found——Aegis 当前依赖无已知漏洞**
- 扫描对象：windows/aegis_source/requirements.txt（全依赖树）
- 工具：pip-audit（pypa 官方，★1345）

## 三、SBOM 存档

- **docs/sbom-aegis-2026.json**（CycloneDX 格式）——随制品存档（供应链透明）
- 工具：cyclonedx-bom（CycloneDX 官方）
- 后续：每次发布重新生成 SBOM + 依赖差分报告随 PR（防镜像腐烂/供应链投毒）

## 四、B 级后续（记录）
- B1 混淆隔离（PyArmor+Nuitka——兼容细节已调研：restrict_module=0 + include-package + 非 trial 版）——设计文档待启动
- B2 代码签名（sigstore-python 或 KMS——调研已就绪）——发布期
- B4 独立 release workflow（build/publish 分离）——与 B3/B2 配套
