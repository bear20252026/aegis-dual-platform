# Aegis 架构全景文档（architecture-overview）

> **权威入口声明**（SP-004 整改）：本文件是项目架构蓝图与 agent/README 的
> 权威汇入点。2026-09-24 全面审计 WB-009 整改重写——旧版仅描述 Python
> 27 文件视图，已与「C# 唯一正典栈」终局（ADR-007/009）严重漂移。
> 编制日期：2026-09-24 ｜ 终局口径：ADR-007（单一正典）+ ADR-008
> （Rust 为**导航裁决**单源——能力评估层未接入 FFI 通路，核心自述 H-7）
> + ADR-009（C# 全面迁移完成）

---

## 一、完整代码树（分类标注职责）

### 1.1 Windows 正典栈（C#/.NET 10 + 原生 WebView2——唯一发布制品）

```
windows/
├── src/Aegis.Windows.App/
│   ├── Program.cs / App.xaml*          入口层：薄壳启动组装
│   ├── Broker/                         能力代理：导航决策/审批/审计
│   ├── Chrome/                         浏览器壳：标签运行时/无痕窗口/地址栏
│   ├── Core/
│   │   ├── Tabs/                       多标签（TabManager 事件闭环）
│   │   ├── Bookmarks/ Favicons/        书签 + 图标服务（无痕不落盘）
│   │   ├── History/                    历史存储与搜索
│   │   ├── Downloads/                  下载管理器（M3，经 broker 审计）
│   │   ├── Privacy/ Security/          KillSwitch / UrlSafety / 无痕
│   │   ├── Settings/                   设置窗口（威胁订阅源等）
│   │   └── UrlSafety.cs                URL 安全关口
│   ├── WebView/                        FingerprintShield / WebView 装配
│   └── Contracts/                      契约生成代码（codegen 单源）
├── tests/                              Core.Tests + Broker.Tests（dotnet test）
```
> Inno Setup 发布脚本实际位于仓库根 `docs/release/`（AegisSetup-CSharp.iss，
> 版本运行时注入；WB-120，2026-09-26 审计——原树形图误挂 windows/ 下）

### 1.2 Rust 策略核心（导航裁决单源——ADR-008）

> **范围限定（第八轮实测，撤「唯一裁决者」无限定语）**：FFI 通路实际只承载
> URL 归一 / 黑名单 / 高危判定 / nonce 兑换；`PolicyEngine::default()` 与
> `CapabilityRegistry::new()` 被构造却从不参与 `evaluate`（核心自述 H-7 未撤）——
> 能力评估裁决仍在各端托管 Broker，未收敛进核心。

```
core/rust-policy-core/                c_abi FFI + matcher + action_policy +
                                      session_state + fingerprint_pipeline +
                                      protection_mode + letterbox + tostring_guard
contracts/schemas/                    冻结 JSON Schema（action/update-manifest…）
contracts/codegen/                    单源模板：bridge_guard（JS/C#/Kotlin 三端归一）
```

### 1.3 Android 端（Kotlin/Compose + System WebView）

```
android/app/src/main/java/com/aegis/browser/
├── MainActivity.kt                    入口：组装 + 返回键（OnBackPressedCallback）
├── webviewadapter/                    AegisWebViewClient（导航授权状态机 + 会话续期）
├── broker/AndroidBroker.kt            会话/nonce/TTL 单源（SESSION_TTL_SECONDS）
├── TabManager.kt / Tab.kt / UI 层     标签（StateListener——copy() 替换实例）
├── SecureWebViewFactory.kt            WebView 安全工厂
├── DownloadPolicy.kt / WebViewDownloadHandler.kt   下载策略（危险扩展拦截）
├── ReaderController.kt / ReaderMode.kt            阅读模式（平文件——非目录，
│                                                  WB-160，2026-10-01 审计改述）
└── TranslateEntry.kt                              翻译入口（平文件）
```

### 1.4 单源 UI（双端共享）

```
shared/shell/                         start.html + start.css + start.js
                                      （Host 适配层）+ start.main.js（主逻辑）
                                      + start.snake.js + start.import.js
                                      ——六文件（WB-120，2026-09-26 审计：
                                      此前漏计 start.js/start.main.js）+
                                      manifest.txt（资产清单）+ wallpapers/
shared/release.json                   版本/分发单源（verify_versions 校验）
```

