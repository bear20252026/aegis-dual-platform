# CLAUDE.md — 项目协作指南（AI 助手 / 开发者共用）

本文件让 AI 助手（Claude Code / AtomCode 等）与人类开发者共享一致的上下文、命令与规范，避免"零全局意识"导致的错误改动。**任何 AI 辅助开发前请先通读本文件。**

## 项目一句话

Aegis 双端安全浏览器：Windows（Python + pywebview + WebView2）+ Android（Kotlin + Compose + System WebView），隐私与安全优先。

**Windows 双栈口径（ADR-007）**：C#/.NET 10（`windows/`）为目标发布栈；
`legacy/windows-pywebview/` 为**现役功能栈**（目录名 `legacy` 是 Qt 迁移期
历史遗留——语义为「迁移中」而非「废弃」）；`legacy/` 下的 Qt 与 `legacy/ui/`
为已归档死代码，禁止 import。

## 关键命令（必须先跑）

```bash
# Windows 端静态验证（改动 Python 代码后必跑）——与 CI 口径一致
python validate_release.py            # AST/JSON/XML/版本声明（仓库根运行）
cd legacy/windows-pywebview
ruff check . --exclude legacy --ignore RUF001,RUF003,E501,TRY300,TRY003,TRY301,RUF021,E402,I001
bandit -r app/ -q --skip B110,B404,B603,B607   # 安全扫描（无 Medium/High）
mypy main_webview.py app/             # 类型检查（0 错误）

# 自检（改动标签/桥/工具栏/会话后必跑——已入 CI）
python selftest_session_store.py
python selftest_api_bridge.py
python selftest_s1_integration.py
python selftest_shell_toolbar.py
python selftest_tab_state.py

# Bridge 守卫单一事实源（改动守卫 JS 后必跑——ADR-007）
python contracts/codegen/verify_bridge_guard.py

# Android 端（需 Android Studio 环境；CI 以 ktlint/detekt 为准）
./gradlew.bat :app:lintDebug
```

## 架构红线（改动前必须确认）

1. **Windows 正式入口是 `main_webview.py`**（薄壳；现役功能栈见 ADR-007 双栈口径）。`legacy/windows-pywebview/legacy/` 与 `legacy/ui/` 是已归档的 Qt 旧栈，**禁止**从活跃代码 import 它。
2. **单文件单职责**：新文件 ≤ 300 行；改造后 ≤ 500 行。不为拆而拆，也不堆职责。
3. **URL 安全关口**：所有导航入口（IPC/会话/书签/历史/拨号/命令行/地址栏）加载 URL 前必须经 `app/security.py` 的 `safe_url()`。
4. **js_api 白名单**：暴露给 JS 的方法必须加入 `app/api_bridge.py` 的 `_JS_EXPOSED`（防 pywebview 递归注入死锁）。
5. **窗口操作走 NavQueue**：js_api 回调线程**绝不**同步调用 load_url/evaluate_js，必须投递到 `app/nav_queue.py`。
6. **Android 安全配置**：每个 WebView 必须经 `SecureWebViewFactory` 创建（复用 BrowserEngine 安全边界）。
7. **凭据红线**：绝不把 token/密钥/证书/key.properties/.jks 写进代码或提交；安全敏感信息仅私密渠道传递。

## 代码检查清单（提交前自查）

- [ ] validate_release / ruff / bandit / mypy 全过
- [ ] 遵守单文件单职责与行数红线
- [ ] 涉及 URL/密码/下载/权限时说明了安全考虑
- [ ] 新增逻辑有对应自检（selftest_*.py）
- [ ] 更新了 CHANGELOG.md
- [ ] 遵循 Conventional Commits（feat/fix/refactor/docs/chore/security）

## 常用文件地图

| 路径 | 职责 |
|---|---|
| `legacy/windows-pywebview/main_webview.py` | 薄入口（建窗/绑定/看门狗） |
| `legacy/windows-pywebview/app/api_bridge.py` | js_api 桥（标签/导航/书签/历史/导入） |
| `legacy/windows-pywebview/app/nav_queue.py` | 导航线程队列（防死锁） |
| `legacy/windows-pywebview/app/shell_toolbar.py` | 注入式工具栏（标签条/快捷键/毛玻璃） |
| `legacy/windows-pywebview/app/security.py` | URL 白名单 / 权限收紧 |
| `legacy/windows-pywebview/app/browser_import.py` | Chrome/Edge 书签与历史导入 |
| `android/app/src/main/java/com/aegis/browser/` | Android 端（TabManager/TabBar/SecureWebViewFactory） |
| `shared/version.properties` | 双端版本单一来源 |

## 常见陷阱

- `validate_release.py` 用相对路径定位项目根，**不要**改回硬编码绝对路径。
- `python` 命令在本机可能被 Store 别名拦截：用 `py` 或显式 Python 路径。
- Windows 上 Git Bash 的 `/tmp` 与 Python 路径不一致：别让 Python 读 Git Bash 的 /tmp 文件。
- 快捷键/JS 注入改动后必须跑 `selftest_shell_toolbar.py`（校验占位符替换与 JSON 转义）。
