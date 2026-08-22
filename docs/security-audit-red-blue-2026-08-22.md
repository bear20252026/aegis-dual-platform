# Aegis 红蓝对抗安全审计报告

> 审计时间：2026-08-22
> 审计角色：红方（攻击）+ 蓝方（防御）
> 审计范围：JS 注入、WebView2、Bridge、指纹防护

---

## 红方发现的漏洞

### 漏洞 1：JS 注入时序缺陷（严重）

**位置**：bridge_hooks.py → on_loaded()
**问题**：指纹防护 JS 在页面加载完成后注入（`on_loaded` 回调），但页面 JS 在加载过程中就能调用原始 API（如 `toDataURL`、`getParameter`），在防护生效前捕获真实指纹。
**攻击方式**：页面内联 `<script>` 在 DOMContentLoaded 前调用 `canvas.toDataURL()`，获取未加噪声的真实指纹。
**根因**：架构缺陷——注入时机依赖页面加载完成事件，而非 WebView 创建时。

### 漏洞 2：fetch 覆盖链断裂（严重）

**位置**：fingerprint_pipeline.py Stage 5 + Stage 9
**问题**：Stage 5（QueryStripper）覆盖 `window.fetch`，Stage 9（ExtProxy）再次覆盖 `window.fetch`——后者直接调用 `origFetch`（Stage 5 的版本），但 Stage 9 的 `origFetch` 捕获的是 Stage 5 覆盖前的原始 fetch，导致 QueryStripper 的参数剥离失效。
**攻击方式**：页面发起含 `fbclid` 参数的 fetch 请求，Stage 5 的剥离被 Stage 9 绕过。
**根因**：架构缺陷——多个阶段各自独立覆盖同一 API，没有链式调用机制。

### 漏洞 3：WebGL 双重覆盖（中等）

**位置**：fingerprint_pipeline.py Stage 3 + Stage 7
**问题**：Stage 3 覆盖 `getParameter` 返回 `'ANGLE (Aegis)'`，Stage 7 再次覆盖 `getParameter` 返回 `'Google Inc. (Intel)'`——后者捕获的 `orig` 是 Stage 3 的版本，但 Stage 7 的 `orig.call(this, p)` 会调用 Stage 3 的逻辑，导致双重代理。
**攻击方式**：指纹脚本通过 `getParameter.toString()` 检测到代理层。
**根因**：架构缺陷——两个阶段各自独立覆盖同一 API，没有合并机制。

### 漏洞 4：javascript: URL 绕过（中等）

**位置**：bridge_hooks.py → link_intercept_js
**问题**：链接拦截允许 `javascript:` URL 通过（`if (a.href.startsWith('javascript:')) return;`），恶意页面可通过 `javascript:` 链接执行任意 JS。
**攻击方式**：页面构造 `<a href="javascript:alert(document.cookie)">` 绕过拦截。
**根因**：设计缺陷——`javascript:` URL 被视为"安全"而放行。

### 漏洞 5：toStringGuard 全局暴露（低）

**位置**：fingerprint_pipeline.py Stage 1
**问题**：`__AEGIS_REGISTER_PROXY` 全局可访问，恶意脚本可调用它注册自己的代理函数，伪装成原始函数。
**攻击方式**：恶意脚本调用 `__AEGIS_REGISTER_PROXY(fakeFunc, origFunc)` 注册伪造函数。
**根因**：架构缺陷——注册接口暴露在全局作用域。

---

## 蓝方架构级修复方案

### 修复 1：注入时序 → WebView2 AddScriptToExecuteOnDocumentCreated

**方案**：将指纹防护 JS 注入从 `on_loaded`（页面加载后）改为 WebView2 的 `AddScriptToExecuteOnDocumentCreated`（页面脚本执行前）。
**效果**：防护在任何页面 JS 执行前生效，无法被绕过。

### 修复 2：fetch 链式调用 → 责任链模式

**方案**：所有 fetch 覆盖使用统一的链式注册机制——每个阶段注册自己的处理函数，由统一的 dispatcher 按顺序调用。
**效果**：多个阶段的 fetch 处理不会互相覆盖。

### 修复 3：WebGL 合并覆盖 → 单一代理 + 参数表

**方案**：Stage 3 和 Stage 7 合并为单一 `getParameter` 代理，使用参数表返回不同值。
**效果**：只有一层代理，无法被 toString 检测。

### 修复 4：javascript: URL → 完全拦截

**方案**：移除 `javascript:` URL 放行逻辑，所有非锚点链接都在浏览器内导航。
**效果**：消除 javascript: URL 绕过向量。

### 修复 5：toStringGuard → 闭包封装

**方案**：将 `__AEGIS_REGISTER_PROXY` 从全局移到闭包内，外部无法访问。
**效果**：恶意脚本无法调用注册接口。
