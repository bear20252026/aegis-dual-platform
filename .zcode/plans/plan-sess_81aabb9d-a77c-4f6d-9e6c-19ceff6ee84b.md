# 历史记录真分页加载（按需分页，不再一次性全载）

## 现状问题（已确认）

`HistoryWindow.Reload` 用 `HistoryStore.SearchRange(query, from, to, _limit)`，初始 `_limit=200`；点「加载更多」把 `_limit += 300` 后**重新查询全部 1..N 条并整体重建列表**。长历史（千/万条）时每次翻页都重查+重绘全部，负担并未减轻——不是真分页。

## 方案：游标分页 + 追加式加载

### 1. 数据层 —— `HistoryStore` 增游标分页

- 新增 `SearchRangePaged(query, from, to, pageSize, Cursor? after)`：
  - 排序键 `visited_at DESC, id DESC`（时间相同用 id 兜底，稳定不重复/不跳）；
  - 用**键集分页**（游标）：`WHERE (...筛选...) AND (visited_at, id) < ($ta, $id)`（多列行值比较），比 `OFFSET` 稳——翻页期间新增记录不会导致重复/漏页；
  - 每页取 `pageSize+1` 条，第 `pageSize+1` 条存在 → 说明还有下一页，返回 `HasMore=true`；
  - 全部参数绑定（安全约束：不拼接 SQL，游标来自上页末条）；
  - 空查询+空区间回退 `RecentPaged`（同游标逻辑）。

### 2. 界面 —— `HistoryWindow` 追加式加载

- 初次加载只取**第一页（100 条）**并渲染；
- **滚动到底部**（ScrollViewer 接近底部）或点「加载更多」→ 用上页末条游标拉下一页，**追加**到现有列表（不重建已有项）；
- 新页条目**合并进已有日期分组**：同日期并入现有 `DayGroup`，新日期新建组并按日期倒序插入——保持按日期分组的观感；
- 列表尾部状态：`已加载 N 条`（+「加载中…」转态）；`HasMore=false` 时隐藏按钮；
- **搜索词/日期筛选变化 → 重置游标、清空列表、从第一页重新拉**；
- 删除单条/清空后按当前筛选重置并刷新；
- 数据模型用可变集合（`ObservableCollection<DayGroup>`/行集合），追加走 `Add`，不整表替换。

### 3. 性能收益

- 首屏只渲染 100 条；长历史滚动逐页加载，内存与绘制负载恒定（配合既有虚拟化 ListBox）。

### 4. 回归测试

- `HistoryStore` 游标分页：跨多页不重不漏、翻页期间插入不跳、`HasMore` 边界、筛选+游标组合、参数绑定；
- `HistoryWindow` 构造冒烟（现有）保持绿。

### 5. 发布流程（云端构建）

- build 0 警告 0 错误 + 全量测试绿 → 提交推送（代理→直连回退）→ 版本升 **v2.2.0-beta.6**（VERSION_CODE 20205）→ `sync_versions.py`+`verify_versions.py` → tag 推送 → **GitHub 云端构建** → 轮询全绿 → 下载 `AegisBrowser-CSharp-Setup-2.2.0-beta.6.exe`（含 GeoGebra，约 24MB）→ **打开安装包文件夹**。

## 涉及文件

- `Core/History/HistoryStore.cs`（新增游标分页方法）
- `Chrome/HistoryWindow.xaml.cs`（追加式加载/滚动触底/分组合并/筛选重置）+ `HistoryWindow.xaml`（滚动触发/状态文案）
- `tests/.../HistoryStorePagingTests.cs`（新分页单测）
