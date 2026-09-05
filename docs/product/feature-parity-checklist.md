# 功能 Parity 清单（C# 迁移验收核对表）

> 依据 ADR-009 D3/D4：每迁移一项，在此勾验并附 PR 链接。**安全列**为该项的
> 安全门禁要求——功能与安全同 PR 接线（缺一不验收）。M = 里程碑归属。
> 清单基准 = Python 现役栈全部功能（全面审计 2026-09-04 盘点）+ 审计缺口项
> （C# 版超越 Python 的部分标 ▲）。

## M1 骨架可用

| 功能 | 安全门禁要求 | Python 参考 | C# 状态 |
|---|---|---|---|
| 多标签：新建/关闭/切换 | 每标签独立会话/broker session | tab_ops.py | ☑ M1-T1（TabManager/TabRuntime/原生标签条） |
| 多标签：拖拽排序 | — | tabstrip_js.py | ☑ M1-T3（ListBox 原生拖放 + TabManager.MoveTab 单测——当前标签索引随动） |
| 标签标题/进度实时同步 | 无 DOM 泄露（原生 UI 天然满足） | bridge_hooks | ☑ M1-T3（DocumentTitleChanged→INPC 原生绑定；不定态加载条接线导航开始/完成） |
| 地址栏：focus 选中/Enter 导航 | safe_url 双层校验经 broker | shell_toolbar | ☑ M1-T3（Enter 导航；Ctrl+L 与点击聚焦均全选） |
| 地址栏：搜索词 vs URL 判定 | 与 Android SearchEngines 同语义 | url_utils.normalize_url | ☑ M1-T3（UrlNormalizer 单源——fail-closed 拒绝非导航协议） |
| 加载进度条 | — | （Python 缺失▲） | ☑ 不定态指示条（WebView2 无进度事件——架构限制内的最优实现；M1-T3 完成接线） |
| 后退/前进/刷新/主页 | 导航经 broker 决策+consume | navigation.py | ☑ M1-T3（←/→/⟳/■/⌂ 全钮——最终经 NavigationStarting→broker） |
| 会话恢复（自动+手动） | 恢复 URL 过 safe_url | session_store.py/tab_ops.seed | ☑ M3 全量（自动恢复 M1-T1；手动入口=NTP 恢复按钮——恢复期抑制落盘，URL 仍逐条过 broker） |
| NewWindowRequested 门禁 | 白名单 fail-closed + 审计 | 批次1 native_interception | ☑（HostWebView Handled——既有语义保持） |
| WebView2 功能收紧 | AreHostObjects/ScriptDialogs=false | 批次1 hardening | ☑（原生直写+留痕） |
| ESM（探测启用） | 显式留痕 | 批次1 enhanced_security | ☑（SDK 未暴露 API——反射探测，升级自动生效） |
| ProcessFailed 崩溃监听 | 崩溃落盘 | 批次1 crash_listener | ☑（SecurityLog） |
| 指纹防护（文档创建前注入） | 会话种子/管道移植 | fingerprint_pipeline | ☑ 最小有效集（canvas 离屏扰动修 Python 污染缺陷/时间精度）；全量随 M3 |
| 威胁黑名单：订阅刷新 | https 强制/5MB 上限/原子落盘 | threat_feed.py | ☑（AEGIS_THREAT_FEED_URL 环境变量；M4 移入设置） |
| 威胁黑名单：导航门禁 | 命中拒绝+审计 | url_utils/security.py | ☑（broker threat_blocklist + 子资源 403 真拦截▲） |
| DNT 请求头 | request_sent 等价物（原生事件） | 批次1 request_policy | ☑（WebResourceRequested 原生注入） |
| per-origin 设置翻转 | 远程页禁 WebMessage/弹窗 | 批次1 per-origin | ☑ M1-T2（SetPerOrigin 原生直翻——每次顶层/子框架导航） |
| 错误页（导航失败/SSL） | SSL 绝不绕过——展示不 proceed | （Python 缺失▲） | ☑ M1-T3（导航失败横幅——仅展示无 proceed 通道；确认拒绝同样可见） |
| **M1 真机验收** | 连续真实浏览 1 小时无阻断 | — | ☑ M1-T1 冒烟通过（#19）+ M1-T3 拓展功能合并；正式 1 小时走查待发布前复验（ADR-009 D5） |

## M2 数据闭环

| 功能 | 安全门禁要求 | Python 参考 | C# 状态 |
|---|---|---|---|
| 书签：SQLite 存储/增删查 | 写操作来源受信（原生 chrome 天然受信） | bookmark_store.py | ☑ M2 |
| 书签：收藏☆（当前页 toggle） | URL 服务端取（零页面可控参数） | 批次3 toggle_bookmark | ☑ M2（工具栏☆+反馈条） |
| 书签：新标签页宫格 | 渲染数据经宿主注入而非页面读取 | start.html renderBookmarks | ☑ M3（NtpBridge WebMessage 注入 title/url——仅受信 ntp.aegis.local 来源） |
| 书签：Chrome/Edge 导入向导 | 只读打开历史库（immutable） | browser_import.py | ☑ M3（NTP 导入向导单源 UI——历史库拷贝只读副本打开，锁定安全；书签解析只读） |
| 历史：记录/搜索 | 记录脱敏（无 query secret） | history_store.py | ☑ M2+M4（搜索/查看/清除已 M2；**记录缺口 2026-09-05 补齐**——导航完成落库，内部页首页/画板/空白页过滤不入历史，后台标签同样记录，受 HistoryEnabled 开关门控） |
| 历史：查看/清除 UI | 清除不可恢复提示 | （Python 缺失▲） | ☑ M2（HistoryWindow+二次确认） |
| 搜索引擎：四引擎切换 | 偏好写入经受信校验 | search_engine.py | ☑ M2（ComboBox+AppSettings） |
| **M2 真机验收** | 导入→收藏→搜历史→清理全流程 | — | ☐ 待真机（导入向导已迁移至 NTP——随 M4 发布走查一并执行） |

