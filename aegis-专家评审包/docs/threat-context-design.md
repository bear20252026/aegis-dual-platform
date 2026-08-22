# 威胁拦截六维上下文设计文档（threat-context-design）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> 借鉴来源：brave adblock 引擎 `Request::preparsed` 六维请求上下文
> （KNOWLEDGE_BASE 第 15 节）
> 原则：政府级小心严谨——设计先行、WebView2 能力求证、门禁决策

---

## 〇、结论速览

**六维中 Aegis 当前可落地 3 维（URL/hostname/method）、部分可推断 1 维（request_type 经 Content-Type）、受限 2 维（initiator/third_party）**。落地分两步：**① 上下文记录增强**（零风险，增强可观测性，不改变拦截语义）→ **② 拦截语义调整**（区分子资源/第三方，需本机实测 WebView2 request_sent 能力后门禁决策）。

## 一、六维上下文（brave 映射 Aegis）

| 维度 | brave（Request::preparsed） | Aegis 现状 | 可落地性 |
|---|---|---|---|
| URL | 完整 URL 匹配 | 导航层 url 完整（_is_navigation_safe_url） | ✅ 已有 |
| hostname | 域名匹配 | host_is_blocked（精确/子域） | ✅ 已有 |
| initiator | 发起者主机 | ❌ WebView2 request_sent 不暴露 | ⚠️ 受限 |
| request_type | 资源类型（document/image/script） | 可经请求头 Content-Type 推断（统一管线） | 🟡 部分 |
| third_party | 第三方（跨域发起） | ❌ 需 initiator 对比，受限 | ⚠️ 受限 |
| method | HTTP 方法（GET/POST） | 统一管线可获取请求方法 | ✅ 可增强 |

## 二、WebView2/pywebview 能力求证（大胆求证）

| 能力 | pywebview 6.2.1（request_sent） | 结论 |
|---|---|---|
| 改请求头 | ✅ 支持（headers 参数） | 统一管线已有（DNT/威胁标记） |
| 获取 URL/host | ✅ 支持 | 已有 |
| 获取请求方法 | ✅ 支持（args 含 method） | 可增强 |
| 获取 Content-Type | ✅ 支持（args） | request_type 可推断（image/script 等） |
| 获取 initiator/third_party | ❌ 不暴露（WebView2 拦截层限制） | 记录限制 |

## 三、风险/收益评估（小心严谨）

### 收益
1. **拦截精确性**：区分文档导航 vs 子资源请求——如威胁域名仅拦子资源、文档导航走严格检查（降低误拦、防绕过）
2. **可观测性**：拦截日志含上下文（谁发起的什么类型请求被拦）——威胁研判更准

### 风险
1. **WebView2 能力边界**：initiator/third_party 不可得——实现需明确边界（文档中声明）
2. **拦截语义调整有误拦风险**（政府级红线）——须门禁：本机实测 request_sent 的 method/Content-Type 可得性 → 设计拦截规则 → 回归验证 → 才改语义

## 四、落地建议（两步走）

### 第 1 步（零风险，本次落地）：上下文记录增强
- 统一拦截管线（_apply_request_policy）记录：method + Content-Type 推断的 request_type 到威胁日志
- **不改变拦截语义**（纯可观测性增强）——零风险，无门禁障碍

### 第 2 步（门禁后）：拦截语义调整
- 前置：本机实测 request_sent 的 method/Content-Type 可得性（测试脚本）
- 设计：威胁域名分类拦截（document 导航严格/子资源宽松）——语义变化，需回归验证
- 门禁：实测通过 + 回归全绿 + 本机验证后才实施

## 五、结论

六维上下文借鉴分两步落地：**本次先落地零风险的"上下文记录增强"**（政府级小心严谨——不改变拦截语义），拦截语义调整（区分资源类型）受 WebView2 能力边界约束，留待本机实测门禁后决策。
