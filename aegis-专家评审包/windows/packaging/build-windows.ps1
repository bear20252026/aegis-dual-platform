[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Release',
    [string]$Publisher = 'CN=Aegis Project',
    [string]$Version = '2.1.6.0',
    [string]$PackageIdentity = 'Aegis.Project.AegisWebView',
    [switch]$SkipPackage,
    [switch]$SkipSign
)

$ErrorActionPreference = 'Stop'
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WindowsRoot = Split-Path -Parent $ScriptRoot
$SourceRoot = Join-Path $WindowsRoot 'aegis_source'
$OutRoot = Join-Path $WindowsRoot 'artifacts'
$StageRoot = Join-Path $OutRoot 'msix-stage'
$DistRoot = Join-Path $SourceRoot 'dist\AegisWebView'
$ManifestTemplate = Join-Path $ScriptRoot 'AppxManifest.xml.template'
$AppInstallerTemplate = Join-Path $ScriptRoot 'Aegis-WebView.appinstaller.template'

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "缺少命令：$Name。此脚本只生成发布产物；请在安装 Python、PyInstaller、Windows SDK 后再执行。"
    }
}

Write-Host "[1/5] 检查构建工具"
Require-Command python
Require-Command pyinstaller
if (-not $SkipPackage) { Require-Command makeappx }
if (-not $SkipSign) { Require-Command signtool }

Write-Host "[2/5] 创建干净 PyInstaller onedir 输出"
Push-Location $SourceRoot
try {
    python -m pip install -r requirements.txt
    pyinstaller --noconfirm --clean aegis_webview.spec
} finally {
    Pop-Location
}

if (-not (Test-Path (Join-Path $DistRoot 'Aegis.exe'))) {
    throw "未找到 Aegis.exe：$DistRoot"
}

Write-Host "[3/5] 准备 MSIX staging 目录"
Remove-Item -Force -Recurse $StageRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $StageRoot | Out-Null
Copy-Item -Recurse -Force (Join-Path $DistRoot '*') $StageRoot
New-Item -ItemType Directory -Force (Join-Path $StageRoot 'Assets') | Out-Null
Copy-Item -Force (Join-Path $SourceRoot 'assets\icon.png') (Join-Path $StageRoot 'Assets\StoreLogo.png')
Copy-Item -Force (Join-Path $SourceRoot 'assets\icon.png') (Join-Path $StageRoot 'Assets\Square150x150Logo.png')
Copy-Item -Force (Join-Path $SourceRoot 'assets\icon.png') (Join-Path $StageRoot 'Assets\Square44x44Logo.png')

$manifest = Get-Content -Raw -Encoding UTF8 $ManifestTemplate
$manifest = $manifest.Replace('CN=Aegis Project', $Publisher)
$manifest = $manifest.Replace('Aegis.Project.AegisWebView', $PackageIdentity)
$manifest = $manifest.Replace('2.1.6.0', $Version)
Set-Content -Encoding UTF8 (Join-Path $StageRoot 'AppxManifest.xml') $manifest

if (-not $SkipPackage) {
    Write-Host "[4/5] 生成 MSIX"
    New-Item -ItemType Directory -Force $OutRoot | Out-Null
    $msix = Join-Path $OutRoot 'Aegis-WebView.msix'
    Remove-Item -Force $msix -ErrorAction SilentlyContinue
    makeappx pack /d $StageRoot /p $msix /o

    if (-not $SkipSign) {
        Write-Host "[5/5] 签名 MSIX（需由 CI 或安全证书配置注入具体签名参数）"
        Write-Warning '已预留签名位置；请使用受保护的证书或 Artifact Signing，不要将私钥写入本脚本。'
    }

    $appInstaller = Get-Content -Raw -Encoding UTF8 $AppInstallerTemplate
    $appInstaller = $appInstaller.Replace('CN=Aegis Project', $Publisher)
    $appInstaller = $appInstaller.Replace('Aegis.Project.AegisWebView', $PackageIdentity)
    $appInstaller = $appInstaller.Replace('2.1.6.0', $Version)
    Set-Content -Encoding UTF8 (Join-Path $OutRoot 'Aegis-WebView.appinstaller') $appInstaller
}

Write-Host '完成：Windows 源码构建与 MSIX staging/模板处理已完成。'
