# 支持功能（supported-features.md）

> 依据：蓝图 docs/product/supported-features + ADR-007/009 终局口径（2026-09-24
> 全面审计 WB-007/008 整改重写——此前版本仍称 legacy 为"真实载体"、称 C#
> "无书签/历史/多标签"，与 parity 清单 100% 勾验结果矛盾，属文档漂移）。
> **本表按代码现实维护。**

## 当前支持（按实际载体记录）

### Windows 正典栈（windows/——C#/.NET 10 + WebView2，ADR-009 唯一发布制品）

- 多标签（TabManager 事件闭环/InPrivate 无痕窗口/标签图标 Favicon 服务）、
  地址栏导航（经 Broker 决策 + 审计脱敏）、后退/前进/刷新/停止
- 书签（BookmarkBar 胶囊栏 + 收藏当前页）、历史（History 存储 + 搜索）、
  下载管理器（M3——经 broker 审计 + 危险拦截）、新标签页（导入向导已迁移至 NTP）
- KillSwitch（主窗口导航/下载/审批链；**NTP 宿主桥与前进/后退/重载等 6 个导航入口
  不查该开关**——第八轮实测）、设置窗口（威胁订阅源 URL 配置——刷新为启动一次性，无
  周期计时器）、主题配色、缩放策略（ZoomPolicy 0.25–3.0）
- 安全：导航确认审批、新窗口禁弹、权限默认拒绝、下载 fail-closed、
  URL 门禁（UrlSafety）、FingerprintShield 指纹防护、崩溃报告
- 策略裁决：Rust 原生策略核心（NativePolicyCoreBridge——**导航**裁决单源，ADR-008；
  能力评估层未接入 FFI 通路（H-7），动作裁决仍由 C# Broker 承担）

### Android（Kotlin/Compose——阶段 D）

- 导航经 broker 决策、地址栏/首页搜索框归一单源、多标签（含崩溃恢复）、
  SSL/HTTP/加载错误中文错误页（可重试/返回安全页）、引擎切换、
  壁纸、画板、贪吃蛇、下载（DownloadManager，文件名净化 + 危险扩展拦截）、
  WebView 版本检查提示、阅读模式入口、翻译入口
  （WB-152，2026-10-01 审计：原列「书签宫格」——Android 全树零 bookmark
  引用，功能不存在；书签/导入为 Windows 专属能力，见 start.js Host 能力面）
- 安全：AegisBridge 壳页来源校验、safe browsing、权限默认拒绝、cleartext 禁用

### Windows 归档栈（legacy/windows-pywebview——只读，ADR-009 D4 冻结纪律）

- 原全部浏览器功能（多标签/书签/导入/历史/搜索/壁纸/画板/贪吃蛇/下载提示等）
  保留为历史记录；**功能与安全修复一律不在该栈进行**——P0 安全缺陷仅经
  安全披露通道评估。下表安全机制（safe_url 双层校验/白名单/指纹前置注入等）
  已由正典栈对应实现承接。

## 明确不做

- Chromium fork / CEF 产品化 / 浏览器扩展生态
- 任意远程网页 native bridge / 网页工具栏 DOM 注入
- HTTP MCP server / Agent 自动下载/上传/导出 / 自动执行网页"指令"
- 云端同步密码 / 用户脚本 / 插件系统
- 主题/AI/同步（蓝图"先不做"清单）

## 已知缺口（诚实清单——2026-09-24 对齐 parity 清单）

- parity 代码项已 100% 勾验（`docs/product/feature-parity-checklist.md`）；
  残余缺口为 3 项**真机验收**（M2 数据闭环 / M3 下载画板 NTP / M4 全新机器
  全功能走查——随 2.2.0 发布流程执行，ADR-009 D5）
- 地址栏联想等蓝图"先不做"项见上节
