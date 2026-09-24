# Aegis 架构全景文档（architecture-overview）

> **权威入口声明**（SP-004 整改）：本文件是项目架构蓝图与 agent/README 的
> 权威汇入点。2026-09-24 全面审计 WB-009 整改重写——旧版仅描述 Python
> 27 文件视图，已与「C# 唯一正典栈」终局（ADR-007/009）严重漂移。
> 编制日期：2026-09-24 ｜ 终局口径：ADR-007（单一正典）+ ADR-008
> （Rust 唯一裁决者）+ ADR-009（C# 全面迁移完成）

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
└── docs/release/AegisSetup.iss         Inno Setup 发布（版本运行时注入）
```

### 1.2 Rust 策略核心（唯一裁决者——ADR-008）

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
└── reader/ translate/ 等              阅读模式 / 翻译入口
```

### 1.4 单源 UI（双端共享）

```
shared/shell/                         start.html（Host 适配层）+ start.css +
                                      start.snake.js + start.import.js
shared/release.json                   版本/分发单源（verify_versions 校验）
```

### 1.5 发布链（release/ + .github/workflows）

- 更新验证：update_verifier（SemVer precedence 防回滚）+ verify_manifest
  （签名阈值单源读 signing-policy.yaml）
- CI：Core-Rust / Android-Quality / Contracts / Supply-Chain / Agent-Redteam
  五门禁常跑 + release-*（构建型）+ WebView2-Compat（每周定时探测）

### 1.6 归档（只读——禁止修复）

```
legacy/windows-pywebview/             原 PyWebview 栈（ADR-009 D4 冻结纪律；
                                      WebView2-Compat 定时自检仍对其探测）
legacy/（Qt、ui/）                    死代码
```

## 二、框架结构（裁决流水线）

```
用户/页面 → Host/地址栏 → C# Broker（Android 对应 AegisWebViewClient）
  → Rust 策略核心（唯一裁决——safe_url/指纹/动作策略）
  → 授权放行 → WebView2 / System WebView 加载
  → 全程审计脱敏 + KillSwitch 强制检查
```

安全不变量：**Default Deny（fail-closed）**——任何导航/下载/桥调用未经
裁决链放行即拒绝；拒绝必须用户可见（弹窗/Toast，禁止静默 return）。

## 三、逻辑关联

### 单源锚点（改动必经核对）
- 版本：shared/version.properties 单源 → 4 文件同步（verify_versions 门禁）
- 守卫 JS：contracts/schemas/bridge_guard.template.js → 三端编译期归一
- 首页：shared/shell/ 四文件 → Android gradle assets 整目录打包
- 引擎/壁纸清单：start.html 主文件 → verify_cross_end_lists.py 对账

### 关键数据流（4 条）
① 导航流：输入 → Broker 决策 → Rust 裁决 → WebView 加载 → 审计
② 会话流（Android）：registerSession → 每次导航前 renewSession（TTL 单源）
③ 发布流：tag → CI 构建 → 签名/校验（fail-closed）→ 安装包/ZIP 分发
④ 回归流：selftest ×N + parity 勾验 + 真机走查 runbook

## 四、演进史（六阶段，详见 docs/adr/）

Qt 旧栈 → PyWebview 分层（白名单/NavQueue）→ 安全纵深 → 契约治理
（import-linter/bridge_guard）→ Android 双端扩展 → **C# 全面迁移终局**
（M1-M4 落地，Python 栈冻结归档，Rust 升格唯一裁决者）

## 五、结论

**Aegis = C# 正典壳 + Rust 唯一裁决 + Kotlin 双端 + 单源 UI/契约 +
五门禁 CI 的双端安全浏览器**——安全不变量跨端一致，演进以 ADR 治理。
