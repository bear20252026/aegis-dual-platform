# Windows 壳本地运行说明（windows-run-guide.md）

> 依据：蓝图 docs/runbooks + 阶段 C（windows/src/Aegis.Windows.App——最小安全壳）+
> device-validation.md（真机验证清单）——供用户本地启动验证（运行门禁准备）。

## 一、构建（.NET 10.0.302——已验证 0 警告）

```bash
cd windows/src/Aegis.Windows.App
dotnet build Aegis.Windows.App.csproj   # 已成功生成（0 错误 0 警告）
```

## 二、运行（本地启动 Aegis.Windows.App——GUI）

```bash
dotnet run --project windows/src/Aegis.Windows.App
# 或运行构建产物：
# windows/src/Aegis.Windows.App/bin/Debug/net10.0-windows/Aegis.Windows.App.exe
```

启动后：地址栏输入 URL（导航经 Broker 决策——NavigationStarting 真实取消）、
后退/前进/刷新/停止、安全错误页（导航失败——WebErrorStatus 可见）。

## 三、真机验证（运行门禁——device-validation.md 清单）

按 docs/runbooks/device-validation.md 执行 Windows WebView2 真机验证（10 项）：
远程 bridge 探测/跨源 iframe/重定向/javascript:/data:/file:/自定义协议/下载 MIME
混淆/重复确认/标签代际竞态/renderer crash/Runtime 更新重启——每项记录结果——
失败项修复后重验（运行门禁 fail-closed）。

## 四、Android 真机

Android 端需真实设备（Kotlin/Compose——阶段 D）——按 device-validation.md
Android 清单（7 项——bridge absence/renderer crash/生命周期/下载/重定向/网络
切换/存储恢复）执行。
