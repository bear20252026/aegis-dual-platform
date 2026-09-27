---
name: 安全漏洞报告
about: 报告安全漏洞（私密披露优先——公开 Issue 不留可利用细节）
title: '[security] '
labels: security
assignees: ''
---

> **披露纪律**：本模板用于低敏感度的安全问题描述。**可利用细节（PoC、
> payload、绕过步骤）不要写在这里**——请通过 GitHub Security Advisory
> （Security 标签页 → Report a vulnerability）私密披露，或按 SECURITY.md
> 的响应流程联系维护者。公开渠道仅描述影响面与严重级评估。

**类型**

- [ ] 边界/信任域破坏（远程页获得桥能力等——ADR-002/003）
- [ ] 导航/下载/权限策略绕过
- [ ] 隐私泄露（历史/图标/凭据落盘等）
- [ ] 供应链/发布链（制品、签名、来源）
- [ ] 其他

**影响面**

受影响的端（Windows/Android/发布链）与能力范围，不含可利用细节。

**复现条件（脱敏）**

环境与前提条件即可；细节走私密渠道。

**建议缓解**

……

**环境**

- 端：Windows / Android / CI/发布链
- 版本：构建号或 commit
