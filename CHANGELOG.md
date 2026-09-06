
## beta.16 (2026-09-07)
### Fixed (崩溃 V3：安装版打不开——书签栏资源未定义)
- **根因**：`RefreshBookmarkBar()` 调 `FindResource("BookmarkBarButton")`，但该资源在仓库从未定义。本机/无书签机器循环为空侥幸通过；**只要收藏过书签，启动即抛
  `ResourceReferenceKeyNotFoundException` → MainWindow 构造失败 → 安装版无法打开**。
- 在 MainWindow.xaml 定义 `BookmarkBarButton` 样式（Apple 圆角胶囊）。
- `RefreshBookmarkBar()` 防御化：样式资源缺失不再中断启动。
- 清理 beta.14 遗留：删除重复的 `DownloadOperationStarted` 持久化订阅（双写下载记录）。
- 新增 `scripts/verify_xaml_resources.py` 并接入云端 fail-closed 断言：发布前强制校验
  每个 `FindResource(key)` 都有对应 `x:Key`，杜绝同类崩溃回归。
