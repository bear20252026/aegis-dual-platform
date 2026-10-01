[CmdletBinding()]
param(
    [ValidateSet('apk', 'aab', 'both')]
    [string]$Target = 'both',
    [switch]$Release
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Gradle = Join-Path $Root 'gradlew.bat'

if (-not (Test-Path $Gradle)) {
    throw "未找到 gradlew.bat。代码阶段已完成；安装 Android Studio/SDK 后，在 $Root 生成或恢复 Gradle Wrapper 再执行本脚本。"
}

# SP-195（2026-10-01 审计）：每个 & gradle 调用后检查 $LASTEXITCODE——
# 原实现不检查，Gradle 失败仍打印「构建完成」误导发布链（PowerShell 的
# $ErrorActionPreference 不拦截原样退出码的外部命令）。
function Invoke-Gradle {
    param([string[]]$GradleArgs)
    & $Gradle @GradleArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Gradle 失败（退出码 $LASTEXITCODE）：gradlew $($GradleArgs -join ' ')"
    }
}

# SP-211（2026-10-01 审计）：本地 -Release 与 CI 发布物的配置差异醒目告警
# ——CI（release-android.yml）以 -PrequireNativePolicyCore=true 构建发布物；
# 本地 -Release 默认不带该属性（产物为纯 Kotlin broker 兜底路径，与发布物
# 行为不同：native 模式策略判定/确认流均不同）。此处打印醒目差异告警；
# 如需对齐 CI 口径，传 -PrequireNativePolicyCore=true。
if ($Release -and -not $env:AEGIS_QUIET_RELEASE_DIFF) {
    Write-Host '============================================================' -ForegroundColor Yellow
    Write-Host '⚠  本地 -Release 未启用原生策略核心（与 CI 发布物配置不同）' -ForegroundColor Yellow
    Write-Host '⚠  CI 发布物：gradlew :app:assembleRelease -PrequireNativePolicyCore=true' -ForegroundColor Yellow
    Write-Host '⚠  对齐 CI：& .\gradlew.bat assembleRelease -PrequireNativePolicyCore=true' -ForegroundColor Yellow
    Write-Host '⚠  或设 AEGIS_QUIET_RELEASE_DIFF=1 静默本告警' -ForegroundColor Yellow
    Write-Host '============================================================' -ForegroundColor Yellow
}

Push-Location $Root
try {
    if ($Target -in @('apk', 'both')) {
        if ($Release) { Invoke-Gradle @('assembleRelease') } else { Invoke-Gradle @('assembleDebug') }
    }
    if ($Target -in @('aab', 'both')) {
        if (-not $Release) { throw 'AAB 仅应生成 Release 版本。请加 -Release。' }
        Invoke-Gradle @('bundleRelease')
    }
} finally {
    Pop-Location
}

Write-Host 'Android 构建完成。发布前请执行 apksigner verify 并生成 SHA-256 校验值。'
