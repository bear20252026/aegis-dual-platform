# 开源浏览器调研报告（第三批）

> 调研时间：2026-08-21
> 调研范围：22+ 浏览器（用户提供的完整列表）
> 重点深入：Mullvad / LibreWolf / Zen / Arc / Helium / ungoogled-chromium / Tor / Brave

---

## 一、重点深入分析（8 个）

### 1. Mullvad Browser（反指纹标杆）

**基底**：Firefox（Tor Browser fork）
**维护方**：Mullvad VPN + Tor Project
**许可**：MPL-2.0

**核心架构**：编译时隐私 + 策略级反指纹

| 特性 | 实现方式 | Aegis 适用性 |
|------|---------|-------------|
| RFP（ResistFingerprinting） | `privacy.resistFingerprinting=true`，Firefox 内核级 | ★★★ Aegis 可参考 RFP 的系统化思路 |
| Letterboxing | 窗口尺寸圆整到 200×100px，所有用户进入有限桶 | ★★★ 防屏幕尺寸指纹，Aegis 可直接借鉴 |
| Canvas 随机化 | `randomDataOnCanvasExtract=true`，每次提取加噪声 | ★★★ 与 Aegis shield.rs 思路一致 |
| WebGL 禁用 | `readPixel` 函数禁用 | ★★☆ Aegis 可选择性禁用或噪声 |
| 定时器精度降低 | 1000μs + jitter | ★★☆ 防定时指纹，Aegis 可参考 |
| 时区归一化 | 报告 UTC | ★★☆ Aegis 可增加时区伪装 |
| 字体归一化 | 仅暴露捆绑字体，隐藏系统字体 | ★★★ 防字体指纹，Aegis 应借鉴 |
| 编译选项 | `--disable-crashreporter`/`--enable-bundled-fonts`/`--disable-eme` | ★★☆ 编译时隐私 |

**关键设计哲学**：
> "所有用户看起来一样"（herd immunity）——不是随机化让每个人不同，而是让每个人相同。

**与 Aegis 对比**：Aegis 采用"噪声随机化"策略（每个人不同），Mullvad 采用"归一化"策略（每个人相同）。两种策略各有优劣：
- 归一化：更难被统计检测，但牺牲个性化（字体/时区/屏幕受限）
- 随机化：更灵活，但可能被噪声检测算法识别

**建议**：Aegis 可混合策略——对高熵属性（Canvas/WebGL）用随机化，对低熵属性（时区/语言/屏幕）用归一化。

---

### 2. LibreWolf（Firefox 隐私增强版）

**基底**：Firefox
**维护方**：LibreWolf Community
**许可**：MPL-2.0

**核心架构**：配置文件级隐私增强（librewolf.cfg）

| 特性 | 实现方式 | Aegis 适用性 |
|------|---------|-------------|
| 严格内容拦截 | `browser.contentblocking.category=strict`，dFPI + 严格拦截列表 | ★★★ Aegis 可参考严格模式默认值 |
| APS（Always Partition Storage） | 第三方 cookie/storage 始终分区 | ★★★ 防跨站追踪，Aegis 可借鉴 |
| 查询参数剥离 | 与 Brave 相同的剥离列表（fbclid/gclid 等） | ★★★ Aegis 可直接复用剥离列表 |
| RFP 默认启用 | `privacy.resistFingerprinting=true` | ★★★ 与 Mullvad 一致 |
| WebGL 默认禁用 | "WebGL is a strong fingerprinting vector" | ★★☆ Aegis 可选择性处理 |
| 证书固定 | `security.cert_pinning.enforcement_level=2`（严格） | ★★☆ Aegis 已有类似机制 |
| Safe Browsing 默认禁用 | 出于审查担忧，但推荐初学者启用 | ★☆☆ Aegis 需要 Safe Browsing |

