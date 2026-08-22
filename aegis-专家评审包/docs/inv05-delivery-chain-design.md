# INV-05 独立交付链设计

> 每发布制品独立可追溯——每平台独立 build→sign→SBOM→provenance→verify→publish

## 现状分析

当前 `release.yml` 是单一流水线：

```
pin-check → build(Windows) → sbom → verify → publish
```

**差距：**
- ❌ 只构建 Windows 包（PyInstaller），无 Android/APK、无 Rust Core/lib
- ❌ 三个平台共享一个 build job，无法独立追溯
- ❌ 无平台独立签名（sign）步骤
- ❌ SBOM 是全局的，不是 per-platform
- ❌ verify 是全局的，不是 per-platform

## 目标架构

```
pin-check
    ├── release-windows  (build→sbom→provenance→verify)
    ├── release-android  (build→sbom→provenance→verify)
    └── release-core     (build→sbom→provenance→verify)
                            ↓
                      verify-gate (三平台全通过才放行)
                            ↓
                      publish (tag-gated + environment审批)
```

### 每平台独立链

| 步骤 | Windows | Android | Rust Core |
|------|---------|---------|-----------|
| build | PyInstaller exe + SHA256 | Gradle apk + SHA256 | cargo build lib + SHA256 |
| sbom | CycloneDX (pip deps) | CycloneDX (gradle deps) | CycloneDX (cargo deps) |
| provenance | SLSA attest | SLSA attest | SLSA attest |
| verify | attest verify + checksum | attest verify + checksum | attest verify + checksum |

### 工作流拆分

1. **`release-windows.yml`** — Windows 平台独立交付链
2. **`release-android.yml`** — Android 平台独立交付链
3. **`release-core.yml`** — Rust Core 独立交付链
4. **`release.yml`**（改造） — 编排器：触发三平台 → verify-gate → publish

### 关键约束

- 每平台 workflow 可独立运行（`workflow_dispatch`）——调试友好
- 每平台产物独立 artifact（`release-windows`/`release-android`/`release-core`）
- 每平台 SBOM 独立生成（per-platform deps 透明）
- 每平台 provenance 独立 attest（per-artifact SLSA）
- verify-gate 需三平台全通过才放行（fail-closed）
- publish 聚合三平台产物，统一发布
- 所有 uses 固定完整 SHA（pin-check 不变）

### 产物清单

| 平台 | 产物 | 格式 |
|------|------|------|
| Windows | AegisWebView.exe | PyInstaller 单文件 |
| Android | app-release.apk | Gradle signed |
| Rust Core | aegis_policy_core.dll/.so | cargo build |
| 全平台 | SHA256SUMS.json | 对账清单 |
| 全平台 | sbom.cdx.json | CycloneDX SBOM |
| 全平台 | *.intoto.jsonl | SLSA provenance |
