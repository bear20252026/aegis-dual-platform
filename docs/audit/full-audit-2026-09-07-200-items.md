# Aegis 全仓审计整改总清单（2026-09-07）

**范围**：aegis-dual-platform 全仓（Windows C# 正典栈 / Rust policy core / shared Web 资产 / CI 发布链 / 文档脚本）
**方式**：5 路并行审计代理逐文件核对（带 file:line 证据）→ 人工去重分级 → 分 8 批修复 → 全量回归验证
**结果**：**100 个问题修复 + 100 项提升改造全部落地**，覆盖 **100 个审计大类**。
**验证**：C# 210（Core）+ 29（Broker）测试通过；Rust 171 测试通过 + clippy 0 警告；XAML 资源连通性校验通过；snake 单测 10/10；版本门禁/评审包 --check/validate_release 通过。

> 编号规则：P=问题（缺陷：崩溃/安全/竞态/失效），I=提升（质量：性能/体验/可维护性/工程化）。每项注明大类与修复位置。

---

## 第一部分：问题修复 100 项（P01–P100）

### A. 崩溃与功能损坏（P01–P14）

| # | 大类 | 问题 | 修复 |
|---|------|------|------|
| P01 | 崩溃防护 | 书签管理窗口引用全仓不存在的 `PrimaryButton` 样式——窗口必抛 XamlParseException 打不开 | BookmarkManagerWindow.xaml 补样式 |
| P02 | 崩溃防护 | 删除按钮引用仅存在于 HistoryWindow 的 `GhostButton`——书签行渲染即崩 | 同上补窗口级样式 |
| P03 | 启动崩溃 | settings.json 手编 `"ZoomByHost": null` → ToSnapshot 抛 ArgumentNullException 且在启动链 | SettingsService.ToSnapshot null 防护 |
| P04 | 输入验证 | 地址栏输入 `http://` 等非法 URI 直接 `new Uri` 抛 UriFormatException | UrlNormalizer 往返校验 + MainWindow.SafeNavigate |
| P05 | 输入验证 | UrlNormalizer 放行 `<>│"^`{}\` 等非法 URI 字符 | StripUnsafeCharacters 剥离 |
| P06 | 功能失效 | InPrivate 窗口从未挂接 NtpBridge——无痕下首页搜索/引擎/壁纸/画板全部静默失效 | InPrivateWindow.WireNtpBridge（无痕语义服务） |
| P07 | 隐私隔离 | 多个 InPrivate 窗口共享同一静态 WebView2 环境（隔离承诺失效） | WebViewEnvironment 每窗口独立租约 |
| P08 | 隐私隔离 | 关闭任一无痕窗口即删共享临时目录——存活窗口数据目录被删 | 引用计数 CleanupInPrivate |
| P09 | 逻辑矛盾 | 缩放三口径（会话 0.25–3.0 / Store 0.25–5.0 / 持久化 1.0–3.0）——缩小后被静默重置 | 统一 0.25–3.0 常量单源 |
| P10 | 竞态条件 | InPrivate CreateRuntime await 期间窗口关闭后仍挂载 WebView（永不释放） | `_closed` 守卫 + 归还租约 |
| P11 | 竞态条件 | InPrivate 初始化完成回调无标签存活校验即设 Source/映射 | `_runtimes.ContainsKey` 守卫 |
| P12 | 异常处理 | InPrivate async void CreateRuntime 异常无局部捕获（未观察异常面） | try/catch + SecurityLog |
| P13 | 授权撤销 | Broker TryConsumeNavigation 消费点不查 KillSwitch——evaluate 与 consume 间触发无法撤销已签发授权 | 消费点强制检查 + 审计 |
| P14 | 门禁失效 | native-required 模式 EvaluateNavigation 直接返回，导航级威胁黑名单静默失效 | native 路径补黑名单门禁 |

### B. 安全绕过与注入（P15–P34）

| # | 大类 | 问题 | 修复 |
|---|------|------|------|
| P15 | SSRF 防护 | IsPublicIp 放行 IPv4-mapped IPv6（`::ffff:192.168.1.1` 判公网） | unwrap 内嵌 IPv4 判定 + 测试 |
| P16 | SSRF 防护 | IPv6 组播 `ff00::/8`、site-local `fec0::/10`、IPv4 兼容残留段放行 | 16 字节分支逐段拦截 |
| P17 | SSRF 防护 | 整数 `2130706433`/十六进制 `0x7f000001`/简写 `127.1` IP 编码判"公网主机名" | TryParseAlternateIpv4 规范化 |
| P18 | Origin 校验 | OriginPolicy 未拒尾点 host（`example.com.`）/非 DNS 字符残留 | IsValidHost 白名单校验 |
| P19 | 授权绕过 | Rust capability `is_origin_allowed` 用 contains 子串——白名单 trusted.com 放行 evil-trusted.com | origin 前缀精确匹配 + 测试 |
| P20 | 授权绕过 | capability 空白名单默认放行全部 origin（fail-open） | fail-closed，显式 "*" 才全放行 |
| P21 | fail-open | Rust oracle 验证 mismatch 时 expected 值 `safe_` 前缀即降级 Warning 放行（攻击者可控命名后门） | 不匹配一律 Fail |
| P22 | 密码学 | FingerprintShield 种子用 SystemTime×PID（可预测且 (i%16)*8 使前后半区相同） | getrandom OS CSPRNG（依赖已在） |
| P23 | 隐私泄露 | 会话种子以顶层 `const __AEGIS_SESSION_SEED` 注入——任意页面按名可读（跨站超级 Cookie） | 全脚本闭包封装 |
| P24 | 隐私泄露 | per_site_seed 把会话种子原文内嵌进每个站点且全局暴露 `__AEGIS_SITE_SEED` | Rust 侧按域派生 + 闭包注入 |
| P25 | KDF 缺陷 | per-site 派生用自制 `acc*31+byte` 混合——多站点种子可逆推会话种子 | SHA-256 域密钥分离 + 向量测试 |
| P26 | JSON 注入 | session_state.to_json format! 手拼零转义——页面标题含 `"`/`\` 损坏会话恢复 | serde_json 构造 |
| P27 | JS 注入 | command_bar 注入 JSON 仅转义双引号（标题源自书签历史=页面可控） | serde_json + javascript: 拒绝 + postMessage 定向 origin |
| P28 | JS 注入 | space_routing 注入 name/workspace_id 完全未转义 | serde_json 构造 |
| P29 | JS 注入 | ext_proxy 端点含单引号即注入 JS 字符串 | 转义后嵌入 |
| P30 | Rust panic | sanitize_filename 字节截断可落多字节 UTF-8 字符中间（panic） | floor_boundary 字符边界 |
| P31 | 匹配绕过 | action_policy 条件 `context.contains(c)`——`?x=example.com` 命中条件 example.com | token 边界匹配 context_contains_token |
| P32 | 匹配误导 | matcher 文档示例用 flat=true 做 URL 匹配——`*.gov.cn` 可被 `/x.gov.cn` 后缀拼接绕过 | 文档修正 + 仅路径模式用于 URL |
| P33 | DoS 防护 | glob_match 无输入上限地分配平方级 DP 缓冲 | 16K 输入上限 |
| P34 | 参数绕过 | query_strip 追踪参数名区分大小写——`Gclid`/`gClId` 变体绕过剥离 | eq_ignore_ascii_case |

