# Aegis 技术演进开发文档（tech-evolution-plan）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> 依据：中英双语联网调研（2025.01 – 2026.08.15，覆盖微软官方/社区/国内外权威站）
> 范围：WebView2 与 pywebview 生态深化 + 2026 桌面新趋势评估

---

## 〇、总览：四条方向与已落地基础

| 方向 | 主题 | 已落地基础（本仓库） | 本文档深化内容 |
|---|---|---|---|
| ① 安全 | WebView2 最新安全特性 | ESM 三模式开关（auto/on/off）+ 启动探测 + 崩溃监听 | ESM per-origin 细化 + 官方安全清单逐项落地 |
| ② 通信 | pywebview 桥性能 | DNT 注入 + 联想开关 + js_api 白名单 | pywebviewready 时序 + 大数据传输（分页/流式/压缩） |
| ③ 趋势 | 2026 桌面新框架 | —（评估阶段） | Deno Desktop / Bunlet / Electrobun 对比与接入决策 |
| ④ 性能 | WebView2 最佳实践 | 性能基线监控（内存/GPU/标签数）+ LRU 多标签 | 启动预热 + 内存释放 + host 对象瘦身 |

---

## 方向 ①：WebView2 最新安全特性深化

### 1.1 官方安全清单逐项落地（微软《Develop secure WebView2 apps》）

| # | 官方要求 | Aegis 现状 | 落地动作 |
|---|---|---|---|
| S1 | **发送信息进 WebView2 前检查 `Source` 来源**（ExecuteScript/PostWebMessage） | js_api 全部走白名单；未校验来源 | 在 `bridge_hooks.on_loaded` 与联想导航处记录 `window.get_current_url()` 并校验白名单（http/https）后才注入 |
| S2 | **用 `PostWebMessageAsJson`（JSON 库构造）**，禁字符串拼接 | 注入用 `json.dumps`（已符合） | ✅ 保持；补充单测断言"注入输出恒为合法 JSON 字面量" |
| S3 | **验证 web 消息与 host 参数**（可畸形/恶意） | js_api 参数有类型校验（部分） | 为 `navigate/switch_tab/close_tab` 等**全部** js_api 入口补参数类型/范围校验（统一 `_validate_args` 助手） |
| S4 | **限制功能**：`AreHostObjectsAllowed=false`、`IsWebMessageEnabled=false`、`IsScriptEnabled=false`、`AreDefaultScriptDialogsEnabled=false` | pywebview 默认暴露 host objects | 启动时经 `CoreWebView2.Settings` 探测并设 false（`hasattr` 兜底静默）——Aegis 前端不需要 host object 直接访问 |
| S5 | **避免通用代理**、按来源调整设置（`NavigationStarting` 检查） | 无 | `NavigationStarting` 事件挂钩：按目标 URL 来源决定是否收紧（配合 ESM 例外） |
| S6 | `ContentLoading` 时 `RemoveHostObjectFromScript` | 未暴露 host objects | ✅ 天然满足（Aegis 不 AddHostObject）；记录为设计声明 |

**实施文件**：`main_webview.py`（新增 `_apply_webview2_settings`，与 `_apply_enhanced_security` 同模式：探测+静默降级）、`api_bridge.py`（参数校验助手）。

### 1.2 ESM per-origin 细化（Origin Configuration API）

调研结论（微软 `specs/TrustedOriginSetting.md`）：
- 接口：`ICoreWebView2Profile3` → `CreateOriginFeatureSetting` / `SetOriginFeatures` / `GetEffectiveFeaturesForOrigin`
- 特性枚举：`EnhancedSecurityMode`（当前支持两值：AccentColor、EnhancedSecurityMode）
- 用法示例：对 `https://*.contoso.com` 设置 `EnhancedSecurityMode` Enabled/Disabled