## M3 功能补齐

| 功能 | 安全门禁要求 | Python 参考 | C# 状态 |
|---|---|---|---|
| 下载管理器：进度/暂停 | DownloadStarting 经 broker 授权 | （Python 不支持▲） | ☑ M3+M4（原生下载+broker 审计+反馈；M4 下载管理面板——进度/暂停/继续/取消/打开所在文件夹，全部受信 chrome 直达原生 API） |
| 下载：危险扩展拦截+确认 | 扩展判定对齐 Android DownloadPolicy | security.is_dangerous | ☑ M3+M4（扩展判定+查询串强判定；审计 M4 补接原生确认对话框——此前仅判定未接线门禁形同虚设；窗口关闭仍 fail-closed） |
| 下载：文件名净化 | 剥路径段/控制字符/尾点 | 批次1 Android sanitize | ☑ M3（对齐 Android 语义） |
| 新标签页：start.html 虚拟主机 | 资源映射不暴露文件系统 | shell/start.html | ☑ M3（SetVirtualHostNameToFolderMapping→发布输出 ntp/ 目录——shared/shell 跨端单源） |
| 新标签页：会话恢复入口 | has_saved/restore 经 broker | start.html restoreBox | ☑ M3（NtpBridge hasSaved/restoreSession——恢复 URL 仍逐条过 broker） |
| 页面源码查看器 | 抓取复用 safe_url+大小上限+全转义 | api_bridge.view_source | ☑ M3（Ctrl+U+独立窗口+零脚本执行） |
| 壁纸切换 | — | bridge/wallpaper.py | ☑ M3（白名单四张随单源 shell/wallpapers；AppSettings.NtpWallpaper 持久化——NtpBridge 校验） |
| 离线几何画板 | 内部资源固定 URI | bridge/geogebra.py | ☑ M3（geo.aegis.local 虚拟主机映射固定路径；资源未随包 fail-closed 置灰——与 Python 同语义） |
| 贪吃蛇 | — | start.snake.js | ☑ M3（start.snake.js 单源覆盖层随 NTP 加载） |
| 指纹防护全量管道 | canvas 噪声仅扰动读路径（修 Python 缺陷） | fingerprint_pipeline | ☑ M3（FingerprintShield 红蓝对抗全量原生移植——每会话 32 字节随机种子；canvas 离屏副本扰动不写回可见画布；6 个单测锁定脚本契约） |
| 链接点击门禁 | 原生处理（无需客户端快照 hack） | 批次2 link_intercept | ☑ 原生架构天然满足（NavigationStarting 全量经 broker） |
| **M3 真机验收** | 下载/画板/新标签页全流程 | — | ☐ 待真机（随 M4 发布走查一并执行——ADR-009 D5） |

## M4 收尾退役

| 功能 | 安全门禁要求 | Python 参考 | C# 状态 |
|---|---|---|---|
| 设置界面（原生） | 每字段必须有消费者（诚实性门禁） | config.py 影子字段清理 | ☑ M4-b（#23 SettingsWindow——威胁订阅源 https 校验；AppSettings 字段全量有消费者：SearchEngine/HistoryEnabled/ThreatFeedUrl/NtpWallpaper） |
| KillSwitch 接线 | 全仓可审计 | broker/KillSwitch.cs | ☑ M4-a（#23——broker 单例，导航评估/下载/批准链三处强制检查，engaged 时 deny+审计） |
| ApprovalManager 接线 | 与 Rust 核心确认流对齐 | broker/Approval | ☑ 处置（#24——审计确认冗余原型，删除；确认流由 Rust 原生核心唯一承担） |
| 下载管理面板 | 原生 API 仅受信 chrome 可达 | （Python 不支持▲） | ☑ M4（#b95a4e8 DownloadsWindow——进度/暂停/继续/取消/打开所在文件夹） |
| 发布链单轨 | 仅 C# 制品，PyInstaller 包移除 | release-windows.yml | ☑ M4（installer-pywebview job 删除——C# 安装包为唯一 Windows 制品，SBOM/SLSA 链不变） |
| Python 栈归档（只读） | 归档声明 + 仅 P0 安全通道 | legacy/windows-pywebview | ☑ M4（归档声明入 README——功能/安全修复不再在该栈进行） |
| 文档终版口径 | README/CLAUDE.md/本清单 100% | — | ☑ M4（终局口径：C# 唯一正典栈+唯一制品；ADR-009 执行状态注记） |
| **M4 真机验收** | 安装包全新机器全功能走查 | — | ☐ 待真机（需安装包环境人工走查——CI 绿为必要非充分条件，ADR-009 D5） |
