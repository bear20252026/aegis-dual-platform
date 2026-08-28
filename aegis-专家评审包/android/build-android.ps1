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

Push-Location $Root
try {
    if ($Target -in @('apk', 'both')) {
        if ($Release) { & $Gradle assembleRelease } else { & $Gradle assembleDebug }
    }
    if ($Target -in @('aab', 'both')) {
        if (-not $Release) { throw 'AAB 仅应生成 Release 版本。请加 -Release。' }
        & $Gradle bundleRelease
    }
} finally {
    Pop-Location
}

Write-Host 'Android 构建完成。发布前请执行 apksigner verify 并生成 SHA-256 校验值。'
