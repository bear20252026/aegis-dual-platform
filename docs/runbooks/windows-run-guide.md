# Windows 壳本地运行说明（windows-run-guide.md）

> 依据：蓝图 docs/runbooks + 阶段 C（windows/src/Aegis.Windows.App——最小安全壳）+
> device-validation.md（真机验证清单）——供用户本地启动验证（运行门禁准备）。
> WB-066（审计 2026-09-23 清单·W5 批）：全文统一 cwd 口径——**除第一节 cd 进
> 工程目录外，其余命令一律在仓库根执行**（与 CLAUDE.md「关键命令」一致）。

## 一、构建与测试（.NET 10——0 警告门禁）

```bash
cd windows
dotnet build src/Aegis.Windows.App/Aegis.Windows.App.csproj   # 0 错误 0 警告
dotnet test tests/Aegis.Windows.Core.Tests                    # 核心套件全绿
dotnet test tests/Aegis.Windows.Broker.Tests                  # Broker 套件全绿
cd ../..
```

> WB-065（审计 2026-09-23 清单·W5 批）：补 dotnet test——运行验证前两套件
> 必须全绿（此前本指南只有 build，缺回归验证环节）。

## 二、运行（本地启动 Aegis.Windows.App——GUI，仓库根执行）

```bash
dotnet run --project windows/src/Aegis.Windows.App
# 或运行构建产物：
# windows/src/Aegis.Windows.App/bin/Debug/net10.0-windows/Aegis.Windows.App.exe
```

启动后：地址栏输入 URL（导航经 Broker 决策——NavigationStarting 真实取消）、
后退/前进/刷新/停止、安全错误页（导航失败——WebErrorStatus 可见）。

## 三、原生策略核心联调（WB-065 补——Rust DLL 与 C# 端联调）

```bash
# 1) 构建 Rust 策略核心（cd core/rust-policy-core）
cargo build --release          # 产出策略核心动态库（--locked 门禁见 CLAUDE.md）
cargo test                     # 策略核心单测全绿
# 2) C# 端经 NativePolicyCoreBridge（NativeLibrary C-ABI 委托绑定）加载 DLL——
#    默认托管评估路径自动可用；原生严格模式（CI 口径）设
#    AEGIS_REQUIRE_NATIVE_POLICY_CORE=1 后启动，桥加载失败即 fail-closed
# 3) 验证：导航裁决走 Rust 核心（deny/allow 决策与解释可见于审计日志）
```

联调口径：Rust 侧只修 `core/rust-policy-core`；C# 绑定层改动需两套件
（Core/Broker.Tests）+ `cargo test` 双绿。

## 四、真机验证（运行门禁——device-validation.md 清单）

按 docs/runbooks/device-validation.md 执行 Windows WebView2 真机验证（10 项）：
远程 bridge 探测/跨源 iframe/重定向/javascript:/data:/file:/自定义协议/下载 MIME
混淆/重复确认/标签代际竞态/renderer crash/Runtime 更新重启——每项记录结果——
失败项修复后重验（运行门禁 fail-closed）。

## 五、Android 真机

Android 端需真实设备（Kotlin/Compose——阶段 D）——按 device-validation.md
Android 清单（7 项——bridge absence/renderer crash/生命周期/下载/重定向/网络
切换/存储恢复）执行。
