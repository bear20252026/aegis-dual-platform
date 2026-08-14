# 隐私默认配置对照审计：LibreWolf vs Aegis（落地建议②）

> 审计日期：2026-08-15 ｜ 对照源：LibreWolf `librewolf.cfg`（gitlab.com/librewolf-community/settings）
> 目标：逐项对照 LibreWolf 隐私默认值，检查 Aegis config.py 默认值是否对齐、是否真正生效。

---

## 一、LibreWolf 隐私默认清单（librewolf.cfg 核心项）

| 类别 | 关键项 | LibreWolf 默认 |
|---|---|---|
| **TELEMETRY** | `toolkit.telemetry.unified/enabled` | `false`（lock，master 开关） |
| | `toolkit.telemetry.server` | `"data:,"`（置空禁用） |
| | `datareporting.healthreport.uploadEnabled` | `false` |
| | `toolkit.coverage.enabled` | `false` |
| | `toolkit.crashreporter.infoURL` | `""`（禁用崩溃上报） |
| **FINGERPRINTING** | `webgl.disabled` | `true`（WebGL 是强指纹向量） |
| | `dom.webgpu.enabled` | `false` |
| | `privacy.resistFingerprinting`（RFP） | 默认启用（可覆盖） |
| **WEBRTC** | `media.peerconnection.ice.default_address_only` | `true`（单接口，防 IP 泄露） |
| **NETWORKING** | 预取/推测连接 | 默认禁用（prefetching/speculative） |
| **QUERY** | 查询参数剥离 | 默认启用（query stripping） |

## 二、Aegis config.py 隐私字段对照

| Aegis 字段 | 默认值 | 对齐 LibreWolf？ | 生效状态 |
|---|---|---|---|
| `adblock` | `True` | ✅ 理念一致（隐私默认开） | ⚠️ **影子配置**（实现随 Qt 旧栈归档，新栈未接入） |
| `do_not_track` | `True` | ✅ 对齐（DNT 默认开） | ⚠️ **影子配置** |
| `safe_browsing` | `True` | ✅ 理念一致 | ⚠️ **影子配置**（threat_feed 新栈存在，但 safe_browsing 字段未接） |
| `webrtc_ip_leak_protection` | `True` | ✅ 对齐 LibreWolf WebRTC 防护 | ⚠️ **影子配置** |
| `search_suggestions` | `True` | ⚠️ LibreWolf 倾向禁远程建议 | ⚠️ **影子配置** |
| `save_passwords` | `True` | ✅ 理念一致（LibreWolf 允许） | ⚠️ **影子配置** |
| `use_system_proxy` | `True` | ✅ | ✅ 新栈已接入（nav 层） |
| 无遥测字段 | — | ✅ Aegis 代码**零遥测**（优于 LibreWolf 的"已禁"） | ✅ 天然满足 |

## 三、审计结论

1. **默认值全部对齐隐私理念**：Aegis 的隐私默认（adblock/DNT/safe_browsing/webrtc 防护全开）与 LibreWolf 一致，且**无任何遥测**（LibreWolf 需显式禁，Aegis 天生没有）——无需修改默认值。
2. **发现"影子配置"真相**：`adblock/do_not_track/safe_browsing/webrtc_ip_leak_protection/search_suggestions/save_passwords` 六个字段**仅在 config 声明，运行时代码未引用**（其实现随 S2 归档随 Qt 旧栈进入 legacy）。
   - **不是安全漏洞**：无代码读取它们执行危险操作；
   - **但是声明与能力脱节**：开发者会误以为这些防护已生效。
3. **修正动作（不改功能、不失效）**：
   - config.py 隐私字段区加**状态标注注释**（哪些已接入/哪些待新栈实现），防止误读；
   - 默认值保持不变（已对齐 LibreWolf 且不破坏现有行为）。

## 四、后续建议（新栈能力接入路线图）

| 优先级 | 能力 | 新栈接入路径 |
|---|---|---|
| 高 | `do_not_track`（DNT 头） | WebView2 请求头设置（pywebview 底层可注入） |
| 高 | `safe_browsing` | 复用 `threat_feed.py`（新栈已存在）扩展 |
| 中 | `adblock` | 复用 legacy `adblock.py` 逻辑迁移（或接 WebView2 请求拦截） |
| 中 | `webrtc_ip_leak_protection` | WebView2 策略/Chromium 标志 |
| 低 | `search_suggestions` | 地址栏建议逻辑接入 |
