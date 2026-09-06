# 变更日志（Changelog）

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Fixed (Windows C# 正典栈——历史页内滚动与页码分页，2026-09-06)
- **页内无法向下滚动**：原 DayGroup 把同一天全部记录包在一个 ListBox 项中，单日大量记录超出视口但组内无滚动。改为扁平虚拟化列表：日期变化处插入独立日期头行，每条记录单独成为虚拟化项，当前页全部内容可正常滚动。
- **保留页码分页**：底部上一页/页码/下一页与每页 50/100/200/500 条设置保持不变；页跳转只加载当前页。
- **回归**：新增页码 Count/OFFSET 边界测试；Core 145 + Broker 27 全绿。


### Changed (Windows C# 正典栈——历史记录页码式分页，2026-09-06)
- **页码分页（非无限滚动）**：底部「‹ 上一页 | 1 2 3 … › 下一页」页码条，可跳任意页；数据层 `Count` + `SearchRangePage/RecentPage`（LIMIT/OFFSET，全部参数绑定）。
- **每页条数设置**：筛选行「每页 50/100/200/500 条」下拉，切换即重载第 1 页。
- 顶部统计「共 N 条 · 第 X / N 页」；搜索/日期/删除/清空回到第 1 页。
- 回归：2 个页码分页单测（跨页覆盖/筛选+offset）。145 测试全绿。


### Changed (Windows C# 正典栈——历史记录真分页，2026-09-06)
- **游标分页替代一次性全载**：`HistoryStore` 新增 `SearchRangePaged/RecentPaged`（键集分页，`(visited_at,id)` 倒序，翻页期间新增不重不漏；全部参数绑定）；UI 首屏只拉 100 条，滚动触底/点「加载更多」按游标追加下一页（不重建已有项），长历史内存与绘制负载恒定。
- 新页条目合并进已有日期分组；搜索/日期/删除/清空重置游标重新拉首页；列表状态改「已加载 N 条」。
- 回归：5 个游标分页单测（不重不漏/边界/游标推进/筛选+游标/文本组合）。143 测试全绿。


### Added (Windows C# 正典栈——对标 Edge P0+P1 大版本，2026-09-06)
P0 基础体验：
- 页内查找 Ctrl+F（WebView2 window.find，计数+上一个/下一个/Esc 关闭）
- 标签交互：右键菜单（关闭其他/右侧/固定/复制/重新打开已关闭）、中键关闭、悬停显示 ✕、固定标签前置且隐藏 ✕
- 地址栏历史/书签自动补全（防抖下拉，↑↓/回车/Esc）
- 缩放：WebView2 原生 Ctrl+滚轮 + Ctrl+0/± 快捷键，每站点记忆持久化
- 窗口状态记忆（大小/位置/最大化，越界安全回退）
P1 差异化：
- 后台标签睡眠（默认 30 分钟释放 WebView 内存；固定标签豁免；激活自动复活）
- InPrivate 无痕窗口（独立临时环境隔离 cookie/缓存，多标签，关闭即清理，不落历史/会话）
- 防跟踪分级（基础/均衡/严格：威胁黑名单 + 已知跟踪器后缀拦截 + 严格拦截第三方脚本/图片）
- 真实 favicon（直连站点 favicon.ico + 磁盘/内存缓存，标签回填，隐私不求第三方图源）
- HTTPS-only 自动升级 https；安全 DNS（DoH，阿里公共解析，环境参数）
基建：Tab 模型扩展（固定/睡眠/图标/最近激活）、TabManager 撤销栈/批量关闭、TabSessionStore pinned 迁移、共享 WebView2 环境注入。回归 26 个新单测。


### Changed (Windows C# 正典栈——贪吃蛇暖阳像素重设计，2026-09-06)
- **金色时刻·暖阳像素艺术方向**：真·像素渲染管线（120×120 离线画布整数绘制 + 关闭平滑放大 + image-rendering:pixelated）；暖阳日落天空（杏→琥珀→玫瑰）、像素太阳与斜射暖光带、漂移像素云、萤火虫漂浮。
- **蜜金蛇身**：暖描边 + 蜜金渐变插值移动，暖色眼睛；苹果 5×5 手绘像素精灵（高光/绿叶）；**奖励星**（每 5 果出现，+50 限时闪烁）。
- **温暖正面氛围**：像素数字浮动得分（+10/+50）、吃食暖金粒子、死亡像素溃散+暖红闪；状态卡片正面文案（太棒了！新纪录 / 再来一次你可以的）。
- **8-bit 柔和音效**：C 大调五声音阶三角波（吃食循音/奖励琶音/死亡下滑/新纪录号角），头部 🔊 静音开关（偏好持久化）。
- 稳定性与内存：42 日格一次构造复用零分配、粒子池化、页面隐藏自动暂停、rAF 仅游戏打开时运行。


### Fixed (Windows C# 正典栈——搜索引擎切换真因 + 主流引擎全覆盖 + 切换 UI 重做，2026-09-06)
- **切换失效真因**：首页搜索走的 `NtpBridge.navigate` 归一化漏传当前引擎，永远拼默认百度（地址栏路径正常）。修复：桥内按 `_services.SearchEngine()` 归一。
- **主流引擎全覆盖（10 个）**：百度/必应/谷歌/搜狗/360搜索/DuckDuckGo/Brave/Startpage/Ecosia/Yandex；展示名单源 `EngineNames`（中文优先）+ `EngineOrder` 固定顺序；工具栏与设置下拉改显示中文名。
- **首页切换 UI 重做**：引擎胶囊改为点击展开的玻璃卡片下拉菜单（逐项选择+选中勾标+外点关闭），替换「点击循环」；跨端单源（Android 同步受益）。
- 回归测试：首页搜索按当前引擎拼 URL + 引擎表覆盖/名单（3 个新用例，133 全绿）。


### Changed (Windows C# 正典栈——历史窗口 Apple 风格重设计 + 性能优化，2026-09-06)
- **性能**：外层改 ListBox 虚拟化（Recycling）替代非虚拟化 ItemsControl；移除每行
  DropShadowEffect（GPU 重负载）；数据库加索引 `idx_visits_date_time`；默认加载 200 条
  +「加载更多」分页——千条数据首屏毫秒级、滚动流畅。
- **Apple 风格 UI**：iOS 系统色板（浅 #F2F2F7/白卡/#007AFF，深 #1C1C1E/#2C2C2E/#0A84FF）、
  大标题、圆角 14 分组卡片 + 发丝分隔线、iOS 分段控件日期快捷（全部/今天/昨天/近7天/本月）、
  可展开日历（自定义某天）+ 起止范围查询、日期分组头友好化（今天/昨天 · 9月6日）。
- 筛选路径全部 try/catch 兜底（日期点击不再可能崩溃）。



### Fixed (Windows C# 正典栈——历史窗口闪退真因，2026-09-06)
- **非法颜色字面量 `#FFB3FFFFFF`（10 位十六进制）**：合法仅 3/4/6/8 位。它先使
  `ColorConverter.ConvertFromString` 抛「令牌无效」（已改手动解析绕过），后又使 XAML
  资源字典在 ApplyTheme 触发延迟资源创建时被 `ParseColor` 抛出 → XamlParseException
  → 历史窗口闪退。已修正为 `#B3FFFFFF`（HistoryWindow/SettingsWindow 两处）。
- **全仓 XAML 颜色字面量扫描**：脚本化校验所有 `#hex` 长度 ∈ {3,4,6,8}——复扫全部合法。
- **回归测试升级**：窗口冒烟测试现调用 `ApplyTheme("dark")+("light")`，强制触发
  XAML 延迟资源解析——非法字面量存在时测试即失败，同类问题无法再溜进构建。



### Fixed (Windows C# 正典栈——历史窗口构造期 NRE，2026-09-06)
- **历史窗口打开即异常**：XAML `ChipAll IsChecked=True` 在 InitializeComponent 阶段就触发
  `Checked`，而 `ChipFilter_Changed` 引用的 `CustomDate/RangePanel` 尚未初始化 →
  NullReferenceException。为所有筛选/删除/清除事件加 `_initialized` 守卫（初始化完成前
  忽略），与设置窗口 `_suppressEvents` 模式对齐。
- **回归防护**：新增 WPF 窗口构造冒烟测试（STA 线程实例化 History/Downloads 窗口，
  任何构造异常即失败），杜绝「事件早于控件初始化」一类构造崩溃复发；兜底日志带完整堆栈。



### Added (Windows C# 正典栈——历史窗口精细化 + 日历查询，2026-09-06)
- **可展开日历查询**：WPF DatePicker 展开日历选某一天；支持起止日期「范围」查询
  （两个日历）、快捷日期芯片（全部/今天/昨天/近7天/本月）；数据层新增
  `SearchRange`（参数绑定区间查询）。
- **精细化 UI**：玻璃卡片 + 圆角 + 阴影；日期分组头含「月日 + 星期 + 条数徽标」；
  条目含时刻胶囊/标题/域名/悬停删除；搜索带图标与占位；跟随深浅主题。



### Fixed (Windows C# 正典栈——历史窗口闪退根因，2026-09-06)
- **历史窗口闪退/无法显示**：`HistoryWindow.ApplyTheme` 里 `ColorConverter.ConvertFromString`
  对同一合法色值抛 `FormatException: 令牌无效`（栈定位），点历即崩。改为手动解析
  ARGB 十六进制（`Convert.ToByte(hex,16)`），确定性不再抛；MainWindow.SetBrush 同步。
- 历史窗口改为「预分组列表 + DataTemplateSelector」渲染（日期头+条目），不再依赖
  CollectionViewSource 分组，规避渲染期格式异常；日期分组/搜索/日期筛选/删除/清空保留。
- 兜底日志记录完整异常堆栈（`[fatal]` 含栈）便于后续精确定位。



### Added (Windows C# 正典栈——历史记录全面升级，2026-09-06)
- **按日期保存与查询**：HistoryStore 新增 visited_date 列（本地日期），支持按日期
  查询（ByDate）、文本+日期组合查询、日期列表、单条删除；旧库自动迁移补列并回填。
  全部外部输入参数绑定（安全约束）。
- **精美历史窗口**：按日期分组（蓝色日期头+条数）、每条显示本地时刻(HH:mm)+标题+
  域名，支持文本搜索 / 日期下拉筛选 / 单条删除(✕) / 清空二次确认；跟随深浅主题。
- 6 个单测锁定（按日查询/日期列表/删除/迁移回填）。



### Fixed (Windows C# 正典栈——标签关闭加固，2026-09-06)
- **新建标签删不掉（部分）**：新建 NTP 标签的导航经 Dispatcher.BeginInvoke 延迟；
  若立即点击 ✕ 关闭会先销毁 WebView，随后延迟回调在已释放控件上设 Source→抛异常。
  已加「标签仍在才执行」防护 + 关闭过程 try/catch 容错 + tabId 双来源兜底（Tag/DataContext），
  并新增关闭日志便于定位。拖拽阈值与关闭按钮排除保留。



### Fixed (Windows C# 正典栈——GeoGebra/标签关闭/主题，2026-09-06)
- **几何画板不可用**：GeoGebra bundle 未进入 C# 发布输出，`ResolveGeoRoot` 永远
  返回空。csproj 现在条件包含 legacy GeoGebra 资源（117MB），发布后映射
  `geo.aegis.local`，按钮可正常打开离线画板。
- **标签只能新增不能删除**：标签拖拽监听在任意微小鼠标移动时就启动
  `DoDragDrop`，会吞掉 ✕ 的 Click。加入系统拖拽阈值并排除关闭按钮区域，
  正常点击可靠关闭，拖动排序仍保留。
- **主题不可用**：主窗口原为硬编码深色且设置无主题入口。新增深色/浅色
  主题下拉，9 个 chrome 色刷改 DynamicResource，切换即时应用并持久化。



### Added (Windows C# 正典栈——对标 Edge 界面，2026-09-05)
- **标签栏对齐 Edge**：顶部圆角直角标签、激活标签与工具栏连成一体、前置站点圆点图标、标题悬停/选中变白、标签间细区分；
- **工具栏对齐 Edge**：右侧顺序 ☆ 收藏/⤓ 下载/历 历史/⚙ 设置/◐ 个人资料占位（点击聚焦地址栏）；
- **新标签页对齐 Edge**：书签改为「常用站点」磁贴宫格（圆形站点图标+名称，最多 8 个 + 「＋ 添加常用站点」磁贴点击聚焦搜索框）、壁纸背景居中搜索框。

### Fixed (Windows C# 正典栈——多标签可见性与切换，2026-09-05)
- 切换时同时设置激活标签 Z 序、Visibility、命中测试与布局刷新，避免 HWND WebView2 层叠导致最后标签盖住其它标签。
- 增加标签创建日志，便于确认多标签创建与初始化。

### Fixed (Windows C# 正典栈——NTP 首页渲染（实则根因）+ 首页清理，2026-09-05)
- **[渲染根因] NTP 导航 ConnectionAborted**：同一调用栈里
  `SetVirtualHostNameToFolderMapping` 后立即导航虚拟主机，映射尚未传播到渲染
  进程 → 连接中止；且首标签 Source 设 null 会让 WebView2 控件永不 eager 初始化
  （首页空白）。修复：源虚拟主机地址时构造期初始化到 about:blank（保证控件
  初始化），映射后就绪，再**推迟到下一 Dispatcher 周期**导航 NTP——与「点主页
  成功」路径一致，实机确认首页完整渲染
- **首页清理**：书签宫格改为紧凑横条（超出水平滚动）并最多展示 8 个，不再让
  大量书签/历史标签占满主屏；贪吃蛇/画板/导入改轻量小链（去大按钮）；移除
  首页浮动返回按钮（工具栏统一提供）

### Fixed (Windows C# 正典栈——浏览历史记录缺口，2026-09-05)
- **历史记录从未落库**（M2 parity 勾验后漏接线——浏览时 `_history.Add` 从未被
  调用，仅导入写入）：现于导航完成时记录成功访问（后台标签同样记录），受
  `HistoryEnabled` 开关门控（该设置终于真正生效）
- **内部页不入历史**：新标签页/离线画板虚拟主机、about:blank、非 http/https
  一律过滤——杜绝「历史被首页占满」；`HistoryRecorder.IsRecordableUrl` 纯静态
  判定，10 个单测

### Fixed (Windows C# 正典栈——多标签切换，2026-09-05)
- **标签点击切换不可靠**：自定义 ListBoxItem 模板内含关闭按钮/子 DockPanel 且
  项不可聚焦，部分环境仅靠 SelectionChanged 隐式命中会失效（表现为「只有一个
  标签切不过去」）。新增显式 `TabStrip_PreviewMouseLeftButtonDown`——命中标签项
  即调用 `SwitchTo`（命中 ✕ 交按钮自身处理，不动手切换）；SelectionChanged
  保留为兜底。跨标签每标签独立 WebView 实例，切换即可见性切换天然可用。

### Fixed (Windows C# 正典栈——NTP 首页空白页，2026-09-05)
- **虚拟主机映射与首次导航时序**：TabRuntime 构造时预置 `Source=https://ntp.aegis.local/start.html`，
  但该 host 的 SetVirtualHostNameToFolderMapping 要到 CoreWebView2 初始化完成后才注册——
  映射生效前发起的首次导航失败 → 首页空白。修复：虚拟主机地址（NTP/画板）不在构造时
  预置 Source，改由 Chrome 在 CoreWebView2InitializationCompleted 里映射虚拟主机后再导航；
  新增 NtpAssets.IsVirtualHostUrl 判定。实机验证：主页渲染出完整新标签页
  （标题/搜索框/书签宫格空态/引擎胶囊均正常，WebMessage 桥可用）

### Fixed (Windows C# 正典栈——M4 全量审计 2026-09-05)
- **[安全·发布阻断] WebMessage 受信通道绕过**：远程页内嵌 ntp.aegis.local 帧即可把
  core 级 IsWebMessageEnabled 打开并驱动本地桥——封死：① 移除
  `FrameNavigationStarting→SetPerOrigin`（内嵌帧不得启用全局 WebMessage）；
  ② 宿主桥入口增加顶层文档门禁（core.Source 必须为 NTP host——帧内嵌来源拒绝）
- **[运行时·发布阻断] restoreSession 撞已释放 CoreWebView2**：会话恢复同步拆除
  发送标签后向已释放 core 回写响应 → 未处理异常；响应注入容错（try/catch 静默丢弃）
- **[功能·M3 死特性] 危险扩展下载确认从未接线**：DownloadConfirmationRequested
  全仓零订阅 → 危险文件恒被静默拒绝。现于 MainWindow 接线为原生确认对话框
  （窗口已关闭仍 fail-closed 拒绝）
- **星标反馈文案错误**：取消收藏误报「已收藏」——改为按实际操作提示
- **反馈条定时器事件累积泄漏**：Tick 处理器改为首次创建时订阅一次

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
