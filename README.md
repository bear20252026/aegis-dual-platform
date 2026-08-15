# Aegis 双端安全浏览器

Aegis 是一款**双平台安全浏览器**：Windows 端基于 Python + pywebview + WebView2（Evergreen Runtime），Android 端基于 Kotlin + Jetpack Compose + Android System WebView。以隐私、安全、本地 AI 与双端统一代码基线为核心设计目标。

> 许可证：MIT（详见 [LICENSE](LICENSE)）

---

## 目录

| 目录 | 内容 |
|---|---|
| `windows/aegis_source` | Windows 源码工作副本，正式入口为 `main_webview.py`（pywebview + WebView2） |
| `windows/packaging` | MSIX、App Installer、Windows 构建脚本（`build-windows.ps1`） |
| `android` | Kotlin + Jetpack Compose + Android WebView 浏览器工程（含多标签、安全 WebView 工厂） |
| `shared` | 双端版本、发布与更新清单协议 |
| `scripts` | 从单一版本配置同步双端版本声明的脚本 |
| `docs` | 项目文档（KNOWLEDGE_BASE 21 节项目记忆 + 25 份调研/审计/设计/评估报告） |
| `docs/release` | **B 级发布期实施产物**（build_release.py 构建 / xor_obfuscate.py 加固 / release.yml 签名发布流水线） |
| `legacy`（位于 `windows/aegis_source/legacy`） | 已归档的 QtWebEngine 旧栈（不再维护，仅供历史参照） |

## 架构

```
Windows（正式路线）          Android
Python + pywebview           Kotlin + Jetpack Compose
  └─ WebView2 Evergreen        └─ Android System WebView
      └─ 注入式工具栏(标签栏)       └─ TabManager 多标签
          └─ js_api 桥                └─ SecureWebViewFactory
              └─ NavQueue 导航线程队列     └─ BrowserEngine(安全边界)
```

### Windows 端模块（单文件单职责）

| 文件 | 职责 |
|---|---|
| `main_webview.py` | 薄入口：参数解析、建窗口、绑定 Api、启动看门狗 |
| `app/shell_adapter.py` | **壳抽象**：Shell 协议（create_window/start/events/core/settings/windows）+ pywebview/pytauri 可插拔（壳可替换——禁止被困原则） |
| `app/shell_toolbar.py` | 注入式工具栏脚本（标签条/导航/地址栏/毛玻璃/快捷键/hints 键盘模式） |
| `app/nav_queue.py` | 导航线程队列（窗口操作串行化，杜绝 js_api 死锁） |
| `app/api_bridge.py` | js_api 桥（标签/导航/书签/历史/壁纸/搜索/JS 错误上报——含消息来源验证） |
| `app/security.py` | 统一安全关口（URL 白名单、权限收紧） |
| `app/threat_feed.py` | 威胁黑名单订阅（host_is_blocked 精确/子域匹配——deny 优先） |
| `app/credential_guard.py` | 凭据脱敏（日志写入前屏蔽凭据值——FreeDom 反 dump 理念） |
| `app/event_log.py` | 统一日志接口（业务层委托 crash_reporter——DRY 消重） |
| `app/mcp.py` | Agent 桥（MCP 7 工具白名单 + 调用审计 + untrusted 标注 + 严格 Schema） |
| `app/webview2_probe.py` | WebView2 性能基线 + ESM 探测（EnhancedSecurityModeState） |
| `app/asset_scheme.py` | 壁纸资源白名单（NFKC 输入规范化——pyscg-0044） |
| `app/backdrop.py` | Windows 11 系统级 Mica/亚克力背景（尽力而为） |
| `app/config.py` / `paths.py` / `bookmark_store.py` / `history_store.py` / `database.py` | 类型化配置 / 路径 / 书签 / 历史 / 数据库存储 |
| `app/url_utils.py` / `reader.py` / `browser_import.py` / `fingerprint.py` / `bridge_hooks.py` | URL 工具 / 阅读模式 / 浏览器导入 / 指纹配置（默认关）/ 桥钩子 |

### Android 端模块

