# Aegis 架构审计报告

> 审计时间：2026-08-22
> 审计范围：文件行数、模块化、功能杂糅、专家要求（INV-01~05）、2026 行业对标

---

## 一、文件行数审计

### 1.1 统计总览

| 语言 | 文件数 | 总行数 | 最大行数 | 超 500 行 |
|------|--------|--------|----------|-----------|
| Rust (.rs) | 28 | 5,001 | 340 | **0** ✅ |
| Kotlin (.kt) | 17 | 1,505 | 252 | **0** ✅ |
| C# (.cs) | 15 | 744 | 185 | **0** ✅ |
| Python (.py) 活跃 | 28 | 4,794 | 724 | **2** ❌ |
| Python (.py) legacy | 8 | — | 1,859 | 8（归档） |

### 1.2 Rust policy-core 文件行数排名

| 行数 | 文件 | 职责 |
|------|------|------|
| 340 | command_bar.rs | 统一命令搜索面板 |
| 312 | space_routing.rs | URL 到工作区路由 |
| 269 | broker.rs | 导航决策引擎 |
| 268 | protection_mode.rs | 三种保护模式 |
| 257 | query_strip.rs | 追踪参数剥离 |
| 228 | matcher.rs | URL/域名匹配器 |
| 207 | ext_proxy.rs | 匿名扩展代理 |
| 199 | oracle.rs | 策略评估 |
| 196 | capability.rs | 能力模型 |
| 188 | adblock.rs | 广告拦截 |

**结论：Rust 全部 28 个模块均 ≤340 行，远低于 500 行上限。✅**

### 1.3 超过 500 行的文件（活跃代码）

| 行数 | 文件 | 问题 |
|------|------|------|
| **724** | `legacy/windows-pywebview/app/api_bridge.py` | ❌ 超标——API 桥接职责过多 |
| **724** | `legacy/windows-pywebview/main_webview.py` | ❌ 超标——主入口 + 窗口管理杂糅 |

### 1.4 legacy/ 归档文件（不计入活跃代码）

| 行数 | 文件 | 状态 |
|------|------|------|
| 1,859 | legacy/ui/main_window.py | 归档（已隔离） |
| 714 | legacy/ui/tab_strip.py | 归档 |
| 650 | legacy/ui/theme.py | 归档 |
| 579 | legacy/ui/browser_tab.py | 归档 |
| 519 | legacy/ui/ai_assistant.py | 归档 |
| 506 | legacy/ui/settings_dialog.py | 归档 |

---

## 二、模块化审计

### 2.1 单文件单职责检查

| 层 | 模块数 | 单职责 | 功能杂糅 | 评价 |
|----|--------|--------|----------|------|
| Rust policy-core | 28 | 28 ✅ | 0 | **优秀**——每模块一个清晰职责 |
| Android broker | 4 | 4 ✅ | 0 | **优秀**——Broker/Decision/Action/OriginPolicy 分离 |
| Android webview-adapter | 1 | 1 ✅ | 0 | **良好**——仅 AegisWebViewClient |
| Android app | 12 | 12 ✅ | 0 | **优秀**——ViewModel/Engine/TabManager/UI 分离 |
| Windows app (活跃) | 28 | 26 ✅ | 2 ❌ | **需改进**——api_bridge + main_webview 超标 |
| C# windows/src | 15 | 15 ✅ | 0 | **优秀**——Broker/Chrome/WebView/Diagnostics 分离 |

### 2.2 一组文件对应一类功能

| 功能类别 | 文件组 | 评价 |
|----------|--------|------|
| 指纹防护 | shield.rs, letterbox.rs, per_site_seed.rs, query_strip.rs, font_norm.rs, webgl_spoof.rs, timer_prec.rs, tostring_guard.rs, ext_proxy.rs, protection_mode.rs | ✅ 10 个独立模块 |
| 安全策略 | broker.rs, decision.rs, executor.rs, policy.rs, oracle.rs, matcher.rs, security_policy.rs, action_policy.rs, capability.rs | ✅ 9 个独立模块 |
| UI/UX | command_bar.rs, space_routing.rs, session_state.rs | ✅ 3 个独立模块 |
| 广告拦截 | adblock.rs | ✅ 独立模块 |
| HTTPS/安全 | https_only.rs, bridge_guard.rs | ✅ 2 个独立模块 |
| 更新 | update_manifest.rs | ✅ 独立模块 |

**结论：功能分组清晰，无杂糅。✅**

### 2.3 功能杂糅问题

