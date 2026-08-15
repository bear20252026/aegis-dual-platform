# pytauri capabilities 映射方案（pytauri-capabilities-mapping）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> 目的：模块化迁移预研（第 ④ 步前导，零风险设计先行）——把 Aegis
> `api_bridge` 的 js_api 白名单映射为 pytauri/Tauri capabilities 权限，
> 为"壳层迁移（pytauri-wheel B 路线）"预留可执行的映射蓝图。
> 约束：仅设计不碰代码；随时可逆（禁止被困原则）。

---

## 〇、映射总原则

1. **白名单即权限清单**：Aegis `_JS_EXPOSED`（js_api 白名单）= 前端可调用的 Python 命令白名单 → Tauri capabilities 的权限条目（**语义等价映射**）
2. **deny 优先**：威胁拦截（host_is_blocked）命中须优先于任何 allow（与 ACL deny 优先一致，第 1 步已复核）
3. **最小权限**：只读方法仅 core:default；写操作显式允许；敏感操作额外限制
4. **业务零改动**：api_bridge 25 文件原样复用（壳层迁移仅改桥接入口）

## 一、js_api 白名单清单（映射源，25 方法）

| 分类 | 方法（_JS_EXPOSED） | 操作类型 |
|---|---|---|
| 导航 | navigate / go_back / go_forward / reload_page / go_home / current_url | 写（导航）/ 读（current_url） |
| 标签 | get_tabs / new_tab / switch_tab / close_tab / pin_tab / unpin_tab / set_tab_group / get_tab_groups | 读（get_*）/ 写（其余） |
| 引擎 | get_search_engine / set_search_engine | 读 / 写 |
| 壁纸 | get_wallpaper / set_wallpaper | 读 / **敏感写** |
| 书签 | get_bookmarks / add_bookmark / remove_bookmark | 读 / 写 |
| 错误 | js_error | 写（只上报） |

## 二、js_api → pytauri capabilities 映射（Tauri v2 ACL）

### 2.1 权限分级

| 级别 | js_api 方法 | capabilities 权限设计 | 理由 |
|---|---|---|---|
| **L0 基础**（core:default） | get_tabs / get_search_engine / get_wallpaper / get_bookmarks / current_url / js_error | `core:default` + 只读命令允许 | 无副作用，最小权限 |
| **L1 导航/标签写** | navigate / go_back / go_forward / reload_page / new_tab / switch_tab / close_tab / pin_tab / unpin_tab / set_tab_group / get_tab_groups / add_bookmark / remove_bookmark / set_search_engine | 显式命令权限（`aegis:allow-*` 逐条） | 写操作须显式允许（Tauri 默认拒绝） |
| **L2 敏感写** | set_wallpaper | 额外限制（scope 校验：仅随包登记文件名，复用现有 WALLPAPERS 白名单） | 防任意路径/URL 注入（现 ntp_wallpaper 校验迁移） |

### 2.2 映射实现要点（pytauri-wheel 语境）

```toml
# capabilities/default.toml（迁移后形态，示意）
identifier = "default"
windows = ["main"]
permissions = [
  "core:default",            # L0 基础（窗口/事件/只读命令）
  "pytauri:default",         # pytauri 插件基础
  # L1 导航/标签写（显式允许——对应 api_bridge 写方法）
  "aegis:allow-navigate",
  "aegis:allow-new-tab",
  "aegis:allow-close-tab",
  # ...（逐条对应 _JS_EXPOSED 写方法）
  # L2 敏感写（scope 限制）
  { "identifier": "aegis:allow-set-wallpaper",
    "allow": [{ "path": "**/wallpapers/*.png" }] },  # 仅随包壁纸
]
```

### 2.3 pytauri 命令注册侧（Python 对应）

```python
# api_bridge 的 js_api 方法 → pytauri Commands 注册（迁移时形态）
# commands = Commands()
# for name in Api._JS_EXPOSED:  # 白名单即注册清单
#     commands.command(name)(getattr(api, name))
# invoke_handler=commands.generate_handler(portal)
# → capabilities 控制前端能否调用（默认拒绝，逐条 allow）
```

## 三、迁移注意事项（诚实清单）

| 注意点 | 说明 |
|---|---|
| **deny 优先保持** | 威胁拦截（host_is_blocked）在导航层（api_bridge 原样）——与 capabilities 无关，迁移后不变 |
| **js_error 上报** | L0 允许（前端错误上报无副作用），但建议仅记录不展示（安全） |
| **set_wallpaper scope** | 复用现有 WALLPAPERS 白名单（asset_scheme）——capabilities scope 与之等价映射 |
| **桥接入口** | 仅 main_webview 的桥接层改（webview.create_window + js_api → pytauri 窗口 + generate_handler）——业务 25 文件零改动 |
| **前端契约** | pywebview.api.x → window.__TAURI__.pytauri.pyInvoke('x')（Tune 案例同款，前端注入脚本改桥调用） |

## 四、结论

映射方案证明 **Aegis 的 js_api 白名单（_JS_EXPOSED）可语义等价映射为 pytauri capabilities 权限**（默认拒绝 + 逐条 allow + deny 优先 + 最小权限）——**模块化迁移的设计先行部分已完成，零风险可逆**。代码迁移仍等 PoC 三关实测门禁 + 双目标季度复核（pytauri 复苏 / pywebview 健康保持）。
