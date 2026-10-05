# ADR-003：禁止远程页面 Native Bridge

- **状态：** Accepted（2026-08-16——按开发蓝图阶段 A——不可回退）
- **背景：** 当前工具栏脚本注入每个已加载页面并暴露 pywebview.api（含导航/标签/分组等桥写操作）——远程页面可控制浏览器 UI。Microsoft WebView2 安全指南要求将 Web 内容视为不可信、验证来源、避免通用代理、在导航后移除 host object。蓝图：远程网页域只渲染内容——无 native bridge/无 MCP token/无本地命令/无标签全量读取。
- **决策：** 远程页面一律无 native bridge——不注入任何 host object/命令；网页工具栏 DOM 注入永久移除（不做清单）。本地 chrome UI 使用固定 bundled origin（file://），仅该 origin 经强类型 IPC 与 Broker 交互。迁移期间（P1-1 过渡）7 个桥写操作已强制来源校验（远程拒绝）。
- **后果：** 消除 XSS→RCE 路径（远程页面注入 + 高权限 host object）；远程内容能力面为零；原生确认 UI 展示目标 Origin/方法/路径/敏感范围/过期时间。

---

## 现状注记（第八轮 B8，2026-10-05）——原则仍生效，实现细节已被取代

- **不可回退的原则仍生效**：远程页面一律无 native bridge，Windows 侧远程文档的
  WebMessage 按来源关闭，Android 侧 `allowedOriginRules` 之外的壳页来源校验在
  `AegisBridge` 承担（第八轮实测：Android 那一项仍有 `setOf("*")` 的过宽形态，
  已登记 R8-AD 队列，不属本 ADR 的静默失效）。
- **本 ADR 的两条实现口径已过期，不构成对本 ADR 的违反**：
  1. 「本地 chrome UI 使用固定 bundled origin（`file://`）」——正典栈改为
     **WebView2 虚拟主机** `https://ntp.aegis.local/start.html`
     （`NtpBridgeFactory` 显式登记 + `IsTopLevelNtpDocument` 顶层文档门禁），
     理由是 `file://` 下无法建立可校验的 https 语义与 CSP；见
     `docs/audit/full-audit-2026-10-04-round8.md` 第十节第 3 条。
  2. 「背景」段描述的是 2026-08-16 的 pywebview 双栈期（工具栏 DOM 注入 +
     `pywebview.api`）——该栈已随 ADR-009 只读冻结归档。
- **仍成立的缺口**：本 ADR「后果」段承诺的「原生确认 UI 展示 Origin/方法/路径/
  敏感范围/过期时间」在 Windows 出货构建里**未启用**（导航确认门未置位），
  第八轮 B4 已把该形态从静默取消改为用户可见拒绝——确认流本身仍待产品裁决
  （第八轮台账 §七 1）。
