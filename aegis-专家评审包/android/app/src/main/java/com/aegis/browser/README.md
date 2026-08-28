# com.aegis.browser — Aegis Android 端组件（单文件单职责）

> 本包是 Aegis Android 端（Kotlin + Compose + System WebView）的全部组件。
> 结构审计约束：单文件单职责、≤500 行。入口为 `MainActivity`（薄壳），
> 业务逻辑在 `TabManager`，UI 在 `TabBar`/`VerticalTabBar`。

## 组件清单

### 入口与状态管理
| 组件 | 职责 |
|---|---|
| `MainActivity.kt` | 薄壳：组装 TabBar/地址栏/WebContentArea；`onDestroy` 统一释放 WebView |
| `TabManager.kt` | 多标签状态：增删/切换/挂起恢复（活跃上限 8 + LRU 挂起）、游标分页无关 |
| `Tab.kt` | 标签数据模型（id/title/url/webView/suspended/pinned/group/lastUsed） |

### UI 层（Compose，纯展示回调上抛）
| 组件 | 职责 |
|---|---|
| `TabBar.kt` | 顶部横向标签条（LazyRow + TabChip） |
| `VerticalTabBar.kt` | 左侧垂直标签栏（LazyColumn 按分组=工作区渲染，落地 B） |
| `AegisTheme.kt` | MaterialTheme 统一字体族（Inter + Source Han Sans SC，苹果风格） |
| `UiColors.kt` | UI 颜色常量表（玻璃风格配色，detekt 基线收敛后命名化） |

### 安全与 WebView
| 组件 | 职责 |
|---|---|
| `SecureWebViewFactory.kt` | 统一创建 + 安全配置 WebView（禁 file/混合内容/调试，复用 BrowserEngine 边界） |
| `BrowserEngine.kt` | 安全导航（URL 白名单 http/https）+ 设置收紧 |
| `DownloadPolicy.kt` | 下载策略（允许的 URL scheme 判定） |

## 运行关系

```
MainActivity（薄壳）
  ├─ TabManager（状态）── Tab（数据）
  ├─ TabBar / VerticalTabBar（UI，回调上抛 switchTo/closeTab/addTab）
  ├─ SecureWebViewFactory（安全创建）── BrowserEngine（URL 白名单加载）
  └─ AegisTheme / UiColors（主题与配色）
```

## 安全要点

- 所有 WebView 经 `SecureWebViewFactory` 创建（禁 file 访问/混合内容/WebView 调试）
- 导航经 `BrowserEngine.normalize`（http/https 白名单）
- 与 Windows 端共享安全模型（统一安全关口理念）

## 验证入口

- `./gradlew.bat :app:assembleDebug` / `lintDebug` / `ktlintCheck` / `detekt`
- 完整类型检查需 Android Studio（命令行仅语法级验证）
