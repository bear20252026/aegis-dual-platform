; Aegis Browser（C# 正典栈）Windows 安装包脚本（Inno Setup 6）——ADR-009
; 与 PyInstaller stable 安装包（AegisSetup.iss）并存：独立 AppId，互不覆盖。
; 版本号不写死——CI 以 /DMyAppVersionOverride=<VERSION_NAME> 运行时注入
; （单源 shared/version.properties，杜绝 iss 版本漂移重演 v2.1.11 事故）。
; 本地编译：ISCC.exe /DMyAppVersionOverride=2.1.18 AegisSetup-CSharp.iss

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

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