| 文件 | 杂糅内容 | 严重程度 |
|------|---------|----------|
| `api_bridge.py` (724 行) | API 桥接 + 标签管理 + 配置读取 + 搜索引擎 + JS 注入 | ⚠️ 中 |
| `main_webview.py` (724 行) | 主入口 + 窗口创建 + 事件绑定 + 烟雾测试 + 配置加载 | ⚠️ 中 |

---

## 三、专家要求对照检查（INV-01~05）

### INV-01：远程零原生能力

> "远程内容不能获得任何原生能力——所有原生能力由 Executor 执行"

| 检查项 | 状态 | 说明 |
|--------|------|------|
| WebView JS 沙箱隔离 | ✅ | Android WebView / Windows pywebview 均在沙箱中运行 |
| Bridge 白名单 | ✅ | `bridge_guard.rs` + `AegisWebViewClient` 拦截未授权调用 |
| 远程内容无法直接调用原生 API | ✅ | 所有原生调用经 Broker→Decision→Executor 链路 |

**达标：✅**

### INV-02：Executor 唯一副作用点

> "所有副作用（导航/下载/导出/改策略）只能通过 Executor 执行"

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 导航副作用 | ✅ | `executor.rs` 控制所有导航 |
| 下载副作用 | ✅ | Android `BrowserEngine` 无 `setDownloadListener`（已移除） |
| 策略修改 | ✅ | 仅通过 Executor |
| 无绕过路径 | ✅ | `BrowserEngine` 无导航/下载副作用 |

**达标：✅**

### INV-03：Broker 唯一授权点

> "所有安全决策只能通过 Broker 授权"

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 导航决策 | ✅ | `AndroidBroker.evaluateNavigation()` + `BrowserPolicyBroker` |
| 类型化决策 | ✅ | `Decision.Allow/Deny/RequireConfirmation` |
| DenyOverrides 模式 | ✅ | deny > ask > allow 最严格优先 |
| fail-closed 默认拒绝 | ✅ | 无匹配规则时返回 `Decision.Deny` |

**达标：✅**

### INV-04：BrowserSessionState 唯一 UI 状态来源

> "所有 UI 状态只能从 BrowserSessionState 获取"

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Android StateFlow | ✅ | `BrowserViewModel` 通过 StateFlow 管理所有 UI 状态 |
| 无 remember 局部状态 | ✅ | `MainActivity` 已移除所有 `remember { mutableStateOf }` |
| TabManager → ViewModel | ✅ | `TabManager` 状态通过 `refresh()` 同步到 ViewModel |

**达标：✅**

### INV-05：每发布制品独立可追溯

> "每平台独立 build→sign→SBOM→provenance→verify→publish"

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Windows 独立交付链 | ✅ | `release-windows.yml` |
| Android 独立交付链 | ✅ | `release-android.yml` |
| Rust Core 独立交付链 | ✅ | `release-core.yml` |
| 编排器 | ✅ | `release.yml` 触发三平台→verify-gate→publish |
| SLSA provenance | ✅ | 每平台独立 attest |
| SBOM | ✅ | 每平台独立 CycloneDX |
| SHA-256 对账 | ✅ | 字节一致不变量 |

**达标：✅**

### 单路径数据流检查

> 唯一数据流：`Adapter→Broker→Decision→Executor→BrowserEvent→BrowserSessionState→ChromeUI`

| 环节 | 实现 | 状态 |
|------|------|------|
| Adapter | `AegisWebViewClient` / `api_bridge.py` | ✅ |
| Broker | `AndroidBroker` / `BrowserPolicyBroker` | ✅ |
| Decision | `Decision.Allow/Deny/RequireConfirmation` | ✅ |
| Executor | `executor.rs` | ✅ |
| BrowserEvent | WebView 回调 | ✅ |
| BrowserSessionState | `BrowserViewModel` / StateFlow | ✅ |
| ChromeUI | Compose UI / pywebview UI | ✅ |

**单路径完整：✅**

---

## 四、2026 行业对标

### 4.1 指纹防护架构对比

| 浏览器 | 架构层级 | 种子机制 | 一致性 | Aegis 状态 |
|--------|---------|----------|--------|-----------|
| **Clearcote** | C++ 内核级 | 单种子 + 域名 → 一致人格 | 所有信号描述同一台机器 | ⚠️ Aegis 用 JS 注入 |
| **AdsPower** | C++ 内核级 | 编译时修改 | 内核级一致性 | ⚠️ Aegis 用 JS 注入 |
| **Brave** | C++ 内核级 | per-session + per-site + per-storage | 随机化 + 归一化混合 | ✅ Aegis 有 per-site 种子 |
| **Mullvad** | Firefox 级 | RFP 归一化 | 所有用户相同 | ✅ Aegis 有 Letterboxing |
| **Aegis** | **JS 注入级** | session seed + per-site seed | 9 阶段管道 | ⚠️ 架构层级最低 |

