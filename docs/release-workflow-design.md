# B4 独立 Release Workflow 设计（release-workflow-design）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> final-development-checklist B4（独立 release workflow——build/publish 分离
> + B1 混淆/B2 签名/B3 SBOM 集成 + 产物保留）
> 依据：全球调研（中英全覆盖）——GitHub Actions 官方（artifact 保留策略）+
> hironow ADR 0014（OIDC Trusted Publishing/build→publish 线性化/受保护环境/
> 最小权限）+ Shaken Fist release 六步（环境审批/Sigstore 签名/Trusted
> Publishing/受保护 v* 标签）+ 中文 Tag 触发发布（SHA256/gh CLI）+ vibebiao
> TIL（CI 与签名分离）

---

## 〇、结论速览

**独立 release workflow（release.yml，v* 标签触发）**——发布专属、与 ci.yml 分离：**build（含 B1 混淆 + B3 SBOM）→ sign（B2 签名 + SHA256）→ publish（受保护环境审批 + OIDC Trusted Publishing）**三 job 线性化 + 产物保留策略 + 最小权限。开发门禁（ci.yml）不受影响。

## 一、Workflow 设计（三 job 线性化）

```yaml
# .github/workflows/release.yml —— 发布专属（v* 标签触发，与 ci.yml 分离）
on:
  push:
    tags: ['v*']

jobs:
  build:                     # Job 1：构建（干净环境）
    runs-on: windows-latest
    steps:
      - checkout
      - B1 混淆隔离产物：master-obf 分支产物（Nuitka 核心 .pyd + PyArmor 混淆其余）
      - B3 SBOM 生成：cyclonedx → sbom.json（随产物存档）
      - upload-artifact@v4: release-dist（retention-days: 90——可审计）

  sign:                      # Job 2：签名（CI/签名分离理念）
    needs: build
    steps:
      - download-artifact: release-dist
      - B2 签名：sigstore sign（内网默认）/ signtool sign（公开 OV 证书）
      - SHA256 校验文件生成（SHA256SUMS.txt）
      - upload-artifact@v4: release-signed（长期保留——存档）

  publish:                   # Job 3：发布（受保护环境审批）
    needs: sign
    environment: release     # 受保护 Environment（required reviewer）
    steps:
      - download-artifact: release-signed
      - 校验：签名验证 + twine check
      - 发布：Trusted Publishing（OIDC——无 API token）
      - gh release create（Release 附产物 + 自动 release notes）
```

## 二、安全配置（调研确认）

| 配置 | 依据 |
|---|---|
| **受保护 Environment**（release——required reviewer） | hironow ADR + Shaken Fist：发布前人工审批 |
| **受保护 v* 标签规则集**（限制 tag 创建/删除） | ADR：Environment 只暂停审批，须在 ref 级限制 |
| **OIDC Trusted Publishing**（无长生命周期 API token） | 官方：token 泄露 = 未授权发布（最高供应链风险） |
| **最小权限**（id-token: write 仅 sign/publish；contents: read 默认） | ADR + Shaken Fist |
| **产物保留**（release-dist 90 天/可审计 + release-signed 长期/存档） | GitHub Actions 官方（retention-days） |
| **build/publish 分离**（签名产物即审核字节——防重建漂移） | Safeguard 指南 + vibebiao TIL |

## 三、B1/B2/B3 集成（发布流水线内——开发零影响）

| B 级项 | release.yml 集成点 |
|---|---|
| B1 混淆隔离 | build job：master-obf 产物（Nuitka/PyArmor——发布期，不触碰 master 源码） |
| B2 签名 | sign job：sigstore/signtool（分层——内网 keyless/公开证书） |
| B3 SBOM | build job：cyclonedx 生成随产物（供应链透明） |

## 四、验证与门禁

1. **发布前**：签名验证 + twine check + smoke-test（产物可运行）
2. **发布后**：gh release 校验（产物/校验值/SBOM 完整）
3. **开发零影响**：ci.yml（开发门禁）与 release.yml（发布）完全分离

## 五、结论

B4 独立 release workflow 满足 2026 行业标准：**发布专属 + build/publish 分离 + B1/B2/B3 全集成 + 受保护环境双审批 + OIDC 无 token + 产物保留策略**——设计先行完毕，待发布期实施（开发流水线零影响）。
