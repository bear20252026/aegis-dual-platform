# WebView2 WebExtension 生态调研（R5）

> 调研日期：2026-08-15 ｜ 目标：评估 Aegis Windows 端（pywebview + WebView2）接入浏览器扩展的可行性
> 结论先行：**技术可行（BYO 机制），但受平台限制明显，建议以"有限扩展 + 内置优先"策略推进**

---

## 一、WebView2 扩展支持的官方现状（2026-08）

| 项 | 状态 | 说明 |
|---|---|---|
| 默认行为 | **关闭**（Browser Extensions: Off） | 官方 `browser-features.md` 明确：默认关闭且"不可配置"（指无 GUI 开关） |
| 开启方式 | `CoreWebView2EnvironmentOptions.AreBrowserExtensionsEnabled = true` | 必须通过代码创建环境时开启 |
| 安装方式 | **BYO（Bring Your Own）** | 微软明确不支持从 Edge Store 直接安装（Edge 与 WebView2 是不同实体，许可证不通用） |
| 加载 API | `ICoreWebView2Profile.AddBrowserExtensionAsync(installerPath)` | 自 WebView2 1.0.2210.55 起支持；加载**本地未打包扩展目录** |
| 扩展来源 | 开发者自备 | 可从 Edge Store 用 `crx` 下载链接取回 .crx → 解压为目录后加载（社区已验证） |
| 配套事件 | `CoreWebView2Initialized` | 环境初始化完成后可安全调用扩展 API |

## 二、关键约束与风险

1. **无扩展管理 UI**：WebView2 不提供 `edge://extensions` 页面，扩展的启用/禁用/图标/options 页均需宿主自己实现（社区 issue #3259 仍在开放）。
2. **无法访问 Store 直达**：官方 API 不提供"按扩展 ID 从商店安装"；需开发者自行获取 .crx 并解压。
3. **MV2 → MV3 过渡（2026）**：
   - 2026-08 起 Edge 消费者端开始 MV2 弃用提示；2026 年底消费者完成过渡
   - 2027 年初企业端弃用 MV2
   - **新接入的扩展必须面向 MV3**（Aegis 若做扩展支持，只应加载 MV3 扩展）
4. **pywebview 集成难度**：pywebview 的 winforms 后端未直接暴露 `CoreWebView2EnvironmentOptions`/`Profile.AddBrowserExtensionAsync`；社区方案是自写 C++/C# loader DLL 包装 `CreateCoreWebView2EnvironmentWithOptions` 并设置 `AreBrowserExtensionsEnabled`，再供 Python 调用（issue #3694 中有完整示例）。
5. **安全边界**：加载第三方扩展 = 引入任意代码执行面，与 Aegis"安全第一"承诺冲突，必须做扩展白名单/来源校验。

## 三、对 Aegis 的落地建议（分级）

### 立即可行（低成本、零风险）
- **不接入**：维持现状，扩展生态定位为"后续里程碑"。理由：pywebview 桥接需自写 loader DLL（C++ 维护成本），且第三方扩展的安全风险与政府项目定位不符。

### 中期可选（中等成本）
- **内置化高频能力**：把用户最常装的扩展能力（广告拦截、翻译、下载管理）继续内置做强——Aegis 已有 adblock/translate/download，可补**密码自动填充**（WebView2 有 Autofill API，默认关闭可开启）。
- **有限扩展支持（BYO + 白名单）**：若确需扩展：
  1. 自写 loader DLL 开启 `AreBrowserExtensionsEnabled`
  2. `AddBrowserExtensionAsync` 仅加载**经审核白名单**的本地 MV3 扩展目录
  3. 校验扩展 manifest（name/id/version/权限声明）后才加载
  4. 提供最小扩展管理 UI（启用/禁用/查看 manifest）

### 不建议
- 直接暴露"任意扩展安装"入口（安全面过大）
- 现在投入 C++ loader 开发（WebView2 扩展 API 仍在演进，社区 issue 表明图标/options 页等仍缺失）

## 四、结论

> WebView2 的扩展支持是 **BYO + 白名单式**的，技术上可接入（自写 loader + `AddBrowserExtensionAsync`），但：
> - 生态成熟度不足（无 UI、无 Store 直达、MV2→MV3 过渡期）
> - 与 pywebview 桥接需 C++ 维护成本
> - 第三方扩展与 Aegis"安全第一 / 政府项目"定位冲突
>
> **建议**：短期不接入，继续"内置优先"（补密码自动填充等高频能力）；中期若做，采用"白名单 MV3 本地扩展 + 校验 + 最小管理 UI"的受限方案。此决策已记录至 KNOWLEDGE_BASE.md 待办表。