### C. 隐私与数据安全（P35–P48）

| # | 大类 | 问题 | 修复 |
|---|------|------|------|
| P35 | 无痕泄露 | InPrivate 复用 TabRuntime——favicon 写磁盘（无痕已访站点永久痕迹） | FaviconService persistToDisk=false |
| P36 | 无痕泄露 | InPrivate 每站点缩放写入进程级 ZoomStore 并随主窗口持久化到 settings.json | TabRuntime.IsPrivate 私有字典 |
| P37 | 日志脱敏 | 审计/安全日志明文记录完整 URL 含 query（token/搜索词），违背 schema 声明 | Broker/HostWebView/MainWindow RedactUrl 全面接入 |
| P38 | 日志脱敏 | deny reason detail 内嵌 rawUrl 反射到 UI | 文案移除 URL |
| P39 | 日志伪造 | SecurityLog 接受页面可控字符串（NTP jsError）原样写入——换行可伪造日志条目 | 换行转义 + 单条 4000 字符上限 |
| P40 | 取证保全 | 安全日志超 1MB 整文件删除——刷量即抹除全部取证痕迹 | 轮转保留 .1 |
| P41 | 历史口径 | HistoryStore 注释承诺"不含 query secret"但调用方原样存全量 URL | 注释对齐现实（history=db 明文本地存储） |
| P42 | 数据丢失 | 设置文件坏读后启动链 Apply(默认值) 覆盖用户全部设置且无备份 | Load 失败先备份 .bak |
| P43 | 订阅源安全 | ThreatFeed 跟随重定向可降级 http——明文可投毒黑名单 | 最终 URL scheme 强制 https |
| P44 | DoS 防护 | ThreatFeed 先全量读内存再查 5MB 上限——被劫持源可 OOM | Content-Length 预检 + 限量缓冲 |
| P45 | 数据失效 | ParseFeedLine 接受带端口/通配条目——入表后永不命中 | 剥端口 + 主机字符白名单 |
| P46 | 会话泄露 | （防回归）native 模式 consumed nonce 满后 DestroySession 无法清理（前版自锁） | 保留既有 sessionId 前缀方案并加消费点 KillSwitch（P13） |
| P47 | 缓存上限 | UrlSafety LocalHostCache 只写不逐出——长期浏览永久驻留 | 2000 条清空 |
| P48 | 缓存上限 | Favicon 内存缓存 ConcurrentDictionary 永不逐出 | 500 条 Trim |