**关键配置文件结构**（librewolf.cfg）：
```
PRIVACY [ISOLATION, SANITIZING, CACHE, HISTORY, QUERY STRIPPING]
NETWORKING [HTTPS, REFERERS, WEBRTC, PROXY, DNS, PREFETCHING]
FINGERPRINTING [RFP, WEBGL]
SECURITY [SITE ISOLATION, CERTIFICATES, TLS/SSL, PERMISSIONS, SAFE BROWSING]
BEHAVIOR [DRM, SEARCH, DOWNLOADS, AUTOPLAY, POP-UPS]
EXTENSIONS [USER INSTALLED, SYSTEM, EXTENSION FIREWALL]
```

**与 Aegis 对比**：LibreWolf 的配置文件结构非常清晰——按类别组织，每个配置项有注释说明原因。Aegis 的安全策略可以参考这种结构化方式。

---

### 3. Zen Browser（工作区浏览器）

**基底**：Firefox
**维护方**：Zen Community
**许可**：MPL-2.0
**Stars**：★高（GitHub 热门 Firefox fork）

**核心架构**：最小补丁 + 最大扩展

```
┌─────────────────────────────────────┐
│        Zen Browser Chrome           │
│  Vertical Tabs | Folders | Spaces   │
├─────────────────────────────────────┤
│     Zen Modules (standalone)        │
│  SpaceRouting | SplitView | Glance  │
│  Folders | Boosts | SessionStore    │
├─────────────────────────────────────┤
│     Firefox Patches (minimal)       │
│  browser.xhtml | tabbrowser | etc   │
├─────────────────────────────────────┤
│        Firefox Engine               │
│  Gecko | JS Engine | Networking     │
└─────────────────────────────────────┘
```

**关键设计模式**：

| 模式 | 描述 | Aegis 适用性 |
|------|------|-------------|
| Manager-based 单例模式 | 每个子系统由单例 Manager 控制 | ★★★ 与 Aegis 的 Broker/Executor 模式一致 |
| Space Routing | `nsZenSpaceRoutingManager` 拦截 `onBeforeAddTab` 路由 URL 到工作区 | ★★★ Aegis 可参考 URL 路由模式 |
| 最小补丁原则 | 只补丁 Firefox 关键组件（SessionStore/TabState），其余用扩展 | ★★☆ Aegis 的 Strangler Fig 思路一致 |
| 工作区同步 | 通过 Firefox Sync 同步工作区/标签/容器 | ★★☆ Aegis 可参考跨设备同步方案 |
| Split View | 并排浏览，无需管理多个窗口 | ★★☆ Aegis 可增加分屏功能 |

**与 Aegis 对比**：Zen 的"最小补丁 + 最大扩展"策略与 Aegis 的"Strangler Fig"渐进迁移策略一致——都不重写核心，而是通过扩展层增强。

---

### 4. Arc Browser（工作区 UI 标杆）

**基底**：Chromium
**维护方**：The Browser Company → Atlassian（2025 收购）
**状态**：已宣布停止开发，转向 Dia（AI 浏览器）
**许可**：Proprietary Freeware

**核心架构**：操作系统级浏览器

| 特性 | 描述 | Aegis 适用性 |
|------|------|-------------|
| Spaces | 独立浏览区域，各有自己的 Pin/主题/图标 | ★★★ Aegis 可参考工作区隔离 |
| Air Traffic Control | URL 自动路由到指定 Space（基于域名/路径规则） | ★★★ 与 Aegis 的 Broker 路由一致 |
| Command Bar | Cmd+T 统一搜索标签/历史/书签/操作 | ★★☆ Aegis 可增加统一命令面板 |
| Boosts | 每站点自定义 CSS/JS 注入 | ★★☆ Aegis 可增加用户级站点定制 |
| Little Arc | 最小窗口（单标签，无 chrome） | ★★☆ 快速任务窗口 |
| 自动归档 | Today 区域标签 12 小时后自动归档 | ★★☆ 防标签堆积 |
| 渐变身份 | 每个 Space 有独特渐变色 | ★☆☆ 纯 UI 特性 |

