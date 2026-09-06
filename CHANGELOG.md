
## beta.16 (2026-09-07)
### Fixed (崩溃 V3：安装版打不开——书签栏资源未定义)
- **根因**：`RefreshBookmarkBar()` 调 `FindResource("BookmarkBarButton")`，但该资源在仓库从未定义。本机/无书签机器循环为空侥幸通过；**只要收藏过书签，启动即抛
  `ResourceReferenceKeyNotFoundException` → MainWindow 构造失败 → 安装版无法打开**。
- 在 MainWindow.xaml 定义 `BookmarkBarButton` 样式（Apple 圆角胶囊）。
- `RefreshBookmarkBar()` 防御化：样式资源缺失不再中断启动。
- 清理 beta.14 遗留：删除重复的 `DownloadOperationStarted` 持久化订阅（双写下载记录）。
- 新增 `scripts/verify_xaml_resources.py` 并接入云端 fail-closed 断言：发布前强制校验
  每个 `FindResource(key)` 都有对应 `x:Key`，杜绝同类崩溃回归。

## beta.18 (2026-09-07)
### Fixed (安装版崩溃 V3 真因 + native 策略桥缺陷)
- **安装版崩溃根因**：`RefreshBookmarkBar()` 调 `FindResource("BookmarkBarButton")`，该资源从未定义。收藏过书签即启动抛
  `ResourceReferenceKeyNotFoundException` → 打不开。定义样式 + FindResource 防御化。
- **原生策略桥确定性缺陷**：`consume_navigation` 绑定比较 `*issued == action` 含 `explanation` 审计字段，而托管端
  `NativeAction` 往返不携带它 → 合法一次消费被误判 `action_not_issued`（native 严格模式必现；CI 因设置
  AEGIS_REQUIRE_NATIVE_POLICY_CORE=1 而暴露）。Rust 侧改为 `same_binding`（剔除 explanation）+ 新增 C-ABI 回归测试。
- 新增 `scripts/verify_xaml_resources.py` 并接入云端 fail-closed 断言；原生桥测试关闭集合并行。

## beta.20 (2026-09-07)
### Fixed (首页首帧纯文字文档——虚拟主机映射启动竞态)
- NTP 延迟导航由单次 Normal 优先级 BeginInvoke 改为 `DispatcherPriority.ApplicationIdle`，
  确保 SetVirtualHostNameToFolderMapping 在启动争用下也已传播到渲染进程，避免
  ntp.aegis.local 解析失败 → WebView2 呈现纯文本错误文档。
- 新增 `NavigationCompleted` 有界失败重试（主窗口协调器 + InPrivate 一致）：首帧若
  ConnectionAborted 稍后自动重试，重试时映射必然已就绪。

## 未发布 (2026-09-07)
### 放开本机域名与 hosts 域名访问（本地开发场景）
- 新增 `UrlSafety.CanOpenHttpUrl`（公网 或 本机/hosts）与 `IsLocalHostOrResolvesLocalHost`
  （DNS 带缓存判定：localhost/.localhost/回环 IP 快路径，hosts 映射域名解析到回环即放行）。
- 新窗口 target=_blank 入口改用 `CanOpenHttpUrl`，本机域名可打开（此前被拒）。
- HTTPS-only 对本机域名不升级为 https——本地服务器通常只跑 http，升级必然失败
  （"开屏纯文字加载画面"根因之一）。
- 地址栏：localhost/foo.localhost（含端口）直接导航到 http:// 本机，不再当搜索词；
  回环/IP 字面量补 http；修掉预存 bug——`example.com:8080` 被 SchemePrefix 误判为
  非导航 scheme 而拒绝（host:port 冒号后是数字端口即非协议）。
