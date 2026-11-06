# ADR-001：Windows 宿主选择 C#/.NET 10 LTS + 原生 WebView2

- **状态：** Accepted（2026-08-16——按开发蓝图阶段 A——不可回退）
- **背景：** 当前 Windows 壳为 Python/pywebview（+ 未投入的 pytauri 适配）。专家审查确认 pywebview 不适合作为高保证 Windows 浏览器壳的长期安全边界（对 WebView2 原生导航取消/Frame 级策略/ContentLoading/host object 生命周期控制不够直接）。蓝图最终路线：Windows 收敛到 C#/.NET 10 LTS + 原生 WebView2。
- **决策：** Windows 主壳采用 C#/.NET 10 LTS（官方支持至 2028-11）+ 原生 WebView2 SDK（Microsoft 持续更新 Evergreen Runtime）。停止扩展 pywebview/pytauri 作为安全主壳；不维护第三套 Windows 壳。
- **后果：** 可直接使用 NavigationStarting/FrameNavigationStarting/WebResourceRequested/WebMessageReceived/ContentLoading/PermissionRequested 等原生事件做真实取消与策略执行；需处理 NewBrowserVersionAvailable（保存状态/通知/受控重启）；Windows/Android 共享逻辑通过 contracts 与测试向量，而非同语言。
- **Runtime 更新实现（2026-11-05）：** 完整实现 `RuntimeUpdater.cs` + `RuntimeRestartStateStore.cs`，覆盖 ADR-001 后果段全部要求：
  - **事件订阅**：MainWindow 构造时异步订阅共享环境的 `NewBrowserVersionAvailable` 事件
  - **状态保存**：事件触发时写入 `runtime-restart.json`（重启原因、时间戳、版本）
  - **UI 通知**：显示蓝色横幅（RuntimeUpdateBanner），用户可点击「重启以应用」或「稍后」
  - **受控重启**：点击重启按钮时强制刷盘会话 → 标记重启状态 → 关闭应用 → 启动新实例
  - **状态恢复**：应用启动时检测重启标记，显示恢复提示并清除标记
  - **测试覆盖**：10 个 RuntimeUpdater 测试 + 8 个 RuntimeRestartStateStore 测试
