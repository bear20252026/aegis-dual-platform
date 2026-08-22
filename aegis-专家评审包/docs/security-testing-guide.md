# Aegis Browser 安全测试资料

> 生成时间：2026-08-22
> 版本：2.1.6
> 测试目标：源代码审计、构建产物验证、安全功能测试

---

## 一、源代码结构

### 1.1 Rust 策略核心（28 个模块）

| 模块 | 文件 | 职责 |
|------|------|------|
| shield.rs | `core/rust-policy-core/src/shield.rs` | 指纹防护种子 + Canvas/WebGL/Audio 噪声 |
| letterbox.rs | `core/rust-policy-core/src/letterbox.rs` | 屏幕/窗口尺寸圆整（防屏幕指纹） |
| per_site_seed.rs | `core/rust-policy-core/src/per_site_seed.rs` | eTLD+1 独立种子（防跨站关联） |
| query_strip.rs | `core/rust-policy-core/src/query_strip.rs` | URL 追踪参数剥离（30+ 参数） |
| font_norm.rs | `core/rust-policy-core/src/font_norm.rs` | 字体列表归一化（防字体指纹） |
| webgl_spoof.rs | `core/rust-policy-core/src/webgl_spoof.rs` | WebGL GPU 参数伪装 |
| timer_prec.rs | `core/rust-policy-core/src/timer_prec.rs` | 定时器精度降低（1000μs + jitter） |
| tostring_guard.rs | `core/rust-policy-core/src/tostring_guard.rs` | Function.prototype.toString 欺骗 |
| ext_proxy.rs | `core/rust-policy-core/src/ext_proxy.rs` | 匿名扩展下载代理 |
| protection_mode.rs | `core/rust-policy-core/src/protection_mode.rs` | 三种保护模式（兼容/平衡/最大隐私） |
| space_routing.rs | `core/rust-policy-core/src/space_routing.rs` | URL 到工作区路由 |
| command_bar.rs | `core/rust-policy-core/src/command_bar.rs` | 统一命令搜索面板 |
| broker.rs | `core/rust-policy-core/src/broker.rs` | 导航决策引擎（fail-closed） |
| decision.rs | `core/rust-policy-core/src/decision.rs` | 类型化安全决策 |
| executor.rs | `core/rust-policy-core/src/executor.rs` | 副作用执行器 |
| policy.rs | `core/rust-policy-core/src/policy.rs` | 策略定义 |
| oracle.rs | `core/rust-policy-core/src/oracle.rs` | 策略评估 |
| matcher.rs | `core/rust-policy-core/src/matcher.rs` | URL/域名匹配器 |
| adblock.rs | `core/rust-policy-core/src/adblock.rs` | 广告拦截 |
| security_policy.rs | `core/rust-policy-core/src/security_policy.rs` | 安全策略 |
| https_only.rs | `core/rust-policy-core/src/https_only.rs` | HTTPS-only 模式 |
| bridge_guard.rs | `core/rust-policy-core/src/bridge_guard.rs` | Bridge 安全守卫 |
| capability.rs | `core/rust-policy-core/src/capability.rs` | 能力模型 |
| session_state.rs | `core/rust-policy-core/src/session_state.rs` | 会话状态管理 |
| origin.rs | `core/rust-policy-core/src/origin.rs` | URL/Origin 规范化 |
| action_policy.rs | `core/rust-policy-core/src/action_policy.rs` | 行动策略 |
| update_manifest.rs | `core/rust-policy-core/src/update_manifest.rs` | 更新清单 |
| lib.rs | `core/rust-policy-core/src/lib.rs` | 管线组合 + 模块导出 |

### 1.2 Android 端（17 个 Kotlin 文件）

| 文件 | 路径 | 职责 |
|------|------|------|
| SecureWebViewFactory.kt | `android/app/src/main/java/com/aegis/browser/` | 安全 WebView 工厂（9 阶段 JS 注入） |
| BrowserViewModel.kt | `android/app/src/main/java/com/aegis/browser/` | 浏览器状态管理（StateFlow） |
| MainActivity.kt | `android/app/src/main/java/com/aegis/browser/` | 主界面 |
| BrowserEngine.kt | `android/app/src/main/java/com/aegis/browser/` | 浏览器引擎 |
| TabManager.kt | `android/app/src/main/java/com/aegis/browser/` | 标签管理 |
| Tab.kt | `android/app/src/main/java/com/aegis/browser/` | 标签数据模型 |
| AndroidBroker.kt | `android/broker/src/main/kotlin/com/aegis/broker/` | 导航决策引擎 |
| Decision.kt | `android/broker/src/main/kotlin/com/aegis/broker/` | 类型化安全决策 |
| AuthorizedAction.kt | `android/broker/src/main/kotlin/com/aegis/broker/` | 授权行动凭据 |
| OriginPolicy.kt | `android/broker/src/main/kotlin/com/aegis/broker/` | Origin 策略 |
| AegisWebViewClient.kt | `android/webview-adapter/src/main/kotlin/com/aegis/webviewadapter/` | WebViewClient 封装 |