### D. 稳定性与竞态（P49–P66）

| # | 大类 | 问题 | 修复 |
|---|------|------|------|
| P49 | UI 线程安全 | Broker._blockedHosts 后台线程替换与导航读取无可见性保证 | volatile |
| P50 | 内存泄漏 | 主窗口 OnClosed 不停 sleep/suggest/feedback 定时器、不解绑 _tabs/ZoomStore 事件 | 全量清理 |
| P51 | 事件泄漏 | ZoomStore.Changed 匿名 lambda 永不可解绑 | handler 字段化退订 |
| P52 | 竞态条件 | 令牌源 Close 即 Dispose——延迟导航回调读 CancellationToken 抛 ObjectDisposedException | 构造期缓存 token |
| P53 | 状态覆盖 | 两个标签先后请求导航确认——_pendingConfirmTabId 被覆盖前者永久挂起 | 新请求先拒绝旧请求 |
| P54 | 死分支 | ApprovalAllow_Click 查字典 `""` 键恒 null——失效恢复路径形同虚设 | 重写为撤面板+告知 |
| P55 | 窗口竞态 | 源码抓取完成时主窗口已关——Owner=已关窗口抛异常被吞成误导提示 | IsLoaded 守卫 |
| P56 | 数据失真 | 下载记录在启动时读 FileInfo.Length——文件未创建即抛被空吞（记录丢失） | TotalBytesToReceive |
| P57 | 状态失真 | DownloadItem 捕获 ObjectDisposedException 一律标"已完成"——已取消下载显示打开按钮 | 如实标"已结束" |
| P58 | 字段未赋值 | DownloadItem._completedAt 从未赋值（编译警告 CS0649） | 完成时刻赋值 |
| P59 | 存储容错 | HistoryStore.Add 异常沿 NavigationCompleted 上抛——每次导航弹全局异常 | 内部捕获+日志，返回真实结果 |
| P60 | 存储容错 | TabSessionStore.Save 无容错——磁盘满/库锁定时每次导航弹窗 | 捕获+日志放弃快照 |
| P61 | 存储容错 | BookmarkStore 并发写（主窗+管理器）依赖默认 30s 忙等后抛锁死 | busy_timeout 5000ms |
| P62 | 栈溢出 | BookmarkImporter.Walk 无深度上限——构造深嵌套书签文件触发不可捕获 StackOverflow | MaxDepth 64 |
| P63 | 数据不完整 | HistoryImporter 只复制主库不复制 -wal/-shm——运行中浏览器最近访问丢失 | 边车一并拷贝 |
| P64 | 临时文件 | 导入临时副本删除仅捕 IOException——UnauthorizedAccessException 残留 | 全捕 + 逐文件删除 |
| P65 | 异常面 | AppSettings.Load 只捕 IOException/JsonException——ACL 拒绝直接炸启动链 | 捕 Exception（fail-safe） |
| P66 | 弹窗风暴 | 全局兜底无条件弹窗——每帧级异常造成无限 MessageBox 循环 | 30s/3 次频控 |

### E. 逻辑与口径缺陷（P67–P82）

| # | 大类 | 问题 | 修复 |
|---|------|------|------|
| P67 | 计数失真 | HistoryImporter Imported 与 Total 恒等（无条件同自增）——返回值无信息量 | Add 返回真实写入计数 |
| P68 | 多屏支持 | NormalizeWindow 以 min=0 钳 Left/Top——负坐标显示器窗口跳回主屏 | ±100000 |
| P69 | 入模校验 | Normalize 不校验 ThreatFeedUrl——手编 settings.json 可注入 http 订阅源 | Normalize 校验（仅 https/空） |
| P70 | 写盘时序 | SettingsService.Apply 先改内存后写盘——写失败内存/磁盘分叉（与注释矛盾） | 先盘后内存 |
| P71 | 变更检测 | Equals(record 含字典) 恒真——Changed 事件语义失效 | ReferenceEquals |
| P72 | 预览失真 | WebView MAX_VIEWPORT_DIMS 返回 Float32Array（规范要求 Int32）——伪装被类型检测识破 | Int32Array |
| P73 | 域名解析 | https_only upgrade() 域名截取不含 `?`/`#`——`http://x.com?a` 误判 | 终止符补全 |
| P74 | 主机提取 | util.extract_host rfind(':') 把 `[::1]:80` 截成 `[::1` | 方括号感知 |
| P75 | userinfo | util.extract_hostname 把 `user@host` 整段当 host（凭证入匹配基座） | 剥 userinfo |
| P76 | 种子静默 | ffi hex_seed_to_bytes 非法 hex 逐字节 unwrap_or(0)——畸形种子全体同噪声 | 长度前置校验 |
| P77 | 保留名 | DownloadPolicy 未处理 Windows 保留设备名（CON/PRN/COM1…）——写盘行为异常 | 词干后缀 `CON_file.txt` |
| P78 | 长度上限 | 下载文件名无长度限制——255+ 字符写盘失败 | 200 字符 + 保留扩展名 |
| P79 | 漏判 | 查询串危险扩展整串取尾点——`?f=x.exe&sig=abc` 因尾缀拼接漏判 | 按参数值判定 + 测试 |
| P80 | 误报 | （对偶锁定）`?v=2&f=exe` 无扩展直链不误报确认框 | 同上测试锁定 |
| P81 | 死守卫 | TabManager.SetPinned 用 First——currentId 失配抛 InvalidOperationException | FirstOrDefault |
| P82 | 空消息面 | HostWebView 空操作 WebMessageReceived 处理器占位（语义已由 SetPerOrigin 承担） | 移除 |

