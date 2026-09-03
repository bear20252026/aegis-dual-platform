# 功能 Parity 清单（C# 迁移验收核对表）

> 依据 ADR-009 D3/D4：每迁移一项，在此勾验并附 PR 链接。**安全列**为该项的
> 安全门禁要求——功能与安全同 PR 接线（缺一不验收）。M = 里程碑归属。
> 清单基准 = Python 现役栈全部功能（全面审计 2026-09-04 盘点）+ 审计缺口项
> （C# 版超越 Python 的部分标 ▲）。

## M1 骨架可用

| 功能 | 安全门禁要求 | Python 参考 | C# 状态 |
|---|---|---|---|
| 多标签：新建/关闭/切换 | 每标签独立会话/broker session | tab_ops.py | ☑ 骨架（M1-T1：TabManager/TabRuntime/原生标签条；拖拽排序独立行） |
| 多标签：拖拽排序 | — | tabstrip_js.py | ☐ |
| 标签标题/进度实时同步 | 无 DOM 泄露（原生 UI 天然满足） | bridge_hooks | ☐ |
| 地址栏：focus 选中/Enter 导航 | safe_url 双层校验经 broker | shell_toolbar | ☐ |
| 地址栏：搜索词 vs URL 判定 | 与 Android SearchEngines 同语义 | url_utils.normalize_url | ☐ |
| 加载进度条 | — | （Python 缺失▲） | ☐ |
| 后退/前进/刷新/主页 | 导航经 broker 决策+consume | navigation.py | ☐ |
| 会话恢复（自动+手动） | 恢复 URL 过 safe_url | session_store.py/tab_ops.seed | ☑ 自动恢复（M1-T1：SQLite+启动还原）；手动入口随 M3 新标签页 |
| NewWindowRequested 门禁 | 白名单 fail-closed + 审计 | 批次1 native_interception | ☐ |
| WebView2 功能收紧 | AreHostObjects/ScriptDialogs=false | 批次1 hardening | ☐ |
| ESM（探测启用） | 显式留痕 | 批次1 enhanced_security | ☐ |
| ProcessFailed 崩溃监听 | 崩溃落盘 | 批次1 crash_listener | ☐ |
| 指纹防护（文档创建前注入） | 会话种子/管道移植 | fingerprint_pipeline | ☐ |
| 威胁黑名单：订阅刷新 | https 强制/5MB 上限/原子落盘 | threat_feed.py | ☐ |
| 威胁黑名单：导航门禁 | 命中拒绝+审计 | url_utils/security.py | ☐ |
| DNT 请求头 | request_sent 等价物（原生事件） | 批次1 request_policy | ☐ |
| per-origin 设置翻转 | 远程页禁 WebMessage/弹窗 | 批次1 per-origin | ☐ |
| 错误页（导航失败/SSL） | SSL 绝不绕过——展示不 proceed | （Python 缺失▲） | ☐ |
| **M1 真机验收** | 连续真实浏览 1 小时无阻断 | — | ☐ |

## M2 数据闭环

| 功能 | 安全门禁要求 | Python 参考 | C# 状态 |
|---|---|---|---|
| 书签：SQLite 存储/增删查 | 写操作来源受信（原生 chrome 天然受信） | bookmark_store.py | ☐ |
| 书签：收藏☆（当前页 toggle） | URL 服务端取（零页面可控参数） | 批次3 toggle_bookmark | ☐ |
| 书签：新标签页宫格 | 渲染数据经宿主注入而非页面读取 | start.html renderBookmarks | ☐ |
| 书签：Chrome/Edge 导入向导 | 只读打开历史库（immutable） | browser_import.py | ☐ |
| 历史：记录/FTS5 搜索 | 记录脱敏（无 query secret） | history_store.py | ☐ |
| 历史：查看/清除 UI | 清除不可恢复提示 | （Python 缺失▲） | ☐ |
| 搜索引擎：四引擎切换 | 偏好写入经受信校验 | search_engine.py | ☐ |
| **M2 真机验收** | 导入→收藏→搜历史→清理全流程 | — | ☐ |

## M3 功能补齐

| 功能 | 安全门禁要求 | Python 参考 | C# 状态 |
|---|---|---|---|
| 下载管理器：进度/暂停 | DownloadStarting 经 broker 授权 | （Python 不支持▲） | ☐ |
| 下载：危险扩展拦截+确认 | 扩展判定对齐 Android DownloadPolicy | security.is_dangerous | ☐ |
| 下载：文件名净化 | 剥路径段/控制字符/尾点 | 批次1 Android sanitize | ☐ |
| 新标签页：start.html 虚拟主机 | 资源映射不暴露文件系统 | shell/start.html | ☐ |
| 新标签页：会话恢复入口 | has_saved/restore 经 broker | start.html restoreBox | ☐ |
| 页面源码查看器 | 抓取复用 safe_url+大小上限+全转义 | api_bridge.view_source | ☐ |
| 壁纸切换 | — | bridge/wallpaper.py | ☐ |
| 离线几何画板 | 内部资源固定 URI | bridge/geogebra.py | ☐ |
| 贪吃蛇 | — | start.snake.js | ☐ |
| 指纹防护全量管道 | canvas 噪声仅扰动读路径（修 Python 缺陷） | fingerprint_pipeline | ☐ |
| 链接点击门禁 | 原生处理（无需客户端快照 hack） | 批次2 link_intercept | ☐ |
| **M3 真机验收** | 下载/画板/新标签页全流程 | — | ☐ |

## M4 收尾退役

| 功能 | 安全门禁要求 | Python 参考 | C# 状态 |
|---|---|---|---|
| 设置界面（原生） | 每字段必须有消费者（诚实性门禁） | config.py 影子字段清理 | ☐ |
| KillSwitch 接线 | 全仓可审计 | broker/KillSwitch.cs | ☐ |
| ApprovalManager 接线 | 与 Rust 核心确认流对齐 | broker/Approval | ☐ |
| 发布链单轨 | 仅 C# 制品，PyInstaller 包移除 | release-windows.yml | ☐ |
| Python 栈归档（只读） | 归档声明 + 仅 P0 安全通道 | legacy/windows-pywebview | ☐ |
| 文档终版口径 | README/CLAUDE.md/本清单 100% | — | ☐ |
| **M4 真机验收** | 安装包全新机器全功能走查 | — | ☐ |