### 1.3 Windows 端（28 个 Python 文件）

| 文件 | 路径 | 职责 |
|------|------|------|
| fingerprint_pipeline.py | `legacy/windows-pywebview/app/` | 9 阶段指纹防护管道 JS 生成 |
| bridge_hooks.py | `legacy/windows-pywebview/app/` | 页面加载回调（JS 注入） |
| api_bridge.py | `legacy/windows-pywebview/app/` | API 桥接 |
| browser.py | `legacy/windows-pywebview/app/` | 浏览器核心 |
| config.py | `legacy/windows-pywebview/app/` | 配置管理 |
| nav_queue.py | `legacy/windows-pywebview/app/` | 导航队列 |
| shell_toolbar.py | `legacy/windows-pywebview/app/` | 工具栏 UI |
| mcp.py | `legacy/windows-pywebview/app/` | MCP 工具 |

### 1.4 C# 端（25 个文件）

| 路径 | 职责 |
|------|------|
| `windows/src/` | Windows 原生 UI（WPF/WebView2） |

---

## 二、构建产物与校验

### 2.1 Windows 安装包

| 项目 | 值 |
|------|-----|
| 文件 | `docs/release/installer_output/AegisBrowser-Setup-2.1.6.exe` |
| 大小 | 18 MB |
| SHA-256 | `e213f4c9fd6f018aefb4ad3fee6571dabd105c72e773bbee0d64b2f603309b3a` |
| 构建工具 | Inno Setup 6 |
| 脚本 | `docs/release/AegisSetup.iss` |

### 2.2 Android APK

| 项目 | 值 |
|------|-----|
| 文件 | `android/app/build/outputs/apk/debug/app-debug.apk` |
| 大小 | 38 MB |
| SHA-256 | `0ba5e35476c674d065f330e7b69ea4404d59ac3d0920dd5ff5a7bc8bc710735c` |
| 构建工具 | Gradle 9.7.0 + AGP 9.x |
| 签名 | debug 签名（测试用） |

### 2.3 项目源码包

| 项目 | 值 |
|------|-----|
| 文件 | `aegis-源码+资料包.zip` |
| 大小 | 33.7 MB（183 个文件） |
| SHA-256 | `8f67d5ea2abab972a4fce41c7830d1315d899631fcfce7d575c5d7fdf10835b8` |
| 内容 | 全部源码 + 安装包 + APK + 文档 + workflow |

### 2.4 校验方法

```powershell
# Windows PowerShell
Get-FileHash -Algorithm SHA256 AegisBrowser-Setup-2.1.6.exe
Get-FileHash -Algorithm SHA256 app-debug.apk
```

```bash
# Linux/macOS
sha256sum AegisBrowser-Setup-2.1.6.exe
sha256sum app-debug.apk
```

---

## 三、安全测试指南

### 3.1 指纹防护测试（9 阶段管道）

| 阶段 | 测试项 | 测试方法 | 预期结果 |
|------|--------|---------|---------|
| Stage 1 | ToStringGuard | `console.log(canvas.toDataURL.toString())` | 返回原始函数源码（非代理） |
| Stage 2 | PerSiteSeed | 在不同域名检查 `__AEGIS_SITE_SEED` | 同域名一致，不同域名不同 |
| Stage 3 | Canvas 噪声 | 访问 browserleaks.com/canvas | 每次刷新 canvas hash 不同 |
| Stage 3 | WebGL 伪装 | 访问 browserleaks.com/webgl | vendor/renderer 返回 Aegis |
| Stage 4 | Letterboxing | 访问 browserleaks.com/screen | 尺寸圆整到 200×100 倍数 |
| Stage 5 | QueryStripper | 访问 `https://example.com/?fbclid=test` | URL 参数被剥离 |
| Stage 6 | FontNormalizer | 访问 browserleaks.com/fonts | 仅显示安全字体（16 个） |
| Stage 7 | WebGLSpoof | 访问 amiunique.org | GPU 参数返回 Intel UHD 620 |
| Stage 8 | TimerPrecision | `performance.now()` 精度测试 | 精度降低到 1ms |
| Stage 9 | ExtProxy | 检查 Chrome Web Store 请求 | 请求被拦截（console.warn） |

### 3.2 指纹测试网站

