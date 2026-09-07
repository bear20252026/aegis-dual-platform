# Changelog

## 未发布（全仓 200 项审计整改 2026-09-07）
### 安全（P0/P1）
- 书签管理窗口 P0 崩溃：补齐缺失的 `PrimaryButton`/`GhostButton` 样式（此前窗口必崩）。
- InPrivate 环境隔离：每无痕窗口独立临时用户数据目录 + 引用计数清理（此前多窗口共享环境且抢先删目录）；
  InPrivate 补齐 NTP 宿主桥（此前无痕窗口搜索/壁纸全部静默失效）。
- 无痕隐私：favicon/缩放不落盘（会话内存态）；`UrlSafety` 补 IPv4-mapped IPv6/组播/非点分 IP 编码绕过；
  `OriginPolicy` 拒绝尾点 host/IDN 残留；Broker 消费点强制 KillSwitch、native 路径补黑名单门禁、审计 URL 脱敏。
- Rust 核心：指纹种子改用 OS CSPRNG 且不再全局暴露；per-site 种子 SHA-256 域密钥分离；
  会话 JSON 序列化转义；capability origin 白名单 fail-closed；oracle 移除 `safe_` 前缀 fail-open 后门。
### 稳定性
- 设置读取失败先备份 `.bak` 再回退默认（防启动即覆盖用户设置）；`ZoomByHost:null` 启动崩溃修复；
  历史/会话/书签存储全部容错化（磁盘异常不再向导航事件上抛）；全局异常兜底频控 + 后台线程留痕。
### 体验/性能
- 全部独立窗口接入深浅主题（WindowTheme 单源）；快捷键补 Ctrl+Tab/1-9/H/J/D/F5/Alt+←→；
  地址栏建议/历史搜索防抖 + 后台线程化；建议列表鼠标可点；贪吃蛇渲染缓存与 localStorage 写放大修复；
  NTP 首页键盘可达性（引擎/壁纸/书签）与导入向导超时兜底。
### 工程
- 发布链修复：verify-gate fail-closed（缺校验文件/空清单/未列明文件即失败）、去重后重生成 SHA 清单、
  12 个 workflow 补 timeout/permissions；`gen_jsapi_schema.py` 路径修复（生成链复活）；`shared/release.json`
  版本对齐 + 纳入 verify/sync 门禁；CI ruff 扩展至 scripts/release/contracts/agent；红队 e2e 接入 CI。

## beta.21 (2026-09-07)
### 放开本机域名与 hosts 域名访问 + P0 安全/CI 加固
- 新增 `UrlSafety.CanOpenHttpUrl`（公网 或 本机/hosts）与 `IsLocalHostOrResolvesLocalHost`
  （DNS 带缓存判定：localhost/.localhost/回环 IP 快路径，hosts 映射域名解析到回环即放行）。
- 新窗口 target=_blank 入口改用 `CanOpenHttpUrl`，本机域名可打开（此前被拒）。
- HTTPS-only 对本机域名不升级为 https——本地服务器通常只跑 http，升级必然失败
  （"开屏纯文字加载画面"根因之一）。
- 地址栏：localhost/foo.localhost（含端口）直接导航到 http:// 本机，不再当搜索词；
  回环/IP 字面量补 http；修掉预存 bug——`example.com:8080` 被 SchemePrefix 误判为
  非导航 scheme 而拒绝（host:port 冒号后是数字端口即非协议）。
- **CI 门禁补齐**：Core.Tests（177 个）接入 contracts.yml 与 release-windows.yml（此前只跑 Broker）；release 链构建发布 DLL 前跑 `cargo test --locked`——随包原生策略核心必须是"测过"的产物。
- **原生 nonce 账本自锁修复**（审计发现 F）：原生模式 consumed nonce 加 sessionId 前缀，DestroySession 可清理——此前裸 Rust nonce 永不清理，满 5 万后该 broker 全站导航永久锁死。
- **下载授权失效修复**（审计发现 G, ADR-002）：AllowDownload 返回值接入实际门禁——会话失效/kill-switch 时拒绝下载（此前仅留痕放行）。
- **跟踪过滤器豁免虚拟主机**（审计发现 A）：严格模式 + 跨站导航过渡期不再误判 NTP/GeoGebra 自带页 JS/WASM 为第三方而 403。

## beta.20 (2026-09-07)
### Fixed (首页首帧纯文字文档——虚拟主机映射启动竞态)
- NTP 延迟导航由单次 Normal 优先级 BeginInvoke 改为 `DispatcherPriority.ApplicationIdle`，
  确保 SetVirtualHostNameToFolderMapping 在启动争用下也已传播到渲染进程，避免
  ntp.aegis.local 解析失败 → WebView2 呈现纯文本错误文档。
- 新增 `NavigationCompleted` 有界失败重试（主窗口协调器 + InPrivate 一致）：首帧若
  ConnectionAborted 稍后自动重试，重试时映射必然已就绪。

## beta.19 (2026-09-07)
### Fixed (CI 稳定性)
- `verify_xaml_resources.py` 强制 UTF-8 输出——修复 Windows 控制台编码（GBK）导致的断言误失败。

## beta.18 (2026-09-07)
### Fixed (安装版崩溃 V3 真因 + native 策略桥缺陷)
- **安装版崩溃根因**：`RefreshBookmarkBar()` 调 `FindResource("BookmarkBarButton")`，该资源从未定义。收藏过书签即启动抛
  `ResourceReferenceKeyNotFoundException` → 打不开。定义样式 + FindResource 防御化。
- **原生策略桥确定性缺陷**：`consume_navigation` 绑定比较 `*issued == action` 含 `explanation` 审计字段，而托管端
  `NativeAction` 往返不携带它 → 合法一次消费被误判 `action_not_issued`（native 严格模式必现；CI 因设置
  AEGIS_REQUIRE_NATIVE_POLICY_CORE=1 而暴露）。Rust 侧改为 `same_binding`（剔除 explanation）+ 新增 C-ABI 回归测试。
- 新增 `scripts/verify_xaml_resources.py` 并接入云端 fail-closed 断言；原生桥测试关闭集合并行。

## beta.17 (2026-09-07)
### Fixed (原生策略核心确定性 + 测试稳定)
- Rust `consume_navigation` 绑定比较改用 `same_binding`（剔除 explanation 审计字段）——修复
  C# `NativeAction` 往返不携带该字段导致的 `action_not_issued` 误判（native 严格模式必现）+ C-ABI 回归测试。
- 原生策略桥测试关闭集合并行——消除云 runner 原生 DLL 加载并发抖动。

## beta.16 (2026-09-07)
### Fixed (崩溃 V3：安装版打不开——书签栏资源未定义)
- **根因**：`RefreshBookmarkBar()` 调 `FindResource("BookmarkBarButton")`，但该资源在仓库从未定义。本机/无书签机器循环为空侥幸通过；**只要收藏过书签，启动即抛
  `ResourceReferenceKeyNotFoundException` → MainWindow 构造失败 → 安装版无法打开**。
- 在 MainWindow.xaml 定义 `BookmarkBarButton` 样式（Apple 圆角胶囊）。
- `RefreshBookmarkBar()` 防御化：样式资源缺失不再中断启动。
- 清理 beta.14 遗留：删除重复的 `DownloadOperationStarted` 持久化订阅（双写下载记录）。
- 新增 `scripts/verify_xaml_resources.py` 并接入云端 fail-closed 断言：发布前强制校验
  每个 `FindResource(key)` 都有对应 `x:Key`，杜绝同类崩溃回归。
