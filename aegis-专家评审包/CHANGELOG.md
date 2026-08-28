# 变更日志（Changelog）

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增（Planned）
- Windows 标签增强：拖拽排序、固定标签、中键关闭、Ctrl+T/W 快捷键、会话恢复 UI
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
