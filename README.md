# Aegis 双端代码基线

本工作区遵循“**先完成代码和发布配置，后安装工具并构建验证**”的约束。当前没有安装 Android Studio、Android SDK、Windows SDK、Python 打包依赖或签名证书，也没有执行 APK、AAB、EXE、MSIX 或安装包构建。

## 目录

| 目录 | 内容 |
|---|---|
| `windows/aegis_source` | 以 `main_webview.py` 为正式入口的 Windows WebView2 源码工作副本。 |
| `windows/packaging` | MSIX、App Installer、代码级 Windows 构建脚本。 |
| `android` | Kotlin + Jetpack Compose + Android WebView 浏览器工程。 |
| `shared` | 双端版本、发布与更新清单协议。 |
| `scripts` | 从单一版本配置同步双端版本声明的脚本。 |

## 当前 Windows 决策

Windows 仅面向 WebView2 Evergreen Runtime，不再维护 macOS 后端和 NSIS 安装脚本。用户数据默认落在 LocalAppData 而不是安装目录；运行于 MSIX 时，应用内 EXE 更新器自动停用，更新职责转交 App Installer。

## 当前 Android 决策

Android 使用 Kotlin/Compose，首个浏览器引擎为 Android System WebView。`BrowserEngine` 已将 HTTP/HTTPS 限定为唯一导航协议，关闭文件访问、内容访问、file URL 跨域访问、混合内容和非调试模式 WebView 调试。后续可在保留 `BrowserEngine` 边界的前提下评估 GeckoView。

## 静态验证

运行：

```bash
python3 validate_release.py
python3 scripts/sync_versions.py
```

会执行 Python AST、JSON、XML 模板和版本声明的基础验证；不会导入或运行 Aegis 应用本体。

## 以后统一安装工具后的构建顺序

1. 安装并验证 Flutter/Android SDK/JDK/Gradle Wrapper，执行 Android `build-android.ps1`。
2. 安装并验证 Python、PyInstaller、Windows SDK 的 `makeappx` 与 `signtool`，执行 Windows `build-windows.ps1`。
3. 配置签名证书或可信签名服务，生成签名 APK/AAB/MSIX。
4. 在干净 Windows 与 Android 设备上测试安装、升级、卸载、数据保留与下载验证。