Aegis 落地（复用已建 `config.security_esm_exceptions`）：
```
config.security_esm_exceptions = '["https://oa.internal.gov.cn"]'
→ 启动时解析 JSON 数组 → 探测 ICoreWebView2Profile3（staging API，hasattr 兜底）
→ 对例外源 SetOriginFeatures(EnhancedSecurityMode, Disabled)
→ 其余源保持 profile 级 Enabled（方向① 已落地）
```
**注意**：该 API 仍为实验/staging，未转 stable 前全部 `hasattr` 探测 + 失败静默；`GetEffectiveFeaturesForOrigin` 可作自检（probe 报告扩展字段）。

---

## 方向 ②：pywebview 通信与性能优化

### 2.1 pywebviewready 时序（调研：官方 2026-04 文档 + issue #1290/#1629）

调研结论：
- `window.pywebview.api` **不保证在 `window.onload` 可用**——必须订阅 `pywebviewready`（js_api 完全注入后触发）
- `window.events.initialized`（GUI 选定后，阻塞）/ `window.events.loaded`（DOM ready）语义不同
- 已知坑：React/Vite 等框架中 `pywebviewready` 可能在业务代码附加监听前已触发 → 需在**入口脚本最早处**订阅

Aegis 落地（`shell_toolbar.py` TOOLBAR_JS）：
- 当前注入是 `on_loaded`（events.loaded）后 evaluate——**改为双保险**：
  ```
  var pvReady = false;
  window.addEventListener('pywebviewready', function(){ pvReady = true; bootUI(); });
  if (window.pywebview && window.pywebview.api) { pvReady = true; bootUI(); }  // 兜底
  function bootUI() { /* 现有工具栏/联想/快捷键初始化 */ }
  ```
- 消除 `setTimeout` 猜测性延迟（如联想防抖外的初始化等待）

### 2.2 大数据传输优化（调研：官方 base64 膨胀 ~33% + HTTP 中转方案）

调研结论：JSON+base64 传输 >10MB 明显延迟、内存激增；**本地 HTTP 服务中转**（aiohttp/Flask + fetch/ArrayBuffer）支持二进制直传、chunked 流式、gzip/Brotli 压缩。

Aegis 落地（按需，分阶段）：
| 阶段 | 场景 | 方案 |
|---|---|---|
| P1 | 书签/历史列表（万级） | **游标分页**（`fulltext_search`/`get_history` 加 `cursor_id` 参数，避免深分页全表扫描）；前端虚拟滚动 |
| P2 | 全文搜索联想（当前 8 条） | ✅ 已够用（小数据）；保持 |
| P3 | 导入向导大文件（Chrome 书签/历史） | 本地 HTTP 端点 + fetch 流式读取（复用 browser_import 解析，加 gzip）——**按需启用，先留接口** |
| P4 | 压缩 | 文本数据启用 Brotli（现代浏览器）> Gzip 20% |

**实施文件**：`api_bridge.py`（分页参数）、`webview2_probe.py`（传输性能基线字段）、`browser_import.py`（流式接口预留）。

---

## 方向 ③：2026 桌面新框架评估（Deno Desktop / Bunlet / Electrobun）

### 3.1 调研事实（2026-06/07 发布）

| 框架 | 发布 | 后端 | 体积 | 成熟度 | 关键点 |
|---|---|---|---|---|---|
| **Deno Desktop** | Deno 2.9（2026-06-25） | `webview`（默认，系统 WebView2）/`cef`（捆绑 Chromium 308.9MB） | webview 实测 macOS ~68.5MB | **未稳定**（macOS 关闭按钮 bug；框架兼容摩擦） | `deno desktop` 子命令 + `Deno.BrowserWindow`/bindings；框架自动检测（Next/Astro/Fresh 等） |
| **Bunlet** | v0.3.0（2026） | 系统 WebView（tao/wry + Rust NAPI） | 20-40MB（vs Electron 80-150MB） | 早期 | Electron 兼容 API；TypeScript 优先；CLI create/dev/build/package |
| **Electrobun** | 2026 | Bun + 系统 webview（CEF 可选） | 极小 | 早期 | 原生绑定 + GPU surface 嵌入 |
| **Keld / Bunv** | 2026 | Bun + webview | 5-60MB | 早期 | Electron 迁移工具链（keld migrate） |

