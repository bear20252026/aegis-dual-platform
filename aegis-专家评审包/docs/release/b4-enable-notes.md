# B4 Release Workflow 实际启用说明（b4-enable-notes）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> B4 实际启用——`release.yml` 已落位 `.github/workflows/release.yml`（实际可触发）
> 配置依据：GitHub Docs 官方（Deployments and environments / Creating rulesets）+ 中文实践（半颗白菜多阶段发布流水线——截止 2026-08-15）

## 一、已落位状态

- `.github/workflows/release.yml`（6143 字节——与 docs/release 版一致——GitHub Actions 识别）
- 触发器：`push tags: v*`（唯一发布触发器——避免手动操作/版本混乱——中文实践）
- 结构：pin-check → build（B1 混淆 + SHA-256）→ sbom（B3）→ verify（fail-closed）→ publish（tag-gated）
- 全部 action 已固定完整 40 字符 SHA（gh api 查证——S-04）

## 二、受保护 Environment 配置（GitHub Docs 官方）

在仓库 Settings → Environments → New environment 创建 `release`：

| 配置项 | 官方要求 | 说明 |
|---|---|---|
| **Required reviewers** | 最多 6 人/团队——只读权限——一人批准即可 | 部署保护规则（deployment protection rules）——发布前人工审批 |
| **Deployment branches and tags** | 选 **Selected branches and tags**——填 `v*` 模式（fnmatch） | 只有 `GITHUB_REF` 为 v* 的 tag 可部署到该环境——与 workflow 触发器一致 |
| **环境级 secrets** | 环境 secrets 仅引用该环境的 job 可访问——审批前不可访问 | 发布凭据（如签名密钥）放环境级——非仓库级 |

## 三、v* 标签规则集（GitHub Docs 官方——rulesets）

在仓库 Settings → Rules → Rulesets 创建 tag 规则集：

| 规则 | 目的 |
|---|---|
| **Tag protections**（谁可删/改名 tag） | 防止 v* tag 被误删/改名——发布可追溯 |
| 目标：`refs/tags/v*` | 仅影响发布 tag——开发分支不受影响 |

## 四、发布流程（中文实践——标准流程）

```bash
# 1. 开发并测试（ci.yml 门禁全绿）
git add . && git commit -m "feat: ..."
git push
# 2. 创建语义化版本 tag（唯一发布触发器）
git tag v1.0.0 -m "Release v1.0.0"
# 3. 推送 tag（触发 release.yml——v* 匹配）
git push origin v1.0.0
# 4. 等待构建（3-5 分钟）——受保护环境 required reviewer 审批后 publish
# 5. 访问 Releases 页面查看产物（最终包 + SHA256SUMS + SBOM + provenance）
```

## 五、发布后验证

- Releases 页面产物齐全（dist 最终包 + SHA256SUMS.json + sbom.cdx.json + .sigstore 签名）
- `verify` job 已 fail-closed 验证（SHA-256 对账/签名/SBOM 缺一拒绝——发布前）
- 更新清单（R-17）验证（Ed25519 阈值签名/防回滚/过期——update_verifier）
