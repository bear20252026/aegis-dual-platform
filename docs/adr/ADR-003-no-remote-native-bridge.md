# ADR-003：禁止远程页面 Native Bridge

- **状态：** Accepted（2026-08-16——按开发蓝图阶段 A——不可回退）
- **背景：** 当前工具栏脚本注入每个已加载页面并暴露 pywebview.api（含导航/标签/分组等桥写操作）——远程页面可控制浏览器 UI。Microsoft WebView2 安全指南要求将 Web 内容视为不可信、验证来源、避免通用代理、在导航后移除 host object。蓝图：远程网页域只渲染内容——无 native bridge/无 MCP token/无本地命令/无标签全量读取。
- **决策：** 远程页面一律无 native bridge——不注入任何 host object/命令；网页工具栏 DOM 注入永久移除（不做清单）。本地 chrome UI 使用固定 bundled origin（file://），仅该 origin 经强类型 IPC 与 Broker 交互。迁移期间（P1-1 过渡）7 个桥写操作已强制来源校验（远程拒绝）。
- **后果：** 消除 XSS→RCE 路径（远程页面注入 + 高权限 host object）；远程内容能力面为零；原生确认 UI 展示目标 Origin/方法/路径/敏感范围/过期时间。
