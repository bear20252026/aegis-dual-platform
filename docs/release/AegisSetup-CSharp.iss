; Aegis Browser（C# 正典栈）Windows 安装包脚本（Inno Setup 6）——ADR-009
; SP-055（审计 2026-09-23 清单·SP1 批）：单轨正典——唯一 Windows 安装包脚本
;（Python 时代 AegisSetup.iss 已删除，verify_versions/sync_versions 不再同步）。
; 版本号不写死——CI 以 /DMyAppVersionOverride=<VERSION_NAME> 运行时注入
; （单源 shared/version.properties，杜绝 iss 版本漂移重演 v2.1.11 事故）。
; 本地编译：ISCC.exe /DMyAppVersionOverride=<VERSION_NAME> AegisSetup-CSharp.iss

#ifndef MyAppVersionOverride
#error "必须以 /DMyAppVersionOverride=<version> 传入版本号（单源 shared/version.properties）"
#else
#define MyAppVersion MyAppVersionOverride
#endif

#define MyAppName "Aegis Browser C#"
#define MyAppPublisher "Aegis Project"
#define MyAppExeName "Aegis.Windows.App.exe"

[Setup]
AppId={{DA228AF1-A3F4-4CBE-B968-45E777F8438D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; PY-163（2026-09-23 审计·V1 核验批）：三个安装器资产此前闲置——接入向导
; 图/侧图/安装器图标（资产同目录，48x48 / 192x386 / 多尺寸 ICO）
SetupIconFile=setup_icon.ico
WizardImageFile=installer_welcome.bmp
WizardSmallImageFile=installer_small.bmp
; PY-164（2026-09-23 审计·V1 核验批）：补安装日志开关——安装期排障留痕
;（日志落 %TEMP%，Setup Log *.log）
SetupLogging=yes
; 产物目录 = 仓库根 dist（相对本文件 docs/release/）——CI build job 的
; dotnet publish 输出（含 Rust aegis_policy_core.dll），与 zip 同源
OutputDir=..\..\dist
OutputBaseFilename=AegisBrowser-CSharp-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\aegis-windows\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 审计第六轮（2026-10-04）：出厂裁决模式标记——安装期写入，卸载删除。
; 为什么要写注册表：AEGIS_REQUIRE_NATIVE_POLICY_CORE 此前只在 CI 构建步的 shell
; 里赋值，既不随安装包交付也不进入终端用户进程环境——aegis_policy_core.dll
; 随包发布却从不被咨询，出货制品的导航裁决与构建期被测路径不是同一条。
; 为什么是 HKCU（与 PrivilegesRequired=lowest 的按用户安装一致）：本脚本不提权，
; HKLM 写入需要管理员；HKCU 是安装器可写、应用可读、无需提升的落点。
; ArchitecturesInstallIn64BitMode=x64compatible 下 HKCU 即 64 位视图，与 x64
; 应用默认读取的视图一致（两侧都不涉及 WOW6432Node 重定向）。
; 键路径/值名必须与 windows/src/Aegis.Windows.App/Broker/InstalledBuildMarker.cs
; 的常量逐字一致——Broker.Tests 的 InstalledBuildMarkerTests 直接读取本文件对账，
; 任一侧改名即失败（本仓反复复发的正是这类字符串漂移）。
; RequireNavigationConfirmation 刻意不写：完整理由记在 InstalledBuildMarker 的
; NavigationConfirmationValueName 注释（要点——核心现在的高危判据是本机/私网 host，
; Windows 在 EvaluateNavigation 与 TryConsumeNavigation 两点已硬拒＝弹面板后再拒的
; 死路径；且确认链不复判托管黑名单，而核心的黑名单注入入口尚无 C# 绑定与调用点，
; 此刻启用等于给黑名单 host 开一条"批准即放行"的面）。启用顺序：先把订阅源快照
; 喂给 aegis_policy_core_broker_update_host_denylist_json，再评估出厂置位。
Root: HKCU; Subkey: "Software\Aegis Browser"; ValueType: dword; ValueName: "RequireNativePolicyCore"; ValueData: "1"; Flags: uninsdeletevalue uninsdeletekeyifempty

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// PY-165（2026-09-23 审计·V1 核验批）：WebView2 运行时检测——主窗体依赖
// WebView2 渲染，缺失运行时时应用无法显示网页。检测 Evergreen 注册表键
//（机器级 WOW6432Node/HKLM + 用户级 HKCU），缺失时提示并允许中止
//（不硬拦——用户可能装完运行时再回来装本应用）。
function WebView2RuntimeInstalled: Boolean;
var
  Pv: string;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Pv) or
    RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Pv);
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if not WebView2RuntimeInstalled then
  begin
    Result := MsgBox(
      '未检测到 Microsoft WebView2 运行时。' #13#10
      'Aegis Browser 依赖 WebView2 渲染网页，缺失时应用无法正常显示内容。' #13#10 #13#10
      '建议先安装 WebView2 Evergreen 运行时（https://developer.microsoft.com/microsoft-edge/webview2/）。' #13#10
      '仍要继续安装吗？',
      mbConfirmation, MB_YESNO) = IDYES;
  end;
end;