### 4.2 关键差距分析

| 维度 | 2026 行业标准 | Aegis 现状 | 差距 |
|------|-------------|-----------|------|
| **指纹防护层级** | C++ 内核级（Clearcote/AdsPower） | JS 注入级 | **大**——JS 注入可被检测 |
| **一致人格** | 单种子派生所有信号（Clearcote） | per-site 种子 + 独立噪声 | **中**——信号间可能不一致 |
| **模块化** | 单文件 ≤500 行 | Rust ✅ / Python ❌ | **小**——仅 2 个 Python 文件超标 |
| **管道化** | 独立可组合阶段 | 9 阶段管道 ✅ | **无**——已达行业水平 |
| **INV 合规** | 5 项不变量 | 全部达标 ✅ | **无** |
| **交付链** | 独立可追溯 | 三平台独立 + 编排器 ✅ | **无** |

### 4.3 与热门浏览器的差距排名

```
内核级（最强）
├── Clearcote（C++ 修改 + 一致人格 + 单种子）
├── AdsPower（C++ 修改 + 编译时指纹）
├── Brave（C++ 修改 + per-site 随机化）
├── Mullvad（Firefox RFP + 归一化）
│
引擎级（中等）
├── Helium（ungoogled-chromium 补丁）
├── LibreWolf（Firefox 配置级）
│
JS 注入级（Aegis 当前）
├── Aegis（9 阶段管道 + per-site 种子）
├── playwright-afp（JS 注入库）
└── fingerprint-toolkit（JS 注入库）
```

---

## 五、总结与改进建议

### 5.1 达标项（✅）

| 项目 | 状态 |
|------|------|
| INV-01 远程零原生能力 | ✅ |
| INV-02 Executor 唯一副作用点 | ✅ |
| INV-03 Broker 唯一授权点 | ✅ |
| INV-04 BrowserSessionState 唯一 UI 状态来源 | ✅ |
| INV-05 每发布制品独立可追溯 | ✅ |
| 单路径数据流 | ✅ |
| Rust 模块化（≤500 行） | ✅ |
| Android 模块化（≤500 行） | ✅ |
| C# 模块化（≤500 行） | ✅ |
| 管道化 9 阶段 | ✅ |
| 版权声明保留 | ✅ |

### 5.2 需改进项（⚠️）

| 项目 | 问题 | 建议 |
|------|------|------|
| `api_bridge.py` 724 行 | 超标——职责过多 | 拆分为 api_bridge.py + tab_ops.py + config_ops.py |
| `main_webview.py` 724 行 | 超标——入口 + 窗口管理杂糅 | 拆分为 main_webview.py + window_setup.py |
| JS 注入级指纹防护 | 2026 行业已转向内核级 | 长期目标：迁移到 Tauri/pytauri（Rust 内核级控制） |
| 信号一致性 | 各指纹信号独立随机化 | 参考 Clearcote 的"一致人格"模式 |

### 5.3 优先级排序

| 优先级 | 改进项 | 复杂度 | 收益 |
|--------|--------|--------|------|
| P0 | 拆分 api_bridge.py / main_webview.py | 低 | 满足 ≤500 行要求 |
| P1 | 信号一致性增强（一致人格模式） | 中 | 提升反指纹强度 |
| P2 | 迁移到 Tauri/pytauri（内核级） | 高 | 达到 2026 行业标准 |

---

## 六、结论

**Aegis 当前架构整体达标**：
- ✅ 专家 5 项不变量（INV-01~05）全部满足
- ✅ 单路径数据流完整
- ✅ Rust/Android/C# 模块化优秀（全部 ≤340 行）
- ✅ 管道化 9 阶段独立可组合
- ✅ 三平台独立交付链

**主要差距**：
- ⚠️ 2 个 Python 文件超 500 行（需拆分）
- ⚠️ JS 注入级指纹防护（2026 行业已转向内核级）
- ⚠️ 信号间一致性不足（参考 Clearcote 一致人格模式）

**总体评价**：在 INV 合规和模块化方面，Aegis 达到了专家要求。在指纹防护架构层级方面，与 2026 年顶级浏览器（Clearcote/AdsPower/Brave）有差距，但已达到 JS 注入级的最佳实践水平。