| 文件 | 职责 |
|---|---|
| `MainActivity.kt` | 薄壳组装（TabManager + TabBar + SecureWebViewFactory） |
| `TabManager.kt` | 多标签增删/切换/挂起恢复（默认 8 活跃） |
| `TabBar.kt` | Compose 标签栏（横滚标签 + 新建/关闭，亚克力风格） |
| `BrowserEngine.kt` | WebView 安全配置（http/https 白名单、禁 file/混合内容/调试） |
| `SecureWebViewFactory.kt` | 统一创建安全 WebView（多标签复用安全配置） |

## 安全设计

- **统一导航过滤**：所有入口（IPC/会话/书签/历史/命令行/地址栏）加载 URL 前经 `safe_url()` 白名单（http/https）
- **WebView 硬边界**（Android）：关闭文件访问、内容访问、file URL 跨域、混合内容；非调试模式禁用 WebView 调试
- **密码加密存储**：Fernet + Windows DPAPI / 系统密钥环，无加密能力时拒绝明文落盘
- **危险下载拦截**：可执行/脚本类扩展名二次确认
- **敏感文件权限**：POSIX 0600 / Windows DACL 仅当前用户
- **无痕模式**：密码/历史/拨号强制不落盘
- **计算机使用（模式 B）**：动作白名单 × 权限等级（L0-L3）交叉校验，密码明文不进模型上下文
- **威胁拦截 deny 优先**：`threat_feed` 黑名单命中优先于白名单放行（导航层 + 请求管线双关口）
- **凭据治理**：环境变量外部化（不落地）+ `credential_guard` 日志脱敏（FreeDom 反 dump 理念）
- **统一日志**：`event_log` 单入口（业务层零散日志收敛——DRY）
- **Agent 安全**（mcp.py）：7 工具白名单 + 调用审计 + untrusted 标注 + 严格 JSON Schema（防参数注入）
- **ESM 禁 JIT**：EnhancedSecurityModeState 探测 + 按来源动态 CoreWebView2Settings（A4）
- **核心模块编译保护**（B 级）：Nuitka 编译 security/credential_guard/threat_feed/mcp 为 .pyd（免费路线）

## 静态验证

```bash
python3 validate_release.py        # Python AST / JSON / XML 模板 / 版本声明
python3 scripts/sync_versions.py   # 同步双端版本声明
```

代码质量检查（2026 工具链）：

```bash
ruff check .                       # Lint + 格式（项目自带 ruff.toml）
bandit -r app/                     # 安全扫描
mypy main_webview.py app/          # 类型检查
```

## 构建

> 当前遵循"**先完成代码和发布配置，后安装工具并构建验证**"的约束；以下为工具就绪后的构建顺序。

1. 安装并验证 Android SDK/JDK/Gradle Wrapper，执行 Android `build-android.ps1`
2. 安装并验证 Python、PyInstaller、Windows SDK 的 `makeappx` 与 `signtool`，执行 Windows `build-windows.ps1`
3. 配置代码签名证书或可信签名服务，生成签名 APK/AAB/MSIX
4. 在干净 Windows 与 Android 设备上测试安装、升级、卸载、数据保留与下载验证

### B 级发布期实施（docs/release/——发布流水线，不触碰开发分支）

```bash
# ① 构建（Nuitka 编译核心敏感模块 + 不编译模块分层）
python docs/release/build_release.py
# ② XOR 常量加固（数据文件加密，密钥嵌入编译模块）
python docs/release/xor_obfuscate.py encrypt <file>
# ③ 签名/发布流水线（sigstore keyless + Trusted Publishing——release.yml 草稿）
#    详见 docs/release/release.yml（受保护环境审批 + OIDC 无 token）
```

### 运行（源码，Windows）

```bash
cd windows/aegis_source
python main_webview.py             # 启动浏览器
python main_webview.py --smoke-test  # 无窗口自检
```

## 当前决策记录

- **Windows**：仅面向 WebView2 Evergreen Runtime，不再维护 macOS 后端与 NSIS 安装脚本；MSIX 运行时应用内 EXE 更新器自动停用，更新职责交 App Installer
- **Android**：首个引擎为 Android System WebView；`BrowserEngine` 已锁定安全边界，后续可在保留边界前提下评估 GeckoView
- **Qt 旧栈**：已归档至 `windows/aegis_source/legacy/`，不再维护

## 贡献

欢迎参与开发，请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [SECURITY.md](SECURITY.md)。

## 变更记录

见 [CHANGELOG.md](CHANGELOG.md)。