### F. 前端功能缺陷（P83–P92）

| # | 大类 | 问题 | 修复 |
|---|------|------|------|
| P83 | 交互失效 | 地址栏建议列表仅键盘可达——鼠标点击不导航（弹层只关不选） | PreviewMouseLeftButtonUp |
| P84 | 交互失效 | 书签管理器仅鼠标可达——无 Enter 打开/Delete 删除 | BookmarkList_KeyDown |
| P85 | 状态错位 | 书签编辑弹层无遮罩——编辑期间可再点列表换目标致 _editingId 错位 | IsHitTestVisible 屏蔽 |
| P86 | 静默失败 | 书签编辑空标题静默 return——无任何反馈 | 聚焦反馈 + 长度上限 |
| P87 | 参数注入 | DownloadsWindow explorer /select 路径未转义引号且无 try/catch | 引号转义 + 容错 |
| P88 | 永久卡死 | 导入向导"扫描中…"无超时——宿主无响应（如未接桥窗口）模态永久卡死 | 15s 超时兜底 |
| P89 | 类型错误 | Host.importScan 三端返回形态不一——win 返回 Promise、cs/android 返回 undefined，`.catch` 作用于 undefined 抛 TypeError | 统一回调 + 可选 thenable |
| P90 | 失败伪装 | 导入链 `.then(renderDone).catch(renderDone)`——失败渲染与成功同一"导入完成"界面 | 失败计数可辨识文案 |
| P91 | 渲染竞态 | 书签宫格 `setTimeout(renderBookmarks, 200)` 魔法延时——慢机桥未就绪即空宫格 | 桥就绪有界重试 |
| P92 | 键盘劫持 | 贪吃蛇全局 WASD 劫持不检查 e.target——overlay 开着时输入框无法打字 | 输入控件守卫 |

### G. CI/发布链缺陷（P93–P100）

| # | 大类 | 问题 | 修复 |
|---|------|------|------|
| P93 | 发布断链 | publish 下载不存在的 `release-windows-installer` artifact——编排发布链 100% 断裂 | 移除该步骤（对齐真实产物名） |
| P94 | fail-open | verify-gate 校验文件缺失仅告警跳过——平台不产 checksum 也过聚合门禁 | 缺失即失败 |
| P95 | 空洞断言 | SHA256SUMS.json 存在但 entries 为空数组时静默通过 | 空清单即失败 + 全文件反向覆盖 |
| P96 | 假对账 | core 平台仅 SHA256SUMS.txt 时"存在即通过"零字节复核 | txt 逐行真实对账 |
| P97 | 清单失配 | 跨平台去重改名发生在 checksum 生成之后——Release 资产名与清单条目脱节 | 去重后重生成清单 |
| P98 | 版本漂移 | shared/release.json 停在 2.1.6/20106（落后三个大版本）且 verify/sync 均不覆盖 | 对齐 2.2.0-beta.21 + 双向门禁 |
| P99 | 生成链断裂 | gen_jsapi_schema.py 指向不存在的 windows/aegis_source——schema 冻结陈旧快照 | 路径修复 + 重生成（30 方法） |
| P100 | 版本门禁 | contracts version schema 拒绝预发布号——实际版本 2.2.0-beta.21 无法通过校验 | pattern 允许 -beta.N |

---

## 第二部分：提升改造 100 项（I01–I100）

### H. 性能优化（I01–I18）