**设计哲学**：
> "Finding should be faster than organizing. Good search eliminates the need for perfect organization."
> "Not every task needs the full browser. Match the interface to the task's weight."

**与 Aegis 对比**：Arc 的 Spaces + Air Traffic Control 与 Aegis 的 Broker→Decision→Executor 链路在概念上一致——都是基于规则的 URL 路由。Arc 偏 UI 层，Aegis 偏安全层。

---

### 5. Helium（隐私优先 Chromium）★19665

**基底**：ungoogled-chromium（重度修改）
**维护方**：imputnet
**许可**：GPL-3.0
**Stars**：★19665（高人气）

**核心架构**：编译时隐私 + 匿名服务

| 特性 | 实现方式 | Aegis 适用性 |
|------|---------|-------------|
| 零首次请求 | 启动时零网络请求，无分析/无广告 | ★★★ 与 Aegis INV-01 一致 |
| 指纹噪声 | Canvas/WebGL/Audio 噪声 + "我们不知道的其他分析攻击" | ★★★ 与 Aegis shield.rs 一致 |
| 匿名扩展下载 | 通过 Helium services 代理 Chrome Web Store 请求 | ★★★ Aegis 可参考匿名代理模式 |
| !bangs 快捷搜索 | `!gh` → GitHub 搜索 | ★★☆ UX 增强 |
| 无密码管理器/无同步/无 DRM | 极简设计 | ★★☆ Aegis 需要这些功能 |
| 补丁来源 | Inox/Debian/Bromite/Iridium/Brave | ★★☆ 可参考补丁来源 |

**关键设计**：
> "Helium makes zero web requests on first launch, has no analytics, and no first-party ads. All types of requests to Helium services must be acknowledged and approved by you."

**与 Aegis 对比**：Helium 的"零首次请求 + 匿名服务代理"模式非常值得 Aegis 借鉴——所有外部请求必须经用户确认。

---

### 6. ungoogled-chromium（Google 去除框架）

**基底**：Chromium
**维护方**：ungoogled-software
**许可**：BSD-3-Clause

**核心架构**：7 阶段构建流水线

```
1. Source Acquisition (下载 Chromium 源码)
2. Binary Pruning (移除预编译二进制)
3. Patch Application (~200+ 补丁，GNU Quilt 格式)
4. Domain Substitution (替换 Google 域名为 qjz9zk)
5. Build Configuration (GN flags)
6. Compilation (Ninja 构建)
7. Packaging (平台打包)
```

**关键设计**：

| 阶段 | 描述 | Aegis 适用性 |
|------|------|-------------|
| Binary Pruning | 移除源码树中的预编译二进制 | ★★☆ 供应链安全 |
| Domain Substitution | 替换所有 Google 域名为不存在的替代（qjz9zk） | ★★★ 防未修补的 Google 请求 |
| 补丁分类 | core（背景请求/Google 服务）+ extra（控制/透明） | ★★☆ 补丁管理 |
| 域名阻断 | 请求到 qjz9zk 域名被拦截并通知用户 | ★★★ 检测未修补请求 |

**与 Aegis 对比**：ungoogled-chromium 的 Domain Substitution 技术非常巧妙——替换域名为不存在的替代，任何未修补的请求都会被拦截。Aegis 可参考这种"编译时检测"思路。

---

### 7. Tor Browser（匿名性标杆）

**基底**：Firefox
**维护方**：Tor Project
**许可**：MPL-2.0

**核心架构**：最大匿名性

| 特性 | 实现方式 | Aegis 适用性 |
|------|---------|-------------|
| RFP 最严格 | 所有高熵 API 禁用或归一化 | ★★★ 参考价值最高 |
| Letterboxing 默认启用 | 窗口尺寸圆整 | ★★★ Aegis 应默认启用 |
| 捆绑字体 | 仅暴露内置字体 | ★★★ 防字体指纹 |
| 时区 UTC | 所有用户同一时区 | ★★☆ Aegis 可增加 |
| 洋葱路由 | 多跳代理，IP 匿名 | ★☆☆ Aegis 不需要（性能代价高） |
| 最大桶策略 | 所有用户看起来完全一样 | ★★★ 归一化 vs 随机化 |

