# app/ — Aegis Windows 端业务模块（单文件单职责）

> 本目录是 Aegis Windows 端（pywebview + WebView2）的全部业务模块。
> 结构审计约束：单文件单职责、≤1000 行（一般 ≤500）。入口为
> `../main_webview.py`（薄壳），本目录只承载业务。

## 模块分层

### 桥接层（js_api 桥 / 页面回调）
| 模块 | 职责 |
|---|---|
| `api_bridge.py` | js_api 白名单桥：标签/导航/书签/历史/导入/搜索（`_JS_EXPOSED` 防递归注入死锁） |
| `bridge_hooks.py` | 页面加载完成回调：刷新标签 + 注入工具栏（独立职责，从 api_bridge 拆出） |
| `shell_toolbar.py` | 注入式工具栏（TOOLBAR_JS）：标签条/地址栏/联想/快捷键/字体栈/垂直标签 |
| `nav_queue.py` | 导航线程队列：窗口操作串行化，防 js_api 回调线程死锁 |

### 业务模块（单文件单职责）
| 模块 | 职责 |
|---|---|
| `security.py` | URL 白名单（safe_url）/ 权限收紧（DACL） |
| `threat_feed.py` | 恶意站点情报订阅（https-only + 签名校验） |
| `url_utils.py` | URL 规整与导航安全校验（纯函数，从 api_bridge 拆出） |
| `reader.py` | 阅读模式（决策/视图分离，防注入转义） |
| `mcp.py` | 轻量 MCP（JSON-RPC 2.0 工具白名单，供 AI 代理调用） |
| `fingerprint.py` | 可选指纹设备配置（默认关闭，不破坏如实 UA） |
| `browser_import.py` | Chrome/Edge 书签与历史导入解析 |
| `webview2_probe.py` | WebView2 兼容性探测 / 性能基线 / 自动化回归入口 |

### 存储层（SQLite）
| 模块 | 职责 |
|---|---|
| `database.py` | SQLite 基础设施（参数化查询） |
| `bookmark_store.py` | 书签存储（多级文件夹 + Netscape HTML 导入导出） |
| `history_store.py` | 历史存储（FTS5 全文搜索 + 游标分页） |

### 支撑层
| 模块 | 职责 |
|---|---|
| `config.py` | 全局配置（隐私/外观/字体/安全增强模式） |
| `paths.py` | 数据目录解析 |
| `backdrop.py` | Windows 11 Mica/亚克力背景（尽力而为） |
| `asset_scheme.py` | 随包资产 scheme（Qt 旧栈遗产，新栈未用） |

## 运行关系

```
main_webview.py（薄入口）
  ├─ api_bridge.Api（js_api 桥）── nav_queue（导航线程）
  ├─ bridge_hooks.on_loaded ── shell_toolbar.build_toolbar_js（注入）
  ├─ webview2_probe（探测/基线/回归）
  └─ crash_reporter（崩溃收集，../ 目录）
```

## 验证入口

- `python ../validate_release.py`（项目根）
- `python selftest_s1_integration.py` / `selftest_api_bridge.py` / `selftest_shell_toolbar.py`
- `python -m app.webview2_probe`（自动化回归：validate_release + 三自检）