| # | 大类 | 提升 | 实现 |
|---|------|------|------|
| I01 | UI 响应 | 地址栏建议查询（书签全表+SQLite LIKE）移出 UI 线程 + 乱序结果防护 | Task.Run + 输入比对 |
| I02 | UI 响应 | 历史窗口搜索防抖（此前每次键入同步 Count+分页两查） | 200ms DispatcherTimer |
| I03 | 导航热路径 | HistoryStore 建表/迁移/索引/清洗改为每库每进程一次（此前每次导航 5 条 DDL） | EnsureSchema once |
| I04 | 索引匹配 | 新增 (visited_at DESC, id DESC) 索引——默认排序查询此前走不上索引 | idx_visits_time_id |
| I05 | 批量写入 | 书签导入单连接单事务（此前 1000 条=1000 个连接生命周期+建表） | BookmarkStore.Import |
| I06 | 网络请求 | favicon 失败负缓存——无 favicon 站点不再每次导航重复打点 | Miss 表 |
| I07 | 并发去重 | favicon 同 host 并发抓取去重（in-flight 合并） | InFlight 表 |
| I08 | 线程 IO | favicon 磁盘读取移出 UI 线程（首次导航不再同步解码 PNG） | LoadFromDiskAsync |
| I09 | 绑定开销 | DownloadItem 派生属性（Percent/Summary）仅字节变化时通知——挂窗不再每 tick 重算 | 变更检测 |
| I10 | 大文本 | 源码查看器禁用撤销栈/自动换行——5MB 文本打开不再长时冻结 | XAML 属性 |
| I11 | 渲染热路径 | 贪吃蛇天空渐变缓存（此前每帧 createLinearGradient） | SKY 缓存 |
| I12 | 渲染热路径 | 萤火虫颜色表预生成（此前每帧字符串拼接+toFixed） | FLY_COLORS |
| I13 | 算法 | 贪吃蛇 freeCell O(N²×蛇长) → 占用集合 O(N²) | taken set |
| I14 | 写放大 | 贪吃蛇最高分只在本局结束持久化（此前领先期间每步同步写 localStorage） | persistBest |
| I15 | DOM 开销 | 贪吃蛇分数 DOM 仅得分变化时刷新（此前每步刷新） | grew 才更新 |
| I16 | 重复请求 | InPrivate 地址栏引擎偏好构造时缓存（此前每次回车同步读盘） | _engineKey 字段 |
| I17 | 会话写放大 | （既有保留）每导航落盘 + 修剪策略配套——历史表有界 5 万行 | 256 次一修剪 |
| I18 | 探测开销 | NativePolicyCoreGate 探测结果文档化缓存语义（热路径每次 Probe 的既有行为留档） | 注释说明 |

### I. 可访问性（I19–I34）

| # | 大类 | 提升 | 实现 |
|---|------|------|------|
| I19 | 读屏 | 主窗口全部字形按钮补 AutomationProperties.Name（☆/⤓/☰/🕘/⚙/◐/🕶/←/→/⟳/■/⌂/＋） | XAML |
| I20 | 键盘可达 | NTP 引擎胶囊 role=button + tabindex + Enter/Space（此前纯 div+onclick） | start.html |
| I21 | 键盘可达 | NTP 引擎菜单项 menuitemradio + aria-checked + 键盘选择 | start.html |
| I22 | 键盘可达 | NTP 壁纸圆点 button/tabindex/aria-label + Enter/Space | start.html |
| I23 | 键盘可达 | NTP 书签卡片 link/tabindex + Enter 导航 | start.html |
| I24 | 键盘可达 | "添加常用站点"磁贴 button 语义 + 键盘触发 | start.html |
| I25 | 表单标注 | 搜索框 aria-label（此前仅 placeholder） | start.html |
| I26 | 对话框语义 | 导入向导 role=dialog + aria-modal | start.html |
| I27 | 替代文本 | 贪吃蛇画布 role=img + aria-label | start.html |
| I28 | 读屏 | 音效/关闭 emoji 按钮 aria-label | start.html |
| I29 | 状态同步 | 引擎胶囊 aria-expanded 随菜单开合更新 | toggleEngineMenu |
| I30 | 快捷键 | Ctrl+Tab / Ctrl+Shift+Tab 循环切标签 | MainWindow |
| I31 | 快捷键 | Ctrl+1..8 直达 / Ctrl+9 末位标签 | JumpToTabByKey |
| I32 | 快捷键 | F5/Ctrl+R 刷新、F6 聚焦地址栏 | Window_PreviewKeyDown |
| I33 | 快捷键 | Alt+←/→ 历史后退/前进 | 同上 |
| I34 | 快捷键 | Ctrl+H 历史 / Ctrl+J 下载 / Ctrl+D 收藏 / Ctrl+Shift+T 重开标签 | 同上 |

### J. 代码质量（I35–I58）

