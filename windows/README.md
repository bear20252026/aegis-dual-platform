# windows — Aegis 正典 Windows 栈（ADR-009：C#/.NET 10 + WPF + WebView2）

> Python/pywebview 时代栈已退役归档至 `legacy/windows-pywebview/`（仅供历史参考）。

## 构建

```powershell
cd windows/src/Aegis.Windows.App
dotnet build            # 调试构建
dotnet run              # 本机运行
dotnet test ../../tests/Aegis.Windows.Core.Tests      # 177 个核心测试
dotnet test ../../tests/Aegis.Windows.Broker.Tests    # 29 个 broker 测试
```

## 发布制品

- 唯一发布制品：**Inno Setup 安装包**（`AegisBrowser-CSharp-Setup-<version>.exe`）。
- 云端链：`.github/workflows/release-windows.yml`（dotnet publish → ISCC → attest → artifact）。
- 版本单源：`shared/version.properties`（`scripts/sync_versions.py` 同步、`scripts/verify_versions.py` 门禁）。

## 结构

- `src/Aegis.Windows.App/` — 应用（Chrome UI / Core 数据层 / Broker 安全层 / WebView 封装）。
- `tests/` — xUnit 测试两套件。
- `packaging/` — 打包脚本。