| 网站 | 测试项 | URL |
|------|--------|-----|
| BrowserLeaks | 综合指纹 | https://browserleaks.com |
| AmIUnique | 唯一性检测 | https://amiunique.org |
| Cover Your Tracks | EFF 指纹测试 | https://coveryourtracks.eff.org |
| CreepJS | 高级指纹检测 | https://abrahamjuliot.github.io/creepjs/ |
| Pixelscan | 指纹扫描 | https://pixelscan.net |
| FingerprintJS | 商业指纹库 | https://fingerprintjs.com/demo |

### 3.3 安全策略测试

| 测试项 | 测试方法 | 预期结果 |
|--------|---------|---------|
| HTTPS-only | 访问 HTTP 网站 | 自动升级到 HTTPS |
| Safe Browsing | 访问已知恶意网站 | 显示安全警告 |
| 广告拦截 | 访问含广告网站 | 广告被拦截 |
| Bridge 安全 | 测试跨域 bridge 调用 | 未授权域名被拒绝 |

### 3.4 导航决策测试

| 测试项 | 测试方法 | 预期结果 |
|--------|---------|---------|
| Broker 决策 | 导航到恶意 URL | Decision.Deny（默认拒绝） |
| 策略版本 | 检查策略版本一致性 | 版本不匹配时拒绝 |
| Nonce 重放 | 重放旧 nonce | 拒绝（一次性） |

---

## 四、源代码获取方式

### 4.1 本地路径

| 资源 | 路径 |
|------|------|
| 项目根目录 | `D:/abrowser/review/aegis_dual_platform/` |
| Rust 核心 | `D:/abrowser/review/aegis_dual_platform/core/rust-policy-core/src/` |
| Android 源码 | `D:/abrowser/review/aegis_dual_platform/android/` |
| Windows 源码 | `D:/abrowser/review/aegis_dual_platform/legacy/windows-pywebview/` |
| C# 源码 | `D:/abrowser/review/aegis_dual_platform/windows/src/` |
| CI/CD | `D:/abrowser/review/aegis_dual_platform/.github/workflows/` |
| 文档 | `D:/abrowser/review/aegis_dual_platform/docs/` |
| 合约/向量 | `D:/abrowser/review/aegis_dual_platform/contracts/` |

### 4.2 GitHub 远端

| 项目 | URL |
|------|-----|
| 仓库 | https://github.com/bear20252026/aegis-dual-platform |
| 最新提交 | `a43dbb3`（CommandBar） |
| 标签 | v1.0.0 |

### 4.3 安装包获取

| 文件 | 获取方式 |
|------|---------|
| Windows 安装包 | `D:/abrowser/review/aegis_dual_platform/docs/release/installer_output/AegisBrowser-Setup-2.1.6.exe` |
| Android APK | `D:/abrowser/review/aegis_dual_platform/android/app/build/outputs/apk/debug/app-debug.apk` |
| 源码包 | `D:/abrowser/review/aegis_dual_platform/aegis-源码+资料包.zip` |

---

## 五、构建环境

| 项目 | 版本 |
|------|------|
| Rust | stable（rustup） |
| JDK | Eclipse Adoptium JDK 21.0.12.8 |
| Gradle | 9.7.0 |
| AGP | 9.x |
| Python | 3.12 |
| Inno Setup | 6 |
| Android SDK | API 36 |
| Node.js | 24（CI） |

---

## 六、安全测试报告模板

```markdown
# Aegis 安全测试报告

## 测试信息
- 测试人员：
- 测试日期：
- 测试版本：2.1.6
- 构建哈希：见上方 SHA-256

## 测试结果

### 指纹防护
| 阶段 | 结果 | 备注 |
|------|------|------|
| Stage 1: ToStringGuard | ✅/❌ | |
| Stage 2: PerSiteSeed | ✅/❌ | |
| Stage 3: Canvas 噪声 | ✅/❌ | |
| Stage 3: WebGL 伪装 | ✅/❌ | |
| Stage 4: Letterboxing | ✅/❌ | |
| Stage 5: QueryStripper | ✅/❌ | |
| Stage 6: FontNormalizer | ✅/❌ | |
| Stage 7: WebGLSpoof | ✅/❌ | |
| Stage 8: TimerPrecision | ✅/❌ | |
| Stage 9: ExtProxy | ✅/❌ | |

### 安全策略
| 测试项 | 结果 | 备注 |
|--------|------|------|
| HTTPS-only | ✅/❌ | |
| Safe Browsing | ✅/❌ | |
| 广告拦截 | ✅/❌ | |
| Bridge 安全 | ✅/❌ | |

### 发现的问题
| 编号 | 严重程度 | 描述 | 复现步骤 |
|------|---------|------|---------|
| 1 | | | |

## 结论
```