**与 Aegis 对比**：Tor Browser 是反指纹的极端案例——牺牲所有个性化换取最大匿名性。Aegis 需要在隐私和可用性之间平衡，但 Tor 的 RFP 实现是参考金标准。

---

### 8. Brave（商业化隐私浏览器）

**基底**：Chromium
**维护方**：Brave Software
**许可**：MPL-2.0

**核心架构**：随机化反指纹

| 特性 | 实现方式 | Aegis 适用性 |
|------|---------|-------------|
| 双策略反指纹 | (1) 归一化 API (2) 随机化值 | ★★★ Aegis 应采用混合策略 |
| 种子机制 | 每 session + 每 site (eTLD+1) + 每 storage area 独立种子 | ★★★ 与 Aegis sessionSeed 一致 |
| Canvas 噪声 | 每 canvas 独立扰动（基于尺寸+上下文） | ★★★ 比 Aegis 当前实现更精细 |
| WebGL/WebGPU 保护 | 2026-08 新增 GPU 指纹防护 | ★★★ Aegis 应跟进 |
| Shields 系统 | 分级拦截（aggressive/standard/allow） | ★★☆ Aegis 可参考分级模式 |
| 查询参数剥离 | fbclid/gclid 等 | ★★★ 与 LibreWolf 一致 |
| FingerprintJS 完全击败 | 官方确认 FingerprintJS 无法生成稳定标识 | ★★★ Aegis 目标 |

**关键设计**：
> "Randomization values are derived from a seed that changes per session, per site (eTLD+1) and per storage area. Third party frames share the seed value of the top level domain. This approach is especially useful in fingerprinters that hash together a large number of semi-identifiers, since randomizing just one value 'poisons' the entire fingerprint."

**与 Aegis 对比**：Brave 的反指纹实现是目前商业浏览器中最先进的。Aegis 的 sessionSeed + shield.rs 噪声思路与 Brave 一致，但 Brave 的 per-site per-storage 种子机制更精细。

---

## 二、快速扫描（14 个）

| 浏览器 | 基底 | 语言 | 核心特性 | Aegis 借鉴点 |
|--------|------|------|---------|-------------|
| **Firefox** | Gecko | C++/Rust/JS | RFP/dFPI/增强追踪保护 | 反指纹基础设施 |
| **Chromium** | — | C++ | 多进程架构/Site Isolation | 架构参考 |
| **Chrome** | Chromium | C++ | 最广泛兼容性 | 兼容性基线 |
| **Edge** | Chromium | C++ | IE 兼容/企业特性 | 无 |
| **Safari** | WebKit | Swift/C++ | ITP/高级指纹防护（Safari 26 默认启用） | WebKit 隐私参考 |
| **Opera** | Chromium | C++ | 内置 VPN/广告拦截 | 无 |
| **Vivaldi** | Chromium | C++ | 高度可定制/标签管理 | UI 定制参考 |
| **Yandex** | Chromium | C++ | 俄罗斯市场 | 无 |
| **Orion** | WebKit | Swift | 支持 Chrome+Firefox 扩展 | 多扩展兼容 |
| **qutebrowser** | Qt WebEngine | Python | 键盘驱动/vim 风格 | 无（极小众） |
| **Ora** | Chromium | JS | 空格键操作/标签管理/垂直侧边栏 | UX 参考 |
| **Min** | Electron | JS | 极简/任务分组/全文搜索 | 架构参考（8981★） |
| **Tabbit** | — | — | AI 原生/上下文理解/自动化 | AI 集成参考 |
| **ChatGPT Atlas** | — | — | 内置 ChatGPT | AI 集成参考 |
| **Web** | WebKit | SwiftUI | macOS AI 浏览器/开源 | 无 |

---

## 三、反指纹策略对比

