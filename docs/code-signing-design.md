# B2 代码签名架构设计（code-signing-design）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> final-development-checklist B2（代码签名——行业标准/防 AV 误报/2026 强制）
> 依据：全球调研（中英全覆盖）——微软 SignTool 官方（/fd SHA256 + /td RFC3161
> 时间戳）+ sigstore-python 官方（keyless：OIDC→Fulcio+Rekor）+ PEP 761
> （Python 3.14 起 Sigstore 唯一签名方式——CPython 官方背书）+ 掘金合规
> 流程（证书选型/SmartScreen/时间戳必加）+ Azure 受信任签名

---

## 〇、结论速览

**Aegis 采用分层签名架构**：内网分发默认 **sigstore keyless**（免费 + PEP 761 权威背书 + 供应链完整性）；公开分发按需 **Authenticode（SignTool + OV/EV 证书）**（防 SmartScreen/AV 误报——2026 强制要求）。配套：**RFC3161 时间戳（必加，防证书过期失效）+ SHA256（SHA1 弃用）+ CI build/publish 分离**。

## 一、方案对比（调研确认）

| 维度 | Authenticode（SignTool + 证书） | sigstore keyless（sigstore-python） |
|---|---|---|
| 效果 | SmartScreen 消除警告（EV 直接绕过/OV 积累信誉） | 证明未篡改——Windows 仍可能提示 |
| 成本 | OV ¥1000-3000/年、EV ¥4000-8000/年（私钥 USB Token） | 免费（GitHub OIDC 身份） |
| 技术 | `/fd SHA256 + /tr 时间戳 + /td SHA256`（SHA1 弃用） | OIDC → Fulcio 短时证书 + Rekor 透明日志；ambient credentials |
| 背书 | 微软官方 + 掘金合规 | **PEP 761**（CPython 官方） |

## 二、Aegis 分层签名架构

```
内网分发（默认）：sigstore-python keyless
  ├─ sigstore sign <artifact> → <artifact>.sigstore
  │   （OIDC 身份 → Fulcio 短时证书 + Rekor 透明日志记录）
  └─ sigstore verify identity --cert-identity <id> --cert-oidc-issuer <url>
      （验证签名/身份——供应链完整性，PEP 761 对齐）

公开分发（按需）：Authenticode（SignTool + OV/EV 证书）
  ├─ signtool sign /f cert.pfx /p <pwd> /fd SHA256 \
  │     /tr http://timestamp.digicert.com /td SHA256 <artifact>
  │   （必加 RFC3161 时间戳——防证书过期后签名失效）
  └─ signtool verify /pa /v <artifact>（验证——默认 Authenticode 策略）

配套（两层通用）：
  ├─ SHA256 摘要（SHA1 已弃用——20236+ 构建强制 /fd + /td）
  ├─ CI build/publish 分离（签名产物即审核字节——防重建漂移）
  └─ 私钥保护（EV：USB Token 硬件不可导出；OV：.pfx 加密最小权限）
```

## 三、技术要点（调研确认）

| 要点 | 依据 |
|---|---|
| 时间戳必加（RFC3161 /tr + /td） | 掘金：无时间戳证书过期→签名失效→重新报未知发布者 |
| SHA256 必须（/fd） | 微软：SHA1 弃用；20236+ 构建警告→错误 |
| EV 私钥 USB Token | 掘金：不可导出、不泄露 |
| 自签名/免费 SSL 不能用于代码签名 | 掘金：自签名、Let's Encrypt 无效 |
| sigstore ambient credentials | sigstore-python 官方：CI 平台 OIDC 自动检测 |
| Azure 受信任签名（可选替代） | 微软：托管签名服务 + 证书生命周期 + CI/CD 集成 |

## 四、验证与门禁

1. **sigstore 路径**：`sigstore verify identity` 通过（身份/issuer 匹配）
2. **Authenticode 路径**：`signtool verify /pa /v` 通过（证书链/时间戳有效）
3. **构建产物**：签名后 smoke-test + 全量回归（发布前）
4. **配合 B1**：签名作用于混淆/编译产物（B1 dist/）——完整性 + 防误报

## 五、结论

B2 分层签名架构满足 2026 行业标准：**内网 sigstore 零成本优先（PEP 761 背书）+ 公开 OV/EV 证书按需（防 SmartScreen/AV 误报——2026 强制）+ 时间戳/SHA256 合规 + CI 集成**——设计先行完毕，待发布期实施。