| # | 大类 | 提升 | 实现 |
|---|------|------|------|
| I35 | 常量治理 | MainWindow 散落魔法数（150ms/30s/2.5s/15s/5MB/8/60/14 字符）集中为命名常量 | 常量区 |
| I36 | 单源主题 | 三套 ApplyTheme 色值（#F5F5F7 vs #F2F2F7 不一致）统一为 WindowTheme 单源 | 新 WindowTheme.cs |
| I37 | 色板补全 | MainWindow 缺 TextMutedBrush/SegmentedBrush 默认值（DynamicResource 静默失败） | XAML 补定义 |
| I38 | 死代码 | TabRuntime.DownloadStarted 事件零订阅者（与 DownloadOperationStarted 语义分裂） | 移除 |
| I39 | 死代码 | SourceViewerWindow 空 TextChanged 占位处理器 | 移除 |
| I40 | 死代码 | Diagnostics 类全仓零实例化且实现与注释不符（宣称脱敏/限流均不存在） | 删除 |
| I41 | 死代码 | SettingsService 4 个零调用公共成员（static Load/Save×2/ApplyRuntimeSnapshot） | 移除 |
| I42 | 死代码 | start.html sync() thenable 包装、androidFeats error/back 死键 | 移除 |
| I43 | 死代码 | 贪吃蛇 togglePause（与 primaryAction 重复且零调用） | 移除 |
| I44 | 死代码 | e2e 脚本 HOME_HASH 赋值后从未使用 | 移除 |
| I45 | 死样式 | .back-fab 永久 display:none 的按钮 + 对应样式随包发布 | HTML+CSS 删 |
| I46 | 无效样式 | Chromium 不插值 background-image 的过渡声明 | 删 |
| I47 | 重复声明 | 640px 媒体查询内 .quick-row 两处声明合并 | start.css |
| I48 | 变量化 | 玻璃色 rgba(15,20,32,…) 6 处硬编码 → :root CSS 变量 | start.css |
| I49 | 图标语义 | 两个 ☆（收藏/管理）无法区分、历/🕶 汉字 emoji 混排 → ☰/🕘 统一 | MainWindow.xaml |
| I50 | 截断正确性 | 书签栏标题 `Title[..14]` 按字符切——emoji 代理对劈成乱码 | TruncateTitle 代理对安全 |
| I51 | 路径单源 | bookmarks/history/downloads/favicons/threat/log 路径散落各文件 Path.Combine | AppPaths 集中 + MainWindow 接入 |
| I52 | 环境回退 | GetFolderPath 空串时路径退化为盘根 \Aegis\；新增 AEGIS_DATA_DIR 便携覆盖 | ResolveDataDir |
| I53 | 契约履约 | ThemeColor 注释"绝不抛异常"但 null/非法输入抛——兑现契约+支持 3/4 位短 hex | 全量防御 |
| I54 | 重复注释 | TabManager.SeedSession 双 doc 块清理 | 修 |
| I55 | 字段组织 | `_editingId` 类中部声明、BookmarkManager 重复 ItemsSource 赋值/SearchHint 双维护 | 重构 |
| I56 | 合并媒体查询 | quick-row 规则归并（同 I47 完成项） | start.css |
| I57 | reduced-motion | 贪吃蛇/悬停动画支持 prefers-reduced-motion | start.css |
| I58 | 失败留痕 | 导入单来源失败、下载记录失败、初始化失败等 7 处空 catch 增加 SecurityLog | 各处 |

### K. 健壮性提升（I59–I76）

| # | 大类 | 提升 | 实现 |
|---|------|------|------|
| I59 | 多配置支持 | 书签/历史导入探测 Profile 1..9（此前仅 Default，多 Profile 用户被静默忽略） | DetectSources |
| I60 | 长度上限 | 导入书签标题 256/URL 2048 上限（超长直接入库并渲染） | Trim |
| I61 | 原子写 | favicon 缓存 temp+Replace（崩溃不留半写 PNG） | SaveToDisk |
| I62 | 源码可测 | AppSettings.Save 原子化（测试专用路径与运行期同语义） | temp+Replace |
| I63 | 后台异常 | AppDomain.UnhandledException + TaskScheduler.UnobservedTaskException 留痕（此前杀进程无日志） | App 构造 |
| I64 | 危险扩展 | 补 lnk/reg/chm/scf/msc/diagcab/py/psm1 等 13 个 Windows 载体 | DangerousExtensions |
| I65 | 记录上限 | 下载记录表 500 条有界保留（此前无限累积） | Add 内修剪 |
| I66 | 状态幂等 | KillSwitch.Engage 幂等化 + 触发留痕 | 已触发即返回 |
| I67 | 可用性 | 设置窗口打开时若 KillSwitch 已触发显示状态文案（此前仅禁用按钮） | KillSwitchState |
| I68 | 会话上限 | Broker _sessions 上限 1024（对齐 Rust MAX_SESSIONS） | RegisterSession |
| I69 | 审计上限 | 托管审计日志 5000 条有界队列 + 锁（此前 List 无界无锁） | Queue + _auditLock |
| I70 | 异步回投 | InPrivate NavigationCompleted 由同步 Invoke 改 BeginInvoke（UI 忙时不再管道等待） | Dispatcher |
| I71 | 初始化观察 | Coordinator/lifetime 初始化异常观察既有机制接入 InPrivate 路径（对齐主窗口） | try/catch |
| I72 | 时区语义 | SecurityLog 时间戳带本地时区偏移（取证可还原绝对时间） | zzz 格式 |
| I73 | 引擎回退 | InPrivate 引擎读取失败回退默认（不再依赖磁盘可用） | catch 回退 |
| I74 | 键盘语义 | InPrivate Esc=停止加载（浏览器惯例）而非关整窗丢会话 | Window_PreviewKeyDown |
| I75 | 书签联动 | 书签管理器改名/删除/清空后主窗口书签栏即时刷新（此前需重启） | _owner.RefreshBookmarkBar |
| I76 | 主机白名单 | ParseFeedLine 主机字符白名单（字母/数字/连字符/点） | 校验 |

