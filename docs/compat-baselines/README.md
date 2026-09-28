# WebView2 兼容性回归基线

> WB-097（审计 2026-09-23 清单·W5 批）口径修正：本目录**仓库内默认只有本
> README**——基线文件（probe-latest.json / probe-YYYYMMDD.json）由
> .github/workflows/compat.yml 每周一 06:00 UTC 在 runner 上生成后经
> **artifact 存档**，不回提交进仓库；对比基线时从 workflow run artifacts
> 下载。此前"文件由工作流自动生成"的表述易被误读为"仓库内应已存在"。

由 .github/workflows/compat.yml 每周一 06:00 UTC 自动生成：
- probe-latest.json：最新探测报告（Runtime 版本 + 关键 API 可用性）
- probe-YYYYMMDD.json：按日期归档的历史基线（均在 run artifacts 中——不入库）

用途：Evergreen Runtime 2 周更新节奏下，比对"版本 × 功能"回归基线。
