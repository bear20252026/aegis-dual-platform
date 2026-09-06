; Aegis Browser Windows 安装包脚本（Inno Setup 6）
; 由账号2生成
; 编译命令：ISCC.exe AegisSetup.iss

#define MyAppName "Aegis Browser"
#define MyAppVersion "2.2.0-beta.17"
#define MyAppPublisher "Aegis Project"
#define MyAppExeName "Aegis.exe"

[Setup]
; 安装器 EXE 自身品牌图标（快捷方式图标继承目标 EXE——assets/icon.ico）
SetupIconFile=setup_icon.ico
; 安装器向导界面图（用户提供品牌图——星球；modern 风格 192x386）
WizardImageFile=installer_welcome.bmp
WizardSmallImageFile=installer_small.bmp
AppId={{A7B8C9D0-E1F2-4A5B-8C7D-9E0F1A2B3C4D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=AegisBrowser-Setup-{#MyAppVersion}
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
Source: "..\..\legacy\windows-pywebview\dist\AegisWebView\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\legacy\windows-pywebview\dist\AegisWebView\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