### 3.2 Aegis 评估结论（国家项目视角）

- **共同优势**：系统 WebView 路线 = 与 Aegis 现有架构同源（都是 WebView2 壳），体积/内存优势明显
- **共同风险**：全部处于早期/未稳定；跨平台渲染一致性依赖宿主 WebView 版本（政府内网老系统风险）；生态/文档未成熟
- **结论**：**现阶段不迁移**。理由：
  1. Aegis 已投入 Python+pywebview 栈并完成安全纵深（白名单/NavQueue/审计），迁移成本高
  2. 新框架未稳定（官方自认），国家项目不宜追逐未稳技术
  3. 保持"持续跟踪"：**每季度复核** Deno Desktop stable / Bunlet 1.0 里程碑，条件满足（稳定 + 政府内网渲染一致性方案）再评估 PoC
- **可即时借鉴**（零迁移成本）：Bunlet/Keld 的 **IPC 数据校验**（Zod schema-first）与 **默认拒绝权限**理念 → 已落地为 js_api 参数校验（`_to_int/_to_nonneg_int/_to_str` 助手，方向①-S3）

### 3.3 季度复核记录（2026-Q3 首期，2026-08-15）

| 框架 | 本期状态（2026-08-15） | 复核结论 |
|---|---|---|
| **Deno Desktop** | Deno 2.9（2026-06-25）发布 `deno desktop`；webview 后端实测 macOS ~68.5MB / CEF ~308.9MB；三后端（webview/cef/raw）；框架自动检测（Next/Astro/Fresh 等）；`Deno.BrowserWindow`+bindings；**官方未标 stable**（macOS 关闭按钮 bug、框架兼容摩擦，The Register 2026-06-24） | 🔴 不迁移（未稳定）；下次复核：Deno 3.x stable 或 `deno desktop` 转 stable 公告 |
| **Bunlet** | v0.3.0（2026）；Bun + tao/wry + Rust NAPI；安装包 20-40MB（vs Electron 80-150MB）；Electron 兼容 API；CLI create/dev/build/package；Windows 需 WebView2（Win11 自带） | 🔴 不迁移（早期）；下次复核：v1.0 里程碑 |
| **Electrobun / Keld / Bunv** | 2026 活跃（Electrobun 原生绑定+GPU surface；Keld `migrate` 迁移工具链；Bunv 5-60MB） | 🔴 观察；下次复核：随 Deno/Bunlet 一并评估 |
| **可借鉴点（已落地）** | IPC 参数校验（schema-first）→ `_to_int` 等助手；默认拒绝权限 → js_api 白名单 + WebView2 Settings 收紧 | ✅ 本季度已吸收 |

**复核机制**：每季度（Q3：2026-09-30 前）更新本表；触发条件 = 任一框架转 stable 或发布 1.0；复核产出 = 更新本记录 + 若条件满足启动 PoC 评估（成本/安全/渲染一致性三项）。

### 3.4 季度复核执行记录（2026-Q3 中期，2026-08-15）

| 框架 | 本次复核发现（2026-08-15 复核） | 结论（维持/调整） |
|---|---|---|
| **Deno Desktop** | Deno **8.06**（2026-08 发布）持续修复 desktop 模块（`fix(desktop): handle colored HMR URLs and page loads #36316`、`fix(desktop): retain update signature verification op #36152`）；**仍无 stable 公告**（desktop 处于持续修复期） | 🔴 **维持不迁移**（未稳定）；下次复核：stable 公告或 3.x 里程碑 |
| **Bunlet** | 无新版本/新报道（仍 v0.3.0 早期） | 🔴 **维持不迁移**（早期）；下次复核：v1.0 |
| **触发检查** | 无任一框架转 stable/发布 1.0 | ✅ **未触发 PoC 评估** |

**复核结论**：Q3 中期复核完成——Deno Desktop 仍在活跃修复（desktop 模块 bug 持续收敛是正面信号，但距 stable 尚远），Bunlet 无进展；Aegis 维持 Python+pywebview 栈，不迁移判断不变。下次复核：2026-09-30 前（Q3 末）。

