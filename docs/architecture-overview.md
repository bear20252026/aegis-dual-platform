# Aegis 架构全景文档（architecture-overview）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> 目的：让人一眼读懂本项目整体逻辑框架——完整代码树 + 框架结构 +
> 逻辑关联 + 模块化设计进程
> 依据：实际代码树（glob 核实 27 Python 核心文件 + 10 Kotlin + 21 文档）
> + import-linter 契约 + 多轮开发历程

---

## 一、完整代码树（分类标注职责）

### 1.1 Windows 端（Python，核心 27 文件 5078 行）

```
windows/aegis_source/
├── main_webview.py            （567 行）入口层：薄壳启动组装
├── crash_reporter.py          （276 行）基础设施：崩溃报告 + 日志
├── selftest_s1_integration.py （114 行）测试：S1 集成自检
├── selftest_api_bridge.py     （ 94 行）测试：桥自检
├── selftest_shell_toolbar.py  （ 81 行）测试：工具栏自检
├── app/
│   ├── api_bridge.py          （568 行）桥层：js_api 白名单 27 方法
│   ├── shell_toolbar.py       （447 行）业务-UI：注入工具栏/快捷键/hints
│   ├── webview2_probe.py      （312 行）基础设施：性能基线监控
│   ├── config.py              （255 行）业务-存储：类型化配置
│   ├── shell_adapter.py       （244 行）壳抽象：Shell 协议 + 可插拔实现
│   ├── mcp.py                 （227 行）业务-能力：Agent 白名单 7 工具
│   ├── history_store.py       （217 行）业务-存储：历史持久化
│   ├── nav_queue.py           （207 行）业务-导航：异步消息驱动
│   ├── threat_feed.py         （183 行）业务-安全：威胁黑名单订阅
│   ├── bookmark_store.py      （158 行）业务-存储：书签持久化
│   ├── security.py            （154 行）业务-安全：safe_url 协议白名单
│   ├── database.py            （148 行）业务-存储：数据库助手
│   ├── reader.py              （135 行）业务-能力：阅读模式
│   ├── browser_import.py      （135 行）业务-能力：浏览器数据导入
│   ├── asset_scheme.py        （119 行）业务-安全：壁纸资源白名单
│   ├── fingerprint.py         （104 行）业务-能力：指纹/UA 配置（默认关）
│   ├── backdrop.py            （ 81 行）业务-能力：亚克力背景
│   ├── paths.py               （ 71 行）业务-存储：数据目录解析
│   ├── bridge_hooks.py        （ 59 行）业务-能力：桥钩子
│   ├── url_utils.py           （ 53 行）业务-安全：URL 工具
│   ├── credential_guard.py    （ 41 行）业务-安全：凭据脱敏
│   ├── event_log.py           （ 27 行）基础设施：统一日志接口
│   └── __init__.py            （  1 行）包标记
└── legacy/                    （36 文件）Qt 旧栈（不参与运行，保留参考）
```

### 1.2 Android 端（Kotlin，10 文件）

```
android/app/src/main/java/com/aegis/browser/
├── MainActivity.kt        入口：Activity 组装
├── BrowserEngine.kt       引擎：WebView 封装
├── TabManager.kt          标签管理
├── Tab.kt                 标签模型
├── TabBar.kt / VerticalTabBar.kt  标签栏（横/竖）
├── SecureWebViewFactory.kt 安全：WebView 工厂（同安全理念）
├── DownloadPolicy.kt      下载策略
├── AegisTheme.kt / UiColors.kt 主题/配色
```

### 1.3 文档（21 份 + KNOWLEDGE_BASE 15 节）

审计类（audit-2026/audit-report/expert-audit-report/privacy-defaults）+ 调研类
（open-source-browser-audit/source-study-report/browser-ecosystem/rust-desktop
/tauri-migration×2/pytauri-technical）+ 计划类（optimization-plan/threat-context
/tech-evolution）+ 架构类（pytauri-capabilities-mapping/code-quality-assessment）
+ KNOWLEDGE_BASE.md（15 节项目记忆）

## 二、框架结构（六层架构）

```
入口层(main_webview) → 壳抽象层(shell_adapter) → 桥层(api_bridge)
  → 业务层(导航/UI/安全/存储/能力) → 基础设施(crash_reporter/event_log/probe)
  → 测试层(selftest×3)
```
混合原生壳 + 异步消息驱动（NavQueue）——2026 最佳实践落地。

## 三、逻辑关联结构

### 依赖图（单向分层 + 星形收敛）
- 星形枢纽：**api_bridge**（业务模块收敛）+ **event_log**（日志收敛）
- 分层单向：main_webview → app/* → crash_reporter（import-linter 契约强制）
- 独立性：nav_queue/threat_feed/credential_guard 互不依赖（契约验证 ✅）

### 关键数据流（5 条）
① 用户操作流（前端→js_api→api_bridge→NavQueue→窗口→回前端）
② 导航拦截流（request_sent→管线 DNT/威胁标记→导航层 deny 优先）
③ 威胁数据流（订阅→签名→缓存→双关口查询）
④ 日志流（业务→event_log→crash_reporter（脱敏）→events.log）
⑤ 崩溃流（线程异常→crash_reporter→crash_reports/）

## 四、模块化设计进程（六阶段）

Qt 旧栈（36 文件，弃用）→ pywebview 分层重构（白名单双关口/NavQueue/
统一管线）→ 安全纵深强化（凭据治理/ESM/deny 优先/credential_guard）→
壳抽象（shell_adapter 可插拔，禁止被困）→ 契约治理（import-linter +
event_log 统一）→ Android 双端扩展（Kotlin 10 文件）

## 五、结论

**Aegis = 六层分层 + 星形收敛 + 壳可插拔 + 契约治理的双端浏览器**——
代码树清晰、逻辑关联可推理、演进方向持续降耦（符合 2026 最佳实践）。
