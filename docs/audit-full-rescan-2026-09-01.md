# Aegis 全量复审报告（2026-09-01）

> 触发：v2.1.8 真机回归发现新 P0（会话 TTL 锁死）后，按用户要求对三端做整体重新全扫描。
> 方法：三路并行深扫（Android 会话/导航链路、Windows 桥接/信任机制、Rust 核心 FFI/共享层）。

## P0（功能不可用，必须发版修复）

| # | 位置 | 问题 | 修复方向 |
|---|------|------|----------|
| P0-A | `android/broker/.../AndroidBroker.kt:43` | `createSession` 写死 `ttl=120` 秒，无任何续期 → 应用启动 2 分钟后**所有导航被 session_expired 拒绝**（真机已复现：重启后 2 分钟内 baidu.com 可开，超时后连搜索词都被拒） | Rust `create_session` 对同 session_id 是覆盖式重注册（重置 created_at），Android 定时重调 registerSession 即可续期，**无需改 Rust** |
| P0-B | `android/webview-adapter/.../AegisWebViewClient.kt:158-160, 198-201` | `Decision.Deny`（含 session_expired）直接 `return false`，无回调无 UI；过期后 `stopLoading()` 白屏无解释 | 增加 onNavigationDenied 回调 → ViewModel 弹"会话过期"提示 |
| P0-C | `android/app/.../AegisHomeBridge.kt:103` | `navigateExternal(url)` 返回值被丢弃 → 首页搜索/地址栏跳转在过期后完全静默 | 失败时回传 JS / Toast |

## P1（主路径受损）

| # | 端 | 位置 | 问题 |
|---|-----|------|------|
| P1-3 | Android | `SecureWebViewFactory.kt:80` | onRendererGone 是 no-op，渲染进程崩溃后标签永久白屏 |
| P1-4 | Android | `AegisWebViewClient.kt:103-107` | 确认框打开期间新导航被静默吞（既不弹窗也不提示） |
| P1-5 | Android | `NativePolicyCoreBridge.kt:121-142` | 桥异常全部静默吞、无日志，故障只能靠"2 分钟后全挂"反推 |
| P1-6 | Android | `BrowserEngine.kt:85-97` | 地址栏永不随实际页面同步（重定向/页内跳转后显示陈旧 URL），导航失败后输入框不复位 |
| P1-7 | Windows | `app/shell_toolbar.py:146` | 菜单按钮调 `pywebview.api.show_menu()`，该方法无实现且不在 `_JS_EXPOSED` 白名单 → 菜单功能完全失效 |
| P1-8 | Windows | `main_webview.py:439/458`、`tab_ops.py:148-151`、`nav_queue.py:54` | 会话恢复 URL 只过 session_store 前缀白名单，未经 `safe_url` + 威胁黑名单 → 被篡改的 session.json 可绕过黑名单 |
| P1-9 | Windows | `main_webview.py:44/145` vs `tab_ops.py:205-212` | Agent 白名单两层不一致（请求层硬编码空集不读环境变量）→ Agent 会话期间每请求误报 |
| P1-10 | Rust/FFI | `ffi/broker.rs:92`、`AndroidBroker.kt:137` | action `expires_at` 双端各硬编码 120 秒，与慢速审批链路冲突（`action_expired`） |
| P1-11 | Rust | `ffi/broker.rs:324-344` | ttl_seconds 无下限校验（ttl=0 即刻过期），无常量默认值 |
| P1-12 | 共享 | `shared/shell/start.html:653-658` | `openGeo` 回调引用未定义变量 `ok`，画板加载失败时按钮不置灰 |

## P2（边角，随迭代）

- Android：consumedNonces 无界增长（`AndroidBroker.kt:86`）；TabManager 死代码/后台标签 JS 未暂停；"打开"按钮无防抖连点会撤销确认并弹误导提示；address 全局单字段多标签覆盖（`BrowserViewModel.kt:30`）。
- Windows：信任判定在 `current_url()` 异常时误判受信（`navigation.py:100-101`）；Agent 会话续期在工具执行后（长工具 >60s 静默失效，`mcp.py:322`）；`new_tab` 忽略用户引擎固定百度（`tab_ops.py:260`）；中文长查询超 8192 静默拒（`security.py:49`）；`navigate` 拒绝/`new_tab` 频控/壁纸/引擎设置/恢复会话/GeoGebra 六处桥方法静默失败无反馈；右键"新标签打开"实为当前页导航（`shell_toolbar.py:202-204`）。
- 共享：start.html `getEngine` parse 失败静默 cb(null) → 引擎胶囊无响应。

## 自测覆盖缺口（selftest_navigation_search.py 待补）

new_tab(url) 路径、启动/恢复 URL 链路、右键新标签/搜索、超长 URL、IP 直连、中文域名 punycode、http:// 明文一致性。

## 确认无问题项

- 多标签会话隔离（每标签独立 session/tabId，关闭注销）✅
- Windows 端无 TTL 锁死（信任判定无时效；Agent 会话过期是降级放行）✅
- FFI 内存安全 fail-closed（null/非法 UTF-8/panic 全部转 deny）✅
- 规则加载 fail-closed（无规则=全拒，不会放行）✅
- file:/javascript:/data: 等全链拒绝、空输入回首页、http:// 三层一致 ✅

## 修复批次建议

1. **批次一（P0，本轮必修）**：Android 会话滑动续期（定时重调 registerSession，周期 <120s）+ Deny 时用户可见反馈（P0-B/C）+ NativePolicyCoreBridge 补日志。补真机回归测试 2/3/4。
2. **批次二（P1）**：渲染崩溃恢复、确认框新导航、地址栏同步、Windows 菜单 show_menu、会话恢复安全链、Agent 白名单统一、action TTL 常量单源、ttl 下限、start.html openGeo。
3. **批次三（P2 + 自测补齐）**。