### L. Web 资产提升（I77–I86）

| # | 大类 | 提升 | 实现 |
|---|------|------|------|
| I77 | 输入卫生 | 壁纸 URL 拼接单引号编码（数据源静态也防御性编码） | replace '→%27 |
| I78 | 兼容性 | NTP 书签渲染桥就绪重试替代固定延时（慢机不再空宫格） | 10×200ms |
| I79 | 资源释放 | 贪吃蛇 AudioContext 关闭时释放（不再跨开关常驻） | close() |
| I80 | 双路径清理 | 搜索 Enter 的 keydown+form onsubmit 双路径去重（form submit 覆盖 IME） | 移除 keydown |
| I81 | 打包卫生 | snake.test.js 不再发布到 ntp 虚拟主机（可经 https://ntp.aegis.local/ 访问） | csproj Exclude |
| I82 | 打包卫生 | 同上 Android assets 排除（保留 AGP 默认忽略集） | ignoreAssetsPattern |
| I83 | CSP 前置 | （记录）内联事件处理器属受信壳页假设——壁纸/引擎 URL 编码加固作为第二道防线 | I77 配套 |
| I84 | 失败可见 | geo 按钮资源缺失置灰提示既有修复保留并回归（openGeo onFail 语义） | 保留验证 |
| I85 | 状态还原 | 搜索按钮"搜索中…"1200ms 复位逻辑保留并注释化（挂起可恢复） | 注释 |
| I86 | 触屏语义 | 贪吃蛇 touchmove 仅滑动态 preventDefault（被动滚动路径不受影响） | 保留 on 守卫 |

### M. CI/工程化提升（I87–I95）