> 受信虚拟主机清单（WB-213，2026-10-02 审计同步——原文本未列）：Windows
> 正典栈以 WebView2 SetVirtualHostNameToFolderMapping 加载单源 UI——
> `https://ntp.aegis.local`（映射发布输出 ntp/ 目录：首页资产）与
> `https://geo.aegis.local`（映射随包 GeoGebra 画板资源；资源未随包不映射
> ——入口 fail-closed 置灰）。两台均 AccessKind=Deny（跨源 fetch/热链
> 探测一律失败——CS-334）；桥能力仅 ntp 顶层文档放行。
> 逐项语义与信任假设见 docs/threat-model/trust-boundaries.md。

### 1.5 发布链（release/ + .github/workflows）

- 更新验证：update_verifier（SemVer precedence 防回滚）+ verify_manifest
  （签名阈值单源读 signing-policy.yaml）
- CI：**15 workflow 分层**（WB-160，2026-10-01 审计对齐实树——原「五门禁」
  漏计 ci/legacy-python-guard 等；第八轮 B8 由 13 更正为 15——其后新增
  gradle-dependency-graph / gradle-dependency-insight 两个而计数静默漂移，
  现由 `scripts/check_doc_claims.py` 逐处与实树对账）。常跑门禁 6（push/PR：
  ci UI 回归 / core-rust / contracts / android-quality / supply-chain /
  agent-redteam）+ 组合冒烟 1（native-policy-artifacts，master+paths）+ 周定时 2
  （compat WebView2 探测 / legacy-python-guard 归档守护）+ 依赖面 2
  （gradle-dependency-graph：push:android/** + 周一 + dispatch；
  gradle-dependency-insight：仅 dispatch）+ 发布链 4
  （release.yml 编排 v* 标签 + release-windows/android/core 三平台子流）

### 1.6 归档（只读——禁止修复）

```
legacy/windows-pywebview/             原 PyWebview 栈（ADR-009 D4 冻结纪律；
                                      WebView2-Compat 定时自检仍对其探测）
legacy/（Qt、ui/）                    死代码
```

## 二、框架结构（裁决流水线）

```
用户/页面 → Host/地址栏 → C# Broker（Android 对应 AegisWebViewClient）
  → Rust 策略核心（导航裁决——safe_url/黑名单/高危判定/nonce；
     动作与能力评估层不在该通路（H-7），由托管 Broker 判定）
  → 授权放行 → WebView2 / System WebView 加载
  → 全程审计脱敏 + KillSwitch 强制检查
```

安全不变量：**Default Deny（fail-closed）**——任何导航/下载/桥调用未经
裁决链放行即拒绝；拒绝必须用户可见（弹窗/Toast，禁止静默 return）。

## 三、逻辑关联

### 单源锚点（改动必经核对）
- 版本：shared/version.properties 单源 → 4 文件同步（verify_versions 门禁）
- 守卫 JS：contracts/schemas/bridge_guard.template.js → 三端编译期归一
- 首页：shared/shell/ 六文件（start.html/css/js/main/snake/import——
  WB-120，2026-09-26 审计改计）+ manifest.txt 资产清单 → Android gradle
  assets 整目录打包；引擎/壁纸清单 → verify_cross_end_lists.py 对账

### 关键数据流（4 条）
① 导航流：输入 → Broker 决策 → Rust 裁决 → WebView 加载 → 审计
② 会话流（Android）：registerSession → 每次导航前 renewSession（TTL 单源）
③ 发布流：tag → CI 构建 → 签名/校验（fail-closed）→ 安装包/ZIP 分发
④ 回归流：四栈回归（node ui-regression + snake / dotnet Core+Broker 套件 /
  cargo test / gradle 四模块单测）+ pytest 发布链 + parity 勾验 + 真机走查
  runbook（WB-159，2026-10-01 审计改述——selftest 已随 SP-041/SP-151 降为
  legacy 归档守护，不再是回归正典）

## 四、演进史（六阶段，详见 docs/adr/）

Qt 旧栈 → PyWebview 分层（白名单/NavQueue）→ 安全纵深 → 契约治理
（import-linter/bridge_guard）→ Android 双端扩展 → **C# 全面迁移终局**
（M1-M4 落地，Python 栈冻结归档，Rust 升格导航裁决单源）

## 五、结论

**Aegis = C# 正典壳 + Rust 导航裁决单源 + Kotlin 双端 + 单源 UI/契约 +
分层 CI（15 workflow——第八轮 B8 按实树更正）的双端安全浏览器**——安全不变量
跨端一致，演进以 ADR 治理。
