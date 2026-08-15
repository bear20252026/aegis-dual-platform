# Aegis 开发优化点计划（optimization-plan）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> 依据：6 个开源浏览器源码精读（brave/FreeDom/ShardBrowser/
> CloakBrowser/browser-shell/electron-browser-shell）+ 权威信源交叉比对
> （官方仓库核实：brave/adblock-rust ★2732、grisuno/FreeDom ★17、
> ProxyShard/ShardBrowser ★641、SalhaNabil/CloakBrowser ★56、
> humphd/browser-shell ★330、samuelmaddock/electron-browser-shell ★725）
> 原则：政府级小心严谨——设计先行、零风险门禁、优先级排序

---

## 〇、结论速览

6 项目交叉比对（3 个官方名修正 + 全部借鉴点经"源码精读 + 官方描述"双向确认，无被推翻项）得出 Aegis 优化点分四级：**P0 已落地 4 项 / P1 门禁后开发 2 项 / P2 评估后开发 3 项 / P3 概念观察**。

## 一、P0（已落地，持续维护）

| 优化点 | 来源 | 落地位置 |
|---|---|---|
| 统一请求回调链 | brave（★2732 官方 Rust 引擎） | main_webview `_apply_request_policy` |
| 六维上下文记录增强 | brave（第 1 步） | main_webview 威胁命中日志（method + request_type） |
| 凭据不落地（反 dump 理念） | FreeDom（★17） | app/credential_guard + log_event 接入 |
| 白名单 fail-closed | FreeDom | js_api/URL 白名单双关口 |

## 二、P1（设计已就绪，门禁后开发）

| # | 优化点 | 来源 | 门禁（政府级） |
|---|---|---|---|
| 1 | **威胁拦截资源类型区分**（文档导航 vs 子资源——降误拦、防绕过） | brave 六维第 2 步（docs/threat-context-design.md） | 本机实测 WebView2 request_sent 的 method/Content-Type 可得性 → 回归全绿 → 才改拦截语义 |
| 2 | **farbling 反指纹确定性复核** | brave | 核对 fingerprint.py 现实现（确定性 farbling 是否与权威机制一致）→ 修正后回归 |

## 三、P2（评估后可开发）

| # | 优化点 | 来源 | 评估点 |
|---|---|---|---|
| 3 | **临时 profile 隔离复核** | ShardBrowser 反面教材（★641） | user_data 目录隔离现状 vs JWT 轮换/临时 profile 设计 |
| 4 | **hints 动作扩展**（F 新后台标签 / yf 复制 URL——Vimium 8 模式） | qutebrowser/Vimium（基础版已落地） | 现有快捷键表冲突检查（Ctrl/Meta 组合键体系） |
| 5 | **Chrome 扩展支持评估** | electron-browser-shell（★725 官方确认） | Aegis 未来可选方向（WebView2 扩展 API 能力核实） |

## 四、P3（概念观察，低优先级）

- **v86+Plan9 VM 壳**（browser-shell ★330）——概念参考（浏览器内 VM 隔离，Aegis 不适用）
- **CloakBrowser 反指纹**（★56，无内核源码不可验证）——不借鉴（已审计结论）

## 五、开发纪律（政府级）

1. **设计先行**：每个 P1/P2 优化点先出设计文档（可行性/限制/风险/收益）→ 门禁后才开发
2. **零风险优先**：不改变现有功能（拦截语义/业务逻辑）的优化先落地（P0 已示范）
3. **回归门禁**：每项开发后全量回归（语法/自检/ruff/mypy/bandit）→ 推送
4. **季度复核**：双目标复核（pytauri 复苏/pywebview 健康）时同步推进 P1 门禁项

## 六、信源清单（权威交叉比对）

- brave/adblock-rust（★2732，2026-08-14 更新，官方 Rust adblock 引擎）
- grisuno/FreeDom（★17，2026-08-15 更新，C 极简浏览器）
- ProxyShard/ShardBrowser（★641，anti-detect launcher）
- SalhaNabil/CloakBrowser（★56，anti-detect download，无内核源码）
- humphd/browser-shell（★330，Linux CLI shell in browser）
- samuelmaddock/electron-browser-shell（★725，minimal tabbed + Chrome extensions）
