# 开源浏览器调研报告（第二批）

> 调研时间：2026-08-21
> 调研目标：发现可借鉴的安全架构模式、指纹防护实现、信任边界设计

---

## 1. scowser（C++/Qt6 WebEngine）★1

**仓库**：https://github.com/scowser/scowser
**语言**：C++20 / Qt6 WebEngine
**许可**：Apache-2.0
**亮点**：清晰的安全层架构分层

### 架构

```
┌─────────────────────────────────┐
│           scowser UI            │
│  (MainWindow, Tabs, AddressBar) │
├─────────────────────────────────┤
│        Security Layer           │
│  AdBlocker · DoH · CertPinner   │
│  CSP Enforcer · SessionManager  │
├─────────────────────────────────┤
│     Request Interceptor         │
│  (filters all network traffic)  │
├─────────────────────────────────┤
│      Qt6 WebEngine (Chromium)   │
│   (rendering, JS, sandboxing)   │
└─────────────────────────────────┘
```

### 可借鉴点

| 模式 | Aegis 适用性 | 借鉴方式 |
|------|-------------|---------|
| Request Interceptor 统一拦截管线 | ★★★ 高度匹配 | Aegis 已有 `_apply_request_policy`，可参考 scowser 的 filter list 集成方式 |
| Security Layer 独立层 | ★★★ 高度匹配 | Aegis 的 Broker→Decision→Executor 链路类似，可参考 CSP Enforcer 的注入方式 |
| Ephemeral by Default（默认临时会话） | ★★☆ 中等 | Aegis 可增加"隐私浏览"模式，默认不持久化 |
| CSP 头注入 | ★★☆ 中等 | Aegis 可在 Request Interceptor 层注入 CSP 头 |

### 与 Aegis 架构对比

scowser 的 4 层架构（UI → Security → Interceptor → Chromium）与 Aegis 的单路径数据流（Adapter→Broker→Decision→Executor→BrowserEvent→BrowserSessionState→ChromeUI）高度一致。scowser 更扁平（4 层），Aegis 更细粒度（7 层）——Aegis 的分层更清晰，但 scowser 的 Request Interceptor 统一拦截模式值得参考。

---

## 2. Onyxia（Rust/Tauri）★1

**仓库**：https://github.com/aieonyx/onyxia
**语言**：Rust / TypeScript / Tauri v2
**许可**：未明确
**亮点**：信任边界不变量、主权渲染引擎

### 架构

```
+-----------------------------------------+
|           Onyxia Browser Chrome         |  <- TypeScript (UI only)
+----------------+------------------------+
| Tauri IPC (Rust commands)
+----------------v------------------------+
|            Rust Backend                 |
|  Tab Manager | AWP Handler | SSV / STS  |
|  Vault | Session | Legacy | Aegis       |
+----------------+------------------------+
```

### 核心不变量

> **Trust boundary invariant: all security state computed in Rust. Frontend renders only.**

这与 Aegis 的 INV-01（远程零原生能力）和 INV-02（Executor 唯一副作用点）高度一致。

### 可借鉴点

| 模式 | Aegis 适用性 | 借鉴方式 |
|------|-------------|---------|
| 信任边界不变量（Rust 计算，前端仅渲染） | ★★★ 高度匹配 | 验证 Aegis 的 INV-01/INV-02 设计正确性 |
| ARPi 五层验证（Schema→Identity→Auth→Scope→Anomaly） | ★★☆ 中等 | Aegis 可参考 ARPi 的分层验证模式增强 Broker 决策 |
| Sovereign Threat Sensor（本地威胁检测） | ★★☆ 中等 | Aegis 已有 adblock + security_policy，可参考 SSV/STS 的 typosquat 检测 |
| EdisonDB 本地数据库 | ★☆☆ 低 | Aegis 使用 SQLite，无需更换 |
| HANIEL 主权渲染引擎 | ★☆☆ 低 | Aegis 使用系统 WebView，无需自建渲染引擎 |

### 与 Aegis 架构对比

Onyxia 的信任边界设计验证了 Aegis 的架构决策：安全状态必须在 Rust/原生层计算，UI 层仅渲染。Onyxia 使用 Tauri v2（与 Aegis 的 pytauri 迁移目标一致），证明 Tauri 可用于安全浏览器。

---

## 3. playwright-afp（指纹防护库）★18

**仓库**：https://github.com/pavlealeksic/playwright-afp
**语言**：JavaScript
**许可**：MIT
**亮点**：确定性指纹、一致性配置文件、全面覆盖

### 覆盖范围