---

## 方向 ④：WebView2 性能最佳实践落地

### 4.1 启动预热（调研：微软官方 2026-01 + issue #1629 约 4s 初始化延迟）

| 官方建议 | Aegis 落地 |
|---|---|
| **不要用 WebView2 渲染初始 UI/闪屏** | ✅ 已满足（首屏是本地 start.html 轻页，非重 UI）——文档记录 |
| **UDF 保持默认本地应用数据文件夹** | ✅ `paths.resolve_data_dir` 用本地 AppData；**检查项**：确保不指向网络共享 |
| **避免冗余 WebView2 实例** | ✅ 单 WebView + 标签数据模型（天然满足） |
| **预热环境**（调研补充：复用机制降 T_init） | 新增 `_warmup_webview2`：启动早期创建共享 Environment（与运行时同一 UDF/Options），缩短后续冷启动——**pywebview 层面为尽力而为，失败静默** |

### 4.2 内存治理（调研：官方 + TrueSight 2026-04 生产指南）

| 官方/社区建议 | Aegis 落地 |
|---|---|
| **共享 CoreWebView2Environment** | ✅ 单 WebView 天然共享；文档记录 |
| **避免大范围 host 对象**（窄对象/分页结果 + RemoveHostObjectFromScript） | ✅ Aegis 不 AddHostObjectToScript（安全设计）；`get_history/fulltext_search` 已带 limit 分页 |
| **防内存泄漏 + 定期刷新 WebView2** | 已落地 `TabManager` LRU 挂起（Android）+ 性能基线监控（内存涨幅 300MB 告警）；**补充**：长期运行每 24h 记录性能快照对比（复用 `compare_baseline`） |
| **ProcessFailed 必须处理**（否则持有失效句柄泄漏） | ✅ 已落地（log_webview2_crash + 监听） |
| **`--disk-cache-size` 限制缓存**（冷启动慢的缓存因素） | 评估：config 加 `http_cache_mb`（已有字段）→ 经 AdditionalBrowserArguments 注入 `--disk-cache-size`（pywebview 环境参数，尽力而为） |

### 4.3 性能监控闭环（衔接已落地）

```
启动 → probe_performance（内存/GPU/标签数）→ compare_baseline（阈值 300MB）
     → 显著/GPU 变化 → log_event 告警
     → 持久化基线 → 下次对比
每日/长期：定时再采样 → 对比 → 慢速泄漏趋势可见
```

---

## 实施优先级与文件映射

| 优先级 | 动作 | 文件 | 依赖 |
|---|---|---|---|
| 🔴 P0 | 方向② `_validate_args`（js_api 全量参数校验） | api_bridge.py | 无 |
| 🔴 P0 | 方向① `_apply_webview2_settings`（S4 限制功能） | main_webview.py | 无 |
| 🟡 P1 | 方向① ESM per-origin（SetOriginFeatures 探测接入） | main_webview.py / config.py | 已建 esm_exceptions 字段 |
| 🟡 P1 | 方向② pywebviewready 双保险初始化 | shell_toolbar.py | 无 |
| 🟢 P2 | 方向④ 24h 性能复采样 + `--disk-cache-size` | webview2_probe.py / main_webview.py | 已建 compare_baseline |
| 🟢 P2 | 方向② 游标分页（get_history/fulltext） | api_bridge.py / history_store.py | 无 |
| ⚪ 观察 | 方向③ Deno Desktop/Bunlet 季度复核 | docs/（评估记录） | 无 |

## 约束（贯穿全部实施）

- 单文件单职责、≤1000 行（一般 ≤500）；新增均拆独立模块或并入职责内聚文件
- 所有 WebView2 新 API 一律 `hasattr` 探测 + 失败静默（Evergreen 2 周节奏，兼容旧 Runtime）
- 不改变既有功能；验证 = 语法 + 三自检 + ruff/mypy/bandit + Android 编译