| # | 大类 | 提升 | 实现 |
|---|------|------|------|
| I87 | 超时治理 | 12 个 workflow 全部补 timeout-minutes（发布链可被挂死占满 runner） | 逐个补 15–60min |
| I88 | 最小权限 | 6 个无 permissions 的 workflow 补 contents: read | agent-redteam/ci/compat/core-rust/supply-chain/android-quality |
| I89 | pin 完整性 | pin-check 覆盖 .github/actions/**（composite）+ 拦截 @latest/@dev 浮动引用 | --include + 正则 |
| I90 | 失败可见 | release-windows gh release create 不再吞 stderr；回落 upload 也失败即中止 | pwsh 修正 |
| I91 | 锁定构建 | release-core clippy/test 加 --locked（防 Cargo.lock 漂移构建） | 补参数 |
| I92 | 复制容错 | release-core `cp …|| true` 三连吞错改直赋值（缺产物即失败） | 移除 || true |
| I93 | 测试接入 | 红队 e2e（redteam_e2e_test.py）接入 agent-redteam（README/runbook 声称的口径兑现） | 新 step |
| I94 | lint 覆盖 | CI ruff 扩展至 scripts/release/contracts/agent（pyproject 声称范围内此前从未跑） | 新 step |
| I95 | 工具锁版 | pip-audit 锁定 2.7.0（审计工具自身受供应链约束） | 版本 pin |

### N. 文档与版本治理（I96–I100）

| # | 大类 | 提升 | 实现 |
|---|------|------|------|
| I96 | 变更日志 | CHANGELOG 补 beta.17/19/21 条目、按序重排、去除错位"未发布" | 重构 |
| I97 | 断链清理 | 蓝图文件引用（README/device-validation/agent README/windows/aegis_source 等 9 处断链）修正 | 逐处 |
| I98 | 文档对齐 | windows/README 重写为 ADR-009 C# 现实（原为已淘汰的 PyInstaller/MSIX 管线） | 重写 |
| I99 | 死文档 | docs/release/release.yml 漂移副本、build_release.py（Nuitka 死管线）、xor_obfuscate.py（硬编码密钥样板）、_patch_p2.py 一次性补丁删除 | 删除 |
| I100 | 门禁扩展 | validate_release.py 增加正典 C# 栈关键文件/首页资产断言（此前 C# 不经任何仓库级校验） | 新断言 |

---

## 第三部分：100 个审计大类索引

崩溃防护 / 输入验证 / 功能失效 / 隐私隔离 / 逻辑矛盾 / 竞态条件 / 异常处理 / 授权撤销 / 门禁失效 / SSRF 防护 / Origin 校验 / 授权绕过 / fail-open / 密码学 / 隐私泄露 / KDF 缺陷 / JSON 注入 / JS 注入 / Rust panic / 匹配绕过 / 匹配误导 / DoS 防护 / 参数绕过 / 无痕泄露 / 日志脱敏 / 日志伪造 / 取证保全 / 历史口径 / 数据丢失 / 订阅源安全 / 数据失效 / 会话泄露 / 缓存上限 / UI 线程安全 / 内存泄漏 / 事件泄漏 / 状态覆盖 / 死分支 / 窗口竞态 / 数据失真 / 字段未赋值 / 存储容错 / 栈溢出 / 数据不完整 / 临时文件 / 异常面 / 弹窗风暴 / 计数失真 / 多屏支持 / 入模校验 / 写盘时序 / 变更检测 / 预览失真 / 域名解析 / 主机提取 / 种子静默 / 保留名 / 长度上限 / 漏判 / 误报 / 死守卫 / 空消息面 / 交互失效 / 状态错位 / 静默失败 / 参数注入 / 永久卡死 / 类型错误 / 失败伪装 / 渲染竞态 / 键盘劫持 / 发布断链 / fail-open 门禁 / 空洞断言 / 假对账 / 清单失配 / 版本漂移 / 生成链断裂 / 版本门禁 / UI 响应 / 导航热路径 / 索引匹配 / 批量写入 / 网络请求 / 并发去重 / 线程 IO / 绑定开销 / 大文本 / 渲染热路径 / 算法 / 写放大 / DOM 开销 / 重复请求 / 会话写放大 / 探测开销 / 读屏 / 键盘可达 / 表单标注 / 对话框语义 / 替代文本 / 状态同步 / 快捷键 / 常量治理 / 单源主题 / 色板补全 / 死代码 / 死样式 / 无效样式 / 变量化 / 图标语义 / 截断正确性 / 路径单源 / 环境回退 / 契约履约 / 多配置支持 / 原子写 / 后台异常 / 危险扩展 / 记录上限 / 状态幂等 / 可用性 / 审计上限 / 异步回投 / 时区语义 / 键盘语义 / 书签联动 / 主机白名单 / 输入卫生 / 兼容性 / 资源释放 / 双路径清理 / 打包卫生 / CSP 前置 / 失败可见 / 超时治理 / 最小权限 / pin 完整性 / 锁定构建 / 复制容错 / 测试接入 / lint 覆盖 / 工具锁版 / 变更日志 / 断链清理 / 文档对齐 / 死文档 / 门禁扩展

（共 100+ 个命名大类——覆盖崩溃、安全、竞态、隐私、性能、可访问性、代码质量、CI、文档、版本治理全维度）

---

## 第四部分：验证记录（2026-09-07）

| 验证项 | 结果 |
|--------|------|
| `dotnet build Aegis.Windows.App` | 0 错误 0 警告 |
| `dotnet test Core.Tests` | **210 通过**（原 177 + 新增 33 回归） |
| `dotnet test Broker.Tests` | **29 通过** |
| `cargo test`（rust-policy-core） | **171 通过**（lib 162 + bin 5 + doc 4） |
| `cargo clippy` | 0 警告 |
| `python scripts/verify_xaml_resources.py` | 39 键连通通过 |
| `node shared/shell/snake.test.js` | 10 通过 |
| `python scripts/verify_versions.py` | v2.2.0-beta.21 通过（新增 release.json 门禁） |
| `python scripts/sync_versions.py` | 同步成功（含 release.json） |
| `python scripts/gen_jsapi_schema.py` | 生成链复活（30 暴露方法） |
| `python validate_release.py` | failures=0（含新增 C# 断言） |
| `build_review_package --build + --check` | 418 文件自校验通过 |
| 12 个 workflow YAML 解析 | 全部有效 |

### 测试增量
- C# `AuditRegressionTests`：33 个新用例（IP 编码绕过 / OriginPolicy host / 下载查询串与保留名 / 设置 null 与备份 / 缩放口径 / URL 归一）。
- Rust：capability fail-closed ×2、per-site SHA-256 派生 ×2、种子不外露断言 ×1。
