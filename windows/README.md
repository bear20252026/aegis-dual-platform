# windows — Aegis 正典 Windows 栈（ADR-009：C#/.NET 10 + WPF + WebView2）

> Python/pywebview 时代栈已退役归档至 `legacy/windows-pywebview/`（仅供历史参考）。

## 构建

```powershell
cd windows
dotnet build src/Aegis.Windows.App/Aegis.Windows.App.csproj -r win-x64 -p:RestoreLockedMode=true   # 调试构建（0 警告 0 错误）
dotnet run --project src/Aegis.Windows.App -r win-x64                                              # 本机运行
dotnet test tests/Aegis.Windows.Core.Tests -r win-x64 -p:RestoreLockedMode=true                    # 核心测试套件全绿
dotnet test tests/Aegis.Windows.Broker.Tests -r win-x64 -p:RestoreLockedMode=true                  # broker 测试套件全绿
```

> 注意（SP-220，与 `docs/runbooks/windows-run-guide.md` 同口径）：NuGet 锁文件含
> RID（win-x64）——restore/build/test 必须带 `-r win-x64`（test 另加
> `-p:RestoreLockedMode=true`）；**无 `-r` 的裸 restore 会把锁改写回无 RID 形态**，
> 改写后的锁不要提交。

## 发布制品

- 唯一发布制品：**Inno Setup 安装包**（`AegisBrowser-CSharp-Setup-<version>.exe`）。
- 云端链：`.github/workflows/release-windows.yml`（dotnet publish → ISCC → attest → artifact）。
- 版本单源：`shared/version.properties`（`scripts/sync_versions.py` 同步、`scripts/verify_versions.py` 门禁）。

## 结构

- `src/Aegis.Windows.App/` — 应用（Chrome UI / Core 数据层 / Broker 安全层 / WebView 封装）。
- `tests/` — xUnit 测试两套件。
- 打包脚本不在本目录：安装包定义在 `docs/release/AegisSetup-CSharp.iss`（Inno Setup——CS-365 修正：`windows/packaging/` 目录不存在）。
