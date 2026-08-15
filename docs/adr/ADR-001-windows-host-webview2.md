# ADR-001：Windows 宿主选择 C#/.NET 10 LTS + 原生 WebView2

- **状态：** Accepted（2026-08-16——按开发蓝图阶段 A——不可回退）
- **背景：** 当前 Windows 壳为 Python/pywebview（+ 未投入的 pytauri 适配）。专家审查确认 pywebview 不适合作为高保证 Windows 浏览器壳的长期安全边界（对 WebView2 原生导航取消/Frame 级策略/ContentLoading/host object 生命周期控制不够直接）。蓝图最终路线：Windows 收敛到 C#/.NET 10 LTS + 原生 WebView2。
- **决策：** Windows 主壳采用 C#/.NET 10 LTS（官方支持至 2028-11）+ 原生 WebView2 SDK（Microsoft 持续更新 Evergreen Runtime）。停止扩展 pywebview/pytauri 作为安全主壳；不维护第三套 Windows 壳。
- **后果：** 可直接使用 NavigationStarting/FrameNavigationStarting/WebResourceRequested/WebMessageReceived/ContentLoading/PermissionRequested 等原生事件做真实取消与策略执行；需处理 NewBrowserVersionAvailable（保存状态/通知/受控重启）；Windows/Android 共享逻辑通过 contracts 与测试向量，而非同语言。
