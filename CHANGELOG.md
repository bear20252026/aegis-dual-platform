# 变更日志（Changelog）

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added (Windows C# 正典栈——ADR-009 M4 收尾退役)
- **发布链单轨**：release-windows.yml 删除 installer-pywebview job——C# 安装包
  为唯一 Windows 发布制品（SBOM/SLSA attestation/校验和链对 C# 制品不变）；
  Python 栈（legacy/windows-pywebview）整体归档只读——仅 P0 安全缺陷经安全
  披露通道评估修复（归档声明入 legacy README）
- **文档终版口径**：README/CLAUDE.md 终局声明（C# 唯一正典栈+唯一制品；
  parity 清单代码项 100% 勾验）；ADR-009 执行状态注记（M1-M4 全部落地，
  M4 真机验收待发布走查）

### Added (Windows C# 正典栈——ADR-009 M4 下载管理面板)
- **DownloadsWindow 原生下载管理面板**（pywebview 天花板特性的完整兑现）：
  进度百分比/字节摘要/状态（进行中/已完成/已中断/已取消——UserCanceled
  单列）、暂停/继续/取消/打开所在文件夹，全部受信 chrome 按钮直达原生
  DownloadOperation API——远程页面无触达通道；工具栏 ⤓ 入口，新下载自动入列

### Added (Windows C# 正典栈——ADR-009 M3 指纹防护全量)
- **FingerprintShield 红蓝对抗全量管道原生移植**（fingerprint_pipeline.py →
  `WebView/FingerprintShield.cs`）：原型链检测防护/ToStringGuard/PerSiteSeed/
  Canvas/WebGL/Audio/Battery/Network/WebRTC 关闭/Letterbox/fetch·XHR 追踪参数
  剥离/字体枚举防护/时间精度收敛——每标签会话独立 32 字节加密随机种子；
  canvas 噪声仅在离屏副本上扰动读路径（绝不写回可见画布——修 Python 污染缺陷）；
  6 个单测锁定脚本构造契约（种子参数化/确定性/阶段齐备）

### Added (Windows C# 正典栈——ADR-009 M3 功能补齐)
- **新标签页（start.html 跨端单源）**：`SetVirtualHostNameToFolderMapping` 加载
  shared/shell（发布输出 ntp/ 目录——资源映射不暴露文件系统）；Host 适配层新增
  C# WebView2 postMessage 桥（第三适配——pywebview/Android 语义不变）
- **NtpBridge 宿主桥**：仅受信 ntp.aegis.local 来源可达（远程页 per-origin 关闭
  WebMessage + 桥双重校验）；壁纸白名单（对齐 Python asset_scheme.WALLPAPERS）、
  引擎切换、书签宫格数据注入、会话恢复入口、导航意图桥内归一后回归
  NavigationStarting→broker 唯一授权路径（12 个单测）
- **导入向导**：Chrome/Edge 书签（既有 BookmarkImporter 接线）+ 历史
  （HistoryImporter——urls 表拷贝只读副本解析，锁定安全；仅 http/https）
- **离线几何画板/贪吃蛇**：geo.aegis.local 虚拟主机（资源未随包 fail-closed
  置灰——与 Python 同语义）；贪吃蛇随单源 start.snake.js 开箱可用

### Added (Windows C# 正典栈——ADR-009 M1-T3)
- **M1 收尾（parity 清单 7 项勾验）**：标签条拖拽排序（ListBox 原生拖放 +
  `TabManager.MoveTab`——当前标签索引随动，3 个单测）；不定态加载指示条完成
  接线（导航开始显示/完成或失败隐藏）；地址栏聚焦全选（Ctrl+L 与鼠标点击同
  语义）；主页按钮（⌂）；per-origin 翻转与错误页横幅 parity 留痕

### Added (Windows C# 正典栈——ADR-009 M1-T1)
- **多标签骨架**：`Core/Tabs`（TabManager/Tab/TabSessionStore——纯逻辑领域层，
  14 个单测全绿）；每标签一 WebView2 实例（切换即可见性切换——页面状态/
  滚动/表单天然保留，架构性修复 Python 栈「切标签全量重载丢状态」缺陷）；
  原生标签条（新建 ✕关闭 点击切换——与页面 DOM 彻底隔离，ADR-003 彻底版）；
  每标签独立 broker 会话（session/tabId 账本键隔离）；Ctrl+T/Ctrl+W/Ctrl+L
  快捷键；会话 SQLite 持久化（导航完成即落盘——崩溃后重启恢复最后的页面
  集合；真机冒烟验证落盘）
- **依赖治理**：新增 Microsoft.Data.Sqlite 10.0.0（数据层统一 SQLite——
  ADR-009 D2），显式升级 SQLitePCLRaw 2.1.12（修复 NU1903 高危漏洞
  GHSA-2m69-gcr7-jv3q）

### 架构决策（2026-09-04：ADR-009——全功能迁移至 C#）
- **owner 拍板 B 路线终局**：C#/.NET 10 + 原生 WebView2 为唯一 Windows 正典栈，
  Python 现役栈全部功能迁移（保留功能不缩水）；`legacy/windows-pywebview/`
  进入**冻结维护**（只修 P0/P1 安全缺陷，功能 PR 一律拒绝）
- 目标架构：每标签一 WebView 实例、原生 WPF chrome（与页面 DOM 彻底隔离）、
  领域服务层（Core/Tabs|Bookmarks|History|Downloads|Settings，全部可单测）、
  SQLite+FTS5 数据层、AppSettings 强类型（杜绝影子配置）
- 迁移路线图 M1 骨架可用 → M2 数据闭环 → M3 功能补齐（含原生下载管理器——
  pywebview 天花板特性的原生兑现）→ M4 收尾退役（Python 归档+发布链单轨）
- 验收机械核对表：`docs/product/feature-parity-checklist.md`（安全门禁列
  强制同 PR 接线——防「机制建了没接线」病灶复发）；C# 产物以 2.2.0-beta 渠道
  发布，PyInstaller 包继续为 stable 直至 M4
- 完整决策/架构/纪律：[ADR-009](docs/adr/ADR-009-full-migration-to-csharp.md)

### Security（2026-09-04：全面审计批次 1——安全止血）
> 报告见 `docs/quality-reports/full-audit-2026-09-04.md`，逐项修复记录见
> `docs/quality-reports/fix-log-2026-09-04.md`（层次/原文件/界限/提交历史）。

- **Windows 现役栈原生加固层复活**（P0-1/P0-2/P0-3 实证修复）：
  `shell_adapter.resolve_core()` 修正 CoreWebView2 解析路径（pywebview 6.x
  `window.gui` 为平台模块、控件在 `window.native`——旧路径恒 None，
  全仓 10 处坏解析收敛单源）；全部原生挂接移到 `shell.start(func)` 回调
  （原时序在窗口创建前，整层加固从未生效）；`window.open/target=_blank`
  新窗口 URI 强制过 safe_url 门禁（类级替换 pywebview 零校验处理器，
  fail-closed）；下载发起时给用户明确提示 + 安全日志（pywebview 默认
  取消语义不变）；关键降级点由静默吞改为显式留痕。`main_webview.py`
  797→267 行，挂接实现拆至 `app/native_{hardening,interception,monitoring}.py`；
  新增 `selftest_native_core.py`（已入 ci.yml，现 8 个自检）
- **Windows js_api 桥面收口**（P0-4）：`current_url` 移出 `_JS_EXPOSED`
  （远程页面不可再读含 token 的完整 URL，零 JS 消费点）；`js_error` 加
  受信来源门禁（远程页上报丢弃，关闭「空 source 绕过同源校验」口）
- **C# 栈下载门禁**（P1）：`HostWebView` 订阅 `DownloadStarting` →
  `Handled=true` + `Broker.DenyDownload` 审计留痕——修复下载完全绕过
  broker 与「无 AuthorizedAction 不能下载」声明的矛盾（新增单测）
- **Android 修复五项**（P0-5/P0-6/P1-1/P2-1/P2-5）：`onDestroy` 仅
  `isFinishing` 时销毁（修复 density/字号/locale/折叠屏变更致全部标签
  白屏/崩溃）；渲染进程崩溃恢复改用宿主 Activity context（修复原生
  对话框必崩）；新增 SSL/HTTP/加载错误中文错误页（SSL 绝不 proceed，
  可重试/返回安全页）；`AegisBridge` 全部方法加壳页来源校验（远端页面
  不可再调 setEngine/navigate 等）；下载文件名净化 + 危险扩展判定修复
  （尾点/查询串直链漏判已消除）

### Added (Android)
- 地址栏贪吃蛇游戏：首页地址栏尾部「🎮」启动，地址栏区域平滑放大 5 倍作为游戏带
  （滑动手势控制方向、计分、游戏结束可退出/再来一局）；游戏期间保留迷你地址栏
  常规功能（输入网址回车自动退出游戏并导航）；游戏循环异常自动回退浏览状态。
  实现参考 MIT 项目 TurzimmGit/Snake-Game-APK 与 mukeshsolanki/snake-game-android
  （版权声明见 AddressBarSnake.kt 文件头）。回退键逐级返回（含游戏退出）。


### 架构收敛（2026-08-30：ADR-007——复审三项系统性修复）
- **单一正典栈**（D1）：ADR-007 收敛 Windows 双栈口径——C#/.NET 10 为目标发布栈，
  `legacy/windows-pywebview` 语义重定义为「现役功能栈（迁移中）」；
  README/CLAUDE.md 权威文档对齐（原文档互相矛盾）
- **Bridge 守卫单一事实源**（D2）：规范模板唯一存于
  `contracts/schemas/bridge_guard.template.js`；Rust 经 `include_str!` 编译期嵌入；
  Kotlin 内嵌副本归一化比对；`contracts/codegen/verify_bridge_guard.py` 入 CI 门禁——
  **修复实际已发生的漂移**（Kotlin 侧缺失 REQUIRE_HTTPS 段），fail-open 类 bug 结构性消除
- **门禁全量常跑**（D3）：android-quality/contracts/core-rust/agent-redteam/supply-chain
  五个 workflow 移除 paths 过滤（ktlint 门禁在 master 长期 FAIL 未被发现即实证）；
  5 个离线自检入 ci.yml（python-checks）；构建型 workflow 保留触发过滤


### 新增（2026-08-30：Windows 标签增强——Planned 首项落地）
- **拖拽排序**：`app/tab_ops.py` 新增 `move_tab(from,to)`（pinned 区边界钳制——固定标签永不混入普通区）；`app/tabstrip_js.py` 注入式标签条支持鼠标拖拽（≥4px 触发、插入线指示、本地即时重渲染，无需等待页面重载）
- **固定标签 UI**：标签右键菜单（固定/取消固定/关闭标签）——`pin_tab`/`unpin_tab` 首次获得 UI 入口
- **会话恢复**：`app/session_store.py` 会话持久化（session.json 原子写 + URL 白名单清洗：仅 http/https 与壳页 START_URL，≤20 标签）；标签增删/切换/固定/分组/导航自动落盘；`config.resume_session=True` 启动自动恢复 + 新标签页「恢复上次会话」按钮（`has_saved_session` 仅返回计数）
- **标签条恢复**：`bridge_hooks` 仅对受信本地页注入**脱敏**标签快照（title/pinned/group——无 URL，B0-W-01 口径不变；远程页维持空快照）
- 新增自检 `selftest_session_store.py`；扩展 selftest_api_bridge / selftest_shell_toolbar（move_tab 钳制/close_current_tab/会话 round-trip/标签条 JS 结构断言）
- **导入向导**（Chrome/Edge 书签与历史，Planned 第二项落地）：
  - `app/browser_import.py`：`find_import_sources()` 来源探测（仅探测文件存在，零读取）+ `find_bookmarks_files/find_history_files(source)` 按来源过滤（yield (来源key, 路径)——显式来源，不从路径猜）
  - 桥入口（B0-W-01 复审口径）：`scan_import_sources` / `import_bookmarks(source)` / `import_history(limit, source)`——白名单恢复 + 方法内受信来源校验（远程页不可达）
  - start.html 向导 UI：NTP 入口 → 扫描来源 → 选择来源/内容/历史上限（100–2000）→ 执行 → 分来源结果；全部 textContent 构建（R-06）；导入后自动刷新书签宫格
  - 修复存量：`import_history` 的 `imported` 恒为 0（`HistoryStore.add` 无返回值——历史为 visit 流水，计数即解析条数）


### 修复（2026-08-30）
- **Ctrl+W 关错标签**：注入侧 `TABS_DATA.current` 是注入时刻的冻结快照（多标签下恒 0）——新增 `close_current_tab`（后端实时 `_current`），TOOLBAR_JS 快捷键改调它
- **远程页面标签操作失效**（P1-1 复审口径调整）：来源校验一刀切导致用户在远程页上无法新建/切换/关闭标签（"+"按钮与 Ctrl+T 全部无效）——标签结构操作（new_tab/switch_tab/close_tab/close_current_tab/move_tab/pin/unpin/set_tab_group）放行来源校验：无数据读取、M-2 频率限制 + 20 上限 + URL 双层校验保留；敏感操作（navigate/搜索引擎/书签/restore_session）维持严格校验
- **新标签页书签宫格失效**（B0-W-01 复审）：`get_bookmarks` 被一刀切移出白名单导致 start.html 宫格静默失效——以「白名单恢复 + 方法内受信来源校验」回归（远程页调用返回空列表，维持零泄露边界）
- **Android 质量门禁修复**（README 遗留项「远端 ktlint 定位」闭环）：ktlint 1.8.0 KDoc 解析 bug（注释中反引号代码段以 `[` 开头且含 `$` 即整文件解析失败）——SecureWebViewFactory.kt 注释改写规避；.kts 存量风格问题 ktlint --format 修复；detekt 存量问题（BrowserViewModel TooManyFunctions/ReturnCount）按「基线对遗留友好」哲学基线化。CI ktlint+detekt 门禁首次全绿
- 自检与实现不一致修正（master 存量 FAIL）：selftest_shell_toolbar 中文转义断言（实现为 `ensure_ascii=False` 字面量注入，行为正确）；selftest_s1_integration 场景顺序（P1-1 语义下远程页写操作本应被拒）

### 新增（2026-08-30：Android 阅读模式与整页翻译入口——Planned 落地）
- **阅读模式**：`ReaderMode.kt` 页内正文提取（只读 evaluateJavascript——article/main/[role=main] → 最大文本块 → body 兜底；JSONTokener 两段解析防畸形返回；正文 200K 截断 + 最小 200 字判定），Compose AlertDialog 渲染（状态经 ViewModel 流转——INV-04）
- **整页翻译入口**：`TranslateEntry.kt` 构建 translatetheweb.com 整页翻译地址（国内可达）；导航仍经 SecureNavigator.navigateExternal（http/https 白名单 + Broker 授权）；用户显式点击触发（URL 外发翻译服务——隐私边界注释明示）
- 导航栏新增「阅读」「翻译」按钮；detekt baseline 同步 AddressBarAndNav 新签名

### 新增（Planned，待做）
- Windows 11 系统级 Mica/亚克力窗口背景（`app/backdrop.py` 已就绪，待真机验证）
- 导入向导：从 Chrome/Edge 导入书签与历史
- Android 阅读模式与整页翻译入口

### 已发布基线说明

以下内容为当前基线（2026-08-14）相对原始发布包（v0.1）的变更汇总，对应 git 提交 `dcedb8c` 与检查修复提交。

## [0.2.0] - 2026-08-14（当前基线）

### 架构重构（S1-S2）
- **Windows 端拆分**：`main_webview.py`（763 行）拆为单职责模块
  - `app/shell_toolbar.py`：注入式工具栏脚本（标签条/导航/地址栏/毛玻璃）
  - `app/nav_queue.py`：导航线程队列（窗口操作串行化，杜绝 js_api 死锁；含超时保护与看门狗恢复）
  - `app/api_bridge.py`：js_api 桥（标签/导航/书签/历史/壁纸/搜索）
  - `main_webview.py`：薄入口（参数解析/建窗/绑定/看门狗）
- **Qt 旧栈归档**：`main.py`、`ui/`、`app/browser.py`、`app/qt_bridge.py` 等 30 个 QtWebEngine 模块移入 `legacy/`，消除双入口混乱
- **修复**：`validate_release.py` 硬编码 `/home/ubuntu/...` 路径改为相对路径（H1）

### 新功能（S3-S4）
- **Android 多标签**（全新）
  - `Tab.kt`：标签数据模型
  - `TabManager.kt`：标签增删/切换/挂起恢复（默认 8 活跃，可注入测试）
  - `TabBar.kt`：Compose 标签栏（横滚标签 + 新建/关闭）
  - `SecureWebViewFactory.kt`：统一安全 WebView 工厂（修复 M1 双实例问题）
  - `MainActivity.kt`：接入 TabManager + TabBar，onDestroy 统一释放 WebView

### 界面（S5）
- Android 工具栏亚克力玻璃化（半透明深蓝紫 `0xCC101827`，与状态栏融合，全版本兼容）
- Windows 11 Mica/亚克力系统背景（`app/backdrop.py`，尽力而为、失败静默降级）

### 修复
- `nav_queue` lambda 捕获循环变量（B023）改为 `functools.partial` + 显式类型
- `threat_feed` 两处 `urlopen`（B310）确认 HTTPS 强制后加 nosec 说明
- `history_store` 显式时区（DTZ005）；`config` 嵌套 if 合并（SIM102）
- 修复 Kotlin 赋值表达式语法错误与 threading 导入位置问题

### 代码质量
- 引入 2026 工具链：ruff 0.16.3 / bandit 1.9.4 / mypy 2.3.0（Python）；ktlint 1.8.0 / detekt（Kotlin，待 Gradle 环境）
- 全量检查清零：ruff 活跃代码 0 错误、mypy 14 文件通过、bandit Medium+High=0
- 新增自检脚本：`selftest_shell_toolbar.py` / `selftest_api_bridge.py` / `selftest_s1_integration.py`

## [0.1.0] - 2026-08-14（原始发布包）

- Windows：Python + pywebview + WebView2，注入式工具栏，多标签基础实现
- Android：Kotlin + Compose + System WebView，`BrowserEngine` 安全边界（http/https 白名单、禁 file/混合内容/调试）
- 双端版本同步脚本、MSIX/App Installer 打包配置
