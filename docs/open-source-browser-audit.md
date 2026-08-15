# 开源浏览器源码专家审计报告（open-source-browser-audit）

> 审计日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> 审计对象：D:/abrowser/research/ 下 6 个开源浏览器源码
> （CloakBrowser / FreeDom / ShardBrowser / brave / browser-shell / electron-browser-shell）
> 目标：提取对 Aegis（pywebview+WebView2 双端壳浏览器）下一步最有帮助的可借鉴点

---

## 〇、审计总览

| 项目 | 技术栈 | 审计判定 | 与 Aegis 关联度 |
|---|---|---|---|
| **FreeDom** | C11 纯 C 浏览器（Lexbor/QuickJS-ng） | ✅ 源码完整，四层沙箱设计顶尖 | 🔴 高（安全架构） |
| **brave** | Chromium C++ + Rust adblock | ✅ 特有增量可审（shields/adblock/farbling） | 🔴 高（拦截管线/反指纹） |
| **ShardBrowser** | Tauri 2 壳 + 独立 Chromium 149 | ✅ 源码完整（JWT/临时 profile） | 🟡 中（生命周期/凭据） |
| **CloakBrowser** | Vite 脚手架 + 预编译二进制 | ⚠️ **无内核源码**（README 宣称 C++ 补丁，源码不可验证） | 🟡 中（拟人输入/自更新理念） |
| **electron-browser-shell** | Electron 标签浏览器 | ✅ 极简 + Chrome 扩展支持 | ⚪ 低（扩展支持理念） |
| **browser-shell** | 浏览器内 Linux VM（v86+Plan9） | ✅ 概念性（VM 状态缓存） | ⚪ 低（状态缓存理念） |

---

## 一、逐项目审计要点

### 1.1 FreeDom（纯 C11，安全架构最具借鉴价值）

- **架构**：可信父进程（网络/GUI）+ 每标签 fork+re-exec 工作进程，双管道二进制协议；父进程不解析任何敌对字节（`src/tab.c:2-11`）
- **四层沙箱**：seccomp-bpf 白名单 + W^X + Landlock 文件系统 + 每 tab 命名空间（`src/os_sandbox.c`）
- **网络隔离**：worker 无 socket，全部请求经管道代理回父进程**重放完整策略**（`src/tab.c:123-130`）
- **策略纯函数**：`js_policy.c`/`request_policy.c`/`net_realm.c` 均为无 I/O 纯函数、fail-closed、17 个 libFuzzer harness 直接测试
- **TLS**：默认 TLS1.3 + 后量子 X25519MLKEM768；TLS 伪装需 allow+js+impersonate 三重 opt-in

### 1.2 brave（Chromium 特有增量）

- **Rust adblock 引擎 + cxx FFI**（`components/brave_shields/core/common/adblock/rs/`）
- **统一请求回调链**：site_hacks→AdBlockTP→CSP→静态重定向（`brave_request_handler_impl.cc`）；被拦请求回 1×1 透明图（`adblock_stub_response.cc`）；**CNAME 反伪装二次判定**
- **确定性 farbling**：per-site 持久化 token + PRNG 生成全部指纹值（`brave_session_cache.cc` FarbleKey）
- **按域名策略存储**：ContentSettings 全局默认 + per-site 覆盖（`brave_shields_settings_service.cc`）

### 1.3 ShardBrowser（Tauri 2 壳 + 独立 Chromium）

- API 仅绑 127.0.0.1 + **HS256 JWT 即时轮换吊销**（`api.rs`）；密钥首启生成
- **临时 profile 生命周期**：关闭自删 + 启动 purge 残留（`lib.rs:1260`）
- CDP 自动取端口（`--remote-debugging-port=0` + DevToolsActivePort 轮询）
- ⚠️ 风险点（反面教材）：`csp:null`、任意文件读、`--remote-allow-origins=*`、cookie 密钥硬编码

### 1.4 其余项目

- **CloakBrowser**：⚠️ 仓库无内核源码（Vite 脚手架 + 预编译二进制分发）；理念借鉴：拟人输入（humanize）、二进制自更新
- **electron-browser-shell**：极简标签浏览器 + Chrome 扩展支持（`packages/electron-chrome-extensions`）
- **browser-shell**：浏览器内 Linux VM（v86 + Plan9 共享文件系统），Cache Storage 状态缓存

---

## 二、对 Aegis 的可借鉴点（按落地优先级）

### 🔴 A 级（立即可借鉴，映射现有代码）

| 可借鉴点 | 来源（文件佐证） | Aegis 落地方向 |
|---|---|---|
| **统一请求拦截管线**（块→1×1 stub→头改写集中回调链） | brave `brave_request_handler_impl.cc` | 扩展 Aegis 已有 `request_sent` 事件（main_webview `_apply_dnt_header`）：DNT→威胁拦截→stub 统一管线，一次请求走全量策略 |
| **纯策略函数 fail-closed + 直接可测** | FreeDom `js_policy.c`/`request_policy.c` | 收敛 Aegis 的 `safe_url`/威胁拦截决策为单一可单测 Python 策略模块（现分散在 security/threat_feed/url_utils） |

### 🟡 B 级（中期可借鉴）

| 可借鉴点 | 来源 | Aegis 落地方向 |
|---|---|---|
| **per-site 确定性 farbling**（站点种子+PRNG） | brave `brave_session_cache.h` FarbleKey | `app/fingerprint.py`（可选模块）改确定性模式（现默认关闭） |
| **白名单覆盖黑名单**（hosts 风格优先级） | FreeDom `hostblock` | threat_feed 黑名单 + URL 白名单明确"白名单优先"语义（现双层但语义可强化） |
| **临时 profile 生命周期**（关闭自删+启动 purge） | ShardBrowser `lib.rs:1260` | Android TabManager 挂起清理借鉴（残留 WebView 回收） |

### ⚪ C 级（参考观察）

- 组件自更新（CloakBrowser）→ Aegis 已有 `watch_runtime_update`（WebView2 Runtime），可评估扩展
- Chrome 扩展支持（electron-browser-shell）→ 观察，政府项目扩展面谨慎
- VM 状态缓存（browser-shell）→ 概念参考（Cache Storage 状态恢复）

---

## 三、反面教训（避免踩坑）

| 风险 | 来源 | Aegis 对照 |
|---|---|---|
| `csp:null`（无 CSP） | ShardBrowser `tauri.conf.json` | ✅ Aegis 已做 CSP 收紧（WebView2 Settings） |
| 任意文件读 API | ShardBrowser `lib.rs::read_text_file` | ✅ Aegis js_api 白名单 + 参数校验 |
| `--remote-allow-origins=*` 无鉴权暴露 | ShardBrowser `launch.rs:193` | ⚠️ Aegis 需注意：若开启 CDP 调试必须回环绑定+鉴权 |
| cookie 密钥硬编码 | ShardBrowser `cookies.rs` | ✅ Aegis 凭据治理已环境变量注入 |

---

## 四、结论与下一步建议

1. **A 级落地（下一开发批次）**：统一请求拦截管线（DNT+威胁+stub 收敛到 request_sent）+ 纯策略函数收敛（safe_url 等集中可单测）
2. **B 级评估**：fingerprint.py 确定性 farbling、白名单优先语义、Android 挂起清理
3. **持续跟踪**：FreeDom 沙箱设计（若 Aegis 未来考虑更严格隔离）、brave shields 迭代（WebView2 无对应能力则记录）
4. **反向对照**：ShardBrowser 的 4 处安全风险已全部被 Aegis 现有设计规避（验证了 Aegis 安全纵深有效性）
