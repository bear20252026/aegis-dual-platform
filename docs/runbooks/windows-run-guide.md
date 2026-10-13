# Windows 壳本地运行说明（windows-run-guide.md）

> 依据：蓝图 docs/runbooks + 阶段 C（windows/src/Aegis.Windows.App——最小安全壳）+
> device-validation.md（真机验证清单）——供用户本地启动验证（运行门禁准备）。
> WB-066（审计 2026-09-23 清单·W5 批）：全文统一 cwd 口径——**除第一节 cd 进
> 工程目录外，其余命令一律在仓库根执行**（与 CLAUDE.md「关键命令」一致）。

## 一、构建与测试（.NET 10——0 警告门禁）

<!-- WB-211（2026-10-02 审计）：dotnet 命令补 -r win-x64（与 NuGet 锁文件的
     rid 一致）与 -p:RestoreLockedMode=true（锁模式防还原改写锁）——
     与 CLAUDE.md/CONTRIBUTING.md 质量门槛命令逐字对齐（SP-220） -->

```bash
cd windows
# SP-220：-r win-x64 与 NuGet 锁一致；RestoreLockedMode 锁模式防改写锁文件
dotnet build src/Aegis.Windows.App/Aegis.Windows.App.csproj -r win-x64 -p:RestoreLockedMode=true   # 0 错误 0 警告
dotnet test tests/Aegis.Windows.Core.Tests -r win-x64 -p:RestoreLockedMode=true                    # 核心套件全绿
dotnet test tests/Aegis.Windows.Broker.Tests -r win-x64 -p:RestoreLockedMode=true                  # Broker 套件全绿
cd ../..
```

> WB-065（审计 2026-09-23 清单·W5 批）：补 dotnet test——运行验证前两套件
> 必须全绿（此前本指南只有 build，缺回归验证环节）。

> R9-CI-9（第九轮 2026-10-10）：「全绿」在 CI 里还多一层含义——八处 `dotnet test`
> 除退出码外都断**发现数下界**（Core ≥700、Broker ≥160）。退出码只说「跑到的都没失败」，
> 一个都没发现时同样退 0，所以本地要复现同一判定得让命令落 TRX：给 `dotnet test` 补
> `--results-directory TestResults/core --logger "trx;LogFileName=core-tests.trx"`，
> 再回仓库根跑
> `python scripts/assert_test_counts.py --results-dir TestResults/core --minimum 700 --label Core`。

## 二、运行（本地启动 Aegis.Windows.App——GUI，仓库根执行）

```bash
# WB-211：-r win-x64 与构建/锁文件口径一致（SP-220）
dotnet run --project windows/src/Aegis.Windows.App -r win-x64
# 或运行构建产物：
# windows/src/Aegis.Windows.App/bin/Debug/net10.0-windows/win-x64/Aegis.Windows.App.exe
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

> 审计第六轮（2026-10-04）：环境变量只在**当前进程**有效，不会随安装包交付，
> 因此上面的手动开关只覆盖开发/CI 联调。第十轮（2026-10-11，AX-05）之后，出货制品的
> 原生裁决由**编译进产物的构建常量**要求（发布链用 `-p:RequireNativePolicyCore=true`
> 生成 `Broker/NativePolicyCoreBuildMarker`，并在已发布的 `Aegis.Windows.App.dll` 上
> 验证 ASCII 姿态串 `aegis.build.require-native-policy-core=1`——按 UTF-16 解码找，
> .NET 字面量存在元数据里不是字节可见的 ASCII）；按用户标记
> （`HKCU\Software\Aegis Browser\RequireNativePolicyCore=1`，
> 见 docs/release/AegisSetup-CSharp.iss 的 [Registry] 段与
> Broker/InstalledBuildMarker.cs）与环境变量仍是有效来源，但**不再是唯一来源**：
> 清注册表、脱离安装器直接双击 EXE，都关不掉这个要求。开发构建（不传该属性）
> 生成 false 那份，行为与以前一致。已安装制品的判定路径可在启动后的安全日志
> 首行 `[adjudication]` 直接读出（要求=true/false、构建姿态、安装标记、探测结果、
> 确认门状态）——该项留痕本身就是修复的一部分：断链此前因零痕迹而连续五轮未被发现。

联调口径：Rust 侧只修 `core/rust-policy-core`；C# 绑定层改动需两套件
（Core/Broker.Tests）+ `cargo test` 双绿。

## 四、真机验证（运行门禁——device-validation.md 清单）

按 docs/runbooks/device-validation.md 执行 Windows WebView2 真机验证。
**计数不在这里抄**（R9-B48：这一行曾经写「10 项」而实树 11 步，R9-DOC-08 把它改准后
本批又长了第 12 步——把数量抄进第二份文档就是制造第二个会过期的事实）。
现读口径：`grep -c '^| [0-9]' docs/runbooks/device-validation.md` 在「一、Windows」小节里的行数即项数。
按名称核对（与上表逐条对应）：远程页面 bridge 探测 / 跨源 iframe / 重定向 /
`javascript:`·`data:`·`file:` / 自定义协议 / 下载 MIME 混淆 / 重复确认 / 标签代际竞态 /
renderer crash / Runtime 更新重启 / **历史导航是否经策略链（R8-CS-SEC-03）** /
**WebView2 内核默认（DevTools 与自动填充，R9-B48）**——每项记录结果——
失败项修复后重验（运行门禁 fail-closed）。

第 11 步是那条修复的**唯一实测出口**（单测只能证明判定函数，证明不了历史列表回填
时没有绕过策略链），漏计的后果是该判据长期没有验证入口；另注意第 7 步「重复确认」
在唯一发布制品上默认不出现面板，须先设 `AEGIS_REQUIRE_NAVIGATION_CONFIRMATION=1`
（前置与理由见 device-validation.md 第 7 步——R9-DOC-07）。

## 五、Android 真机

Android 端需真实设备（Kotlin/Compose——阶段 D）——按 device-validation.md
Android 清单（8 项——bridge absence/renderer crash/生命周期/下载/重定向/网络
切换/存储恢复/下载重定向落点复判）执行。**8 是 R9-B43 加的**（R9-AD-3 的复判只能在真机
上验，登记时按 R9-DOC-08 同一口径把数量与名称一起改准，不留「文档数 ≠ 实树数」的旧病）。
