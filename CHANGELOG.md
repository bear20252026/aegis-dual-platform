# 变更日志（Changelog）

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

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
