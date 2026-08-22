# 浏览器生态调研：13 个开源浏览器对 Aegis 的参考价值（R9）

> 调研日期：2026-08-15 ｜ 目标：对用户提供的 13 个开源浏览器逐一核实、分类，
> 判断哪些对 Aegis（Windows=pywebview+WebView2 壳 / Android=Kotlin+System WebView 壳）
> 有直接或理念层面的参考价值。

---

## 一、核实结果（2026-08-15，全部真实存在且活跃）

| 项目 | ★ | 语言 | 许可证 | 活跃度 |
|---|---|---|---|---|
| Ladybird | 65.6k | C++ | BSD-3-Clause | 2026-08-14 更新 |
| Zen Browser | 43.9k | JS/TS | MPL-2.0 | 2026-08-14 更新 |
| Servo | 37.7k | Rust | MPL-2.0 | 2026-08-14 更新 |
| Ungoogled Chromium | 27.4k | Python/C++ | BSD-3-Clause | 2026-08-14 更新 |
| Brave | 22k | TS/C++ | MPL-2.0 | 活跃（v1.91.28） |
| Min | 9.1k | JS/Electron | Apache-2.0 | 活跃 |
| Floorp | 8.3k | TS | MPL-2.0 | v12.16.4（2026-07-26） |
| Firefox | — | C++ | MPL-2.0 | 活跃 |
| Tor Browser | — | C++ | BSD+MPL | 活跃 |
| LibreWolf | — | C++ | MPL-2.0 | v150.0.1-1（2026-06） |
| Waterfox | — | C++ | MPL-2.0 | 6.6.17（2026-07-21） |
| Midori | — | C/WebKitGTK | LGPL | 活跃 |
| Falkon | — | C++/QtWebEngine | GPL-3.0 | 活跃 |

## 二、重新分类（按内核来源，验证用户分类）

| 内核家族 | 项目 | 备注 |
|---|---|---|
| **Gecko（Firefox 家族）** | Firefox / Tor / LibreWolf / Waterfox / Floorp / Zen | Tor 与 LibreWolf 本质是 Firefox 分支（用户分类需注意） |
| **Chromium 家族** | Ungoogled / Brave / Min(Electron) / Falkon(QtWebEngine) | Min、Falkon 归此而非"独立轻量" |
| **独立引擎** | Ladybird / Servo | 不依赖 Blink/WebKit/Gecko |
| **WebKit 家族** | Midori | 修正：内核是 WebKitGTK 非 Chromium |

**用户分类验证结论**：总体准确；2 处修正（Midori=WebKitGTK；Min/Falkon=Chromium 内核），1 处重叠提示（Tor/LibreWolf 属 Gecko 分支）。

## 三、对 Aegis 的作用分析

### 🟢 直接相关（同"WebEngine 壳"形态）→ 建议持续关注
1. **Min**（已深入研读）：与 Aegis 完全同构的极简壳；已落地其 3 项建议（R1 快捷键表、R4 标签分层、R8 阅读模式）
2. **Falkon**：QtWebEngine 壳 + 内置广告拦截，最接近 Aegis 架构的取舍范式
3. **Floorp**：垂直标签页 + 工作区——Aegis 标签增强的下一步蓝本
4. **Zen**：极简 UI 哲学与垂直标签布局参考

### 🟡 理念相关（配置/功能借鉴，无代码复用）
- Firefox：配置分层哲学；LibreWolf：默认隐私清单（对照 Aegis 配置默认值）
- Brave：Shields 广告拦截思路 + 本地 AI（Leo）与 Aegis 方向一致
- Ungoogled：最小化后台通信的思路（Aegis 用 WebView2，通用理念）

### 🔴 确认无直接作用
- Ladybird / Servo：自研引擎，工程量差 100 倍，仅严谨性理念
- Tor Browser：依赖 Tor 网络，政府内网场景不适用
- Waterfox / Midori：内核不同（Gecko/WebKitGTK），无增量

## 四、结论

> Aegis 是"Chromium 内核壳浏览器"，与 Min/Falkon 形态最接近、与 Floorp/Zen
> 的标签与 UI 理念互补；自研引擎类（Ladybird/Servo）与 Tor 类不在本路线内。
> 建议：短期对齐 Floorp 垂直标签 + 工作区；中期对照 LibreWolf 默认隐私清单
> 复核 Aegis 配置；长期跟踪 Brave 本地 AI 与 Ungoogled 的去后台化思路。