| 策略 | 代表浏览器 | 机制 | 优势 | 劣势 |
|------|-----------|------|------|------|
| **归一化（Herd Immunity）** | Tor / Mullvad | 所有用户看起来一样 | 最难被统计检测 | 牺牲个性化（字体/时区/屏幕受限） |
| **随机化（Noise Injection）** | Brave / Aegis | 每 session/site 加噪声 | 灵活，保留功能 | 可能被噪声检测算法识别 |
| **混合策略** | Brave（推荐） | 高熵属性随机化 + 低熵属性归一化 | 平衡隐私与可用性 | 实现复杂 |
| **API 禁用** | Tor / LibreWolf | 禁用高指纹熵 API | 彻底消除向量 | 牺牲 Web 功能 |
| **配置文件增强** | LibreWolf | 通过 cfg 文件设置安全默认值 | 简单，可审计 | 依赖 Firefox RFP |

---

## 四、可借鉴优先级（第三批新增）

### P0（高优先级——直接增强 Aegis）

1. **Brave 的 per-site per-storage 种子机制**
   - 当前 Aegis sessionSeed 是全站共享——应改为 per-site (eTLD+1) 独立种子
   - 防止跨站关联

2. **Mullvad 的 Letterboxing**
   - 窗口尺寸圆整到 200×100px
   - 防屏幕尺寸指纹
   - 实现简单，收益高

3. **Mullvad/LibreWolf 的字体归一化**
   - 仅暴露捆绑字体，隐藏系统字体
   - 防字体指纹（高熵向量）

4. **Helium 的匿名服务代理**
   - 所有外部请求（扩展商店/搜索建议）通过匿名代理
   - 防服务端追踪

### P1（中优先级——可选增强）

5. **LibreWolf 的查询参数剥离列表**（fbclid/gclid 等 25+ 参数）
6. **Brave 的 WebGL/WebGPU 保护**（2026-08 新增）
7. **Zen 的 Space Routing 模式**（URL 自动路由到工作区）
8. **Arc 的 Command Bar**（统一搜索标签/历史/操作）
9. **ungoogled-chromium 的 Domain Substitution**（编译时检测未修补请求）

### P2（低优先级——参考价值）

10. **Tor 的最大归一化策略**（Aegis 不需要极端匿名）
11. **Min 的任务分组**（轻量级标签管理）
12. **qutebrowser 的键盘驱动**（极小众）
13. **Tabbit/ChatGPT Atlas 的 AI 集成**（未来方向）

---

## 五、总结：Aegis 反指纹增强路线图

基于三批调研，Aegis 应按以下优先级增强反指纹能力：

### Phase 1（立即实施）

| 增强项 | 参考来源 | 复杂度 | 收益 |
|--------|---------|--------|------|
| per-site 种子（eTLD+1） | Brave | 中 | 高（防跨站关联） |
| Letterboxing | Mullvad/Tor | 低 | 高（防屏幕指纹） |
| 字体归一化 | Mullvad/LibreWolf | 中 | 高（防字体指纹） |
| 查询参数剥离 | LibreWolf/Brave | 低 | 中（防 URL 追踪） |

### Phase 2（近期实施）

| 增强项 | 参考来源 | 复杂度 | 收益 |
|--------|---------|--------|------|
| WebGL 参数固定 | playwright-afp | 中 | 中（防 GPU 指纹） |
| 定时器精度降低 | Mullvad | 低 | 中（防定时指纹） |
| 匿名扩展下载代理 | Helium | 中 | 中（防扩展追踪） |
| Function.prototype.toString 欺骗 | playwright-afp | 中 | 中（防代理检测） |

### Phase 3（中期实施）

| 增强项 | 参考来源 | 复杂度 | 收益 |
|--------|---------|--------|------|
| 三种保护模式（兼容/平衡/最大） | fingerprint-toolkit | 低 | 中（用户选择） |
| Space Routing（URL 路由到工作区） | Zen/Arc | 高 | 中（UX 增强） |
| Command Bar（统一命令面板） | Arc | 中 | 低（UX 增强） |