| 模块 | 描述 |
|------|------|
| Canvas | 像素偏移（RGBA -5..5），OffscreenCanvas 支持 |
| WebGL | vendor/renderer 欺骗，硬件限制伪装 |
| AudioContext | 频率偏移噪声 |
| Fonts | offsetHeight/offsetWidth + measureText 噪声 |
| Navigator | userAgent/platform/vendor/languages/userAgentData |
| Screen | 分辨率 + outerWidth/outerHeight |
| WebRTC | 移除 RTCPeerConnection（防 IP 泄露） |
| Plugins | PDF plugins + mimeTypes 伪装 |
| Permissions | notifications 权限一致性 |

### 关键设计

1. **确定性指纹**（seeded PRNG）——同一 seed 产生同一指纹，会话内稳定
2. **一致性配置文件**（coherent profiles）——所有属性描述同一台可信机器
3. **Function.prototype.toString 欺骗**——注入的代理无法被检测

### 可借鉴点

| 模式 | Aegis 适用性 | 借鉴方式 |
|------|-------------|---------|
| 确定性指纹（seeded PRNG） | ★★★ 高度匹配 | Aegis 的 shield.rs 已有 sessionSeed，可参考 PRNG 方案 |
| 一致性配置文件 | ★★★ 高度匹配 | Aegis 的 FINGERPRINT_SHIELD_JS 可参考 coherent profiles |
| Function.prototype.toString 欺骗 | ★★☆ 中等 | 防止注入的代理被检测 |
| WebGL 参数固定 | ★★☆ 中等 | Aegis 可参考 webgl.data 固定方案 |

### 与 Aegis 对比

Aegis 的 shield.rs（canvas/WebGL/Audio 噪声）与 playwright-afp 的实现思路一致。playwright-afp 的优势在于：
1. **确定性**（seeded PRNG）——同一会话内指纹稳定
2. **一致性**（coherent profiles）——所有属性描述同一台机器
3. **防检测**（toString 欺骗）——注入的代理无法被发现

Aegis 可借鉴这三个设计增强 FINGERPRINT_SHIELD_JS。

---

## 4. fingerprint-toolkit（指纹随机化工具包）★1

**仓库**：https://github.com/xuweizhengo/fingerprint-toolkit
**语言**：Python
**许可**：未明确
**亮点**：多维随机化、2.4M+ 唯一组合

### 覆盖范围

| 模块 | 描述 |
|------|------|
| Canvas | RGB 噪声，改变 hash |
| WebGL | GPU vendor/renderer 欺骗（Intel/NVIDIA/AMD/Apple） |
| Audio | AudioContext 频率偏移 |
| Navigator | hardwareConcurrency/deviceMemory/platform/languages/webdriver |
| Screen | 分辨率/colorDepth/pixelDepth |
| WebRTC | 防 IP 泄露 |
| Timezone | 时区欺骗 |
| Fonts | 自定义字体列表 |
| Battery | 电量/充电状态欺骗 |
| Permissions | 通知/剪贴板权限伪装 |

### 关键设计

- **2.4M+ 唯一组合**（1000 Canvas × 20 GPU × 6 CPU × 4 RAM × 5 Screen）
- **CDP 注入**（Page.addScriptToEvaluateOnNewDocument）——在页面脚本之前运行
- **三种模式**：兼容/平衡/最大隐私

### 可借鉴点

| 模式 | Aegis 适用性 | 借鉴方式 |
|------|-------------|---------|
| 多维随机化（2.4M+ 组合） | ★★☆ 中等 | Aegis 可增加更多指纹维度（Battery/Timezone/Fonts） |
| CDP 注入时序（页面脚本之前） | ★★☆ 中等 | Aegis 的 WebView 注入时序可参考 |
| 三种保护模式 | ★★☆ 中等 | Aegis 可增加"兼容/平衡/最大隐私"模式切换 |

---

## 总结：可借鉴优先级

### P0（高优先级——直接增强 Aegis）

1. **确定性指纹（seeded PRNG）**（playwright-afp）
   - Aegis 的 shield.rs 已有 sessionSeed，可参考 PRNG 方案增强稳定性
   - 同一会话内指纹应稳定（当前每次注入可能不同）

2. **一致性配置文件（coherent profiles）**（playwright-afp）
   - Aegis 的 FINGERPRINT_SHIELD_JS 可参考 coherent profiles
   - 所有指纹属性应描述同一台可信机器

3. **Request Interceptor 统一拦截管线**（scowser）
   - Aegis 已有 `_apply_request_policy`，可参考 filter list 集成方式

### P1（中优先级——可选增强）

4. **Function.prototype.toString 欺骗**（playwright-afp）
5. **ARPi 五层验证模式**（Onyxia）
6. **Ephemeral by Default**（scowser）
7. **三种保护模式**（fingerprint-toolkit）

### P2（低优先级——参考价值）

8. **HANIEL 主权渲染引擎**（Onyxia）——Aegis 使用系统 WebView，无需自建
9. **EdisonDB**（Onyxia）——Aegis 使用 SQLite，无需更换
10. **Timezone/Battery 欺骗**（fingerprint-toolkit）——可选增强
