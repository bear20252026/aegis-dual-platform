# Aegis Windows 发布代码

正式 Windows 运行路径为：

```text
main_webview.py
  → PyInstaller onedir（Aegis.exe + _internal）
  → MSIX（Aegis-WebView.msix）
  → App Installer（Aegis-WebView.appinstaller）
```

本目录当前只包含源码、配置和脚本，未安装任何工具、未执行构建、未生成签名产物。

## 已完成的代码改造

1. `app/paths.py` 将默认用户数据从 EXE 同级目录迁移至 `LOCALAPPDATA\\Aegis\\WebView\\LocalState`，避免 MSIX 只读安装目录写入失败。
2. `app/package_runtime.py` 检测 Windows Package Identity；当运行于 MSIX 时，`app/updater.py` 不再下载自更新 EXE，更新责任交给 App Installer。
3. `aegis_webview.spec` 只保留 Windows pywebview 后端，并收集 shell 与 assets 运行资源。
4. `packaging/` 包含 MSIX manifest、App Installer 模板和 `build-windows.ps1`。

## 以后安装工具后的构建

安装 Python、Windows SDK、WebView2 Evergreen Runtime 和签名工具后，执行：

```powershell
cd windows\packaging
.\build-windows.ps1 -SkipSign
```

正式发布时必须替换以下占位项：

- Package Identity
- Publisher（必须与代码签名身份一致）
- App Installer 的 HTTPS 发布地址
- MSIX 视觉资产尺寸
- 签名证书或 Artifact Signing 配置

不要重新启用 NSIS；它保留在原始源码中仅作历史参考。
