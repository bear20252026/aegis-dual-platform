# 信任边界威胁模型（trust-boundaries.md）

> 依据：蓝图 docs/threat-model/trust-boundaries + ADR-002（Capability Broker 唯一
> 副作用点）/ADR-003（禁止远程 native bridge）+ 阶段 C/D 落地（三信任域）。

## 信任域（蓝图最终路线——三个信任域）

| 信任域 | 内容 | 能力边界 |
|---|---|---|
| 远程网页域 | 不可信 renderer（互联网内容——脚本/iframe/重定向/下载） | 仅渲染——无 native bridge/无 MCP token/无本地命令/无标签全量读取（ADR-003） |
| 本地 chrome UI 域 | 按端分列（WB-121，2026-09-26 审计）：Windows C# 正典栈 = 受信虚拟主机两台（下表——非 file://）；Android = `file:///android_asset/` 本地资产页——展示/意图发起/确认 | 仅显示/提交意图——不持有全局后台权限（经 Broker 请求 action） |
| Capability broker 域 | 唯一产生本地副作用的边界（Windows/Android Broker） | 验证来源/会话/代际/scope/参数/预算/批准/nonce——没有 AuthorizedAction 不能产生副作用（ADR-002——default_deny） |

## 受信虚拟主机清单（Windows 正典栈——WebView2 SetVirtualHostNameToFolderMapping）

<!-- WB-213（2026-10-02 审计）：补 geo.aegis.local 行——原表只列 ntp 一台，
     画板虚拟主机的资产根映射/跨源 Deny 语义/信任假设失联 -->

| 虚拟主机 | 资产根映射 | 信任假设与跨源语义 |
|---|---|---|
| `https://ntp.aegis.local` | 发布输出 `ntp/` 目录（shared/shell 单源首页资产——start.html/css/js 等） | 受信壳页：桥能力仅顶层文档放行（`NtpAssets.IsTopLevelNtpDocument`——帧内嵌复用即拒）；远程页面 WebMessage 被宿主按来源关闭 |
| `https://geo.aegis.local` | 随包 GeoGebra 画板资源（`GeoGebra/HTML5/5.0/GeoGebra.html` 固定入口；资源未随包不映射——入口 fail-closed 置灰） | 离线画板信任假设：整包为随包静态资源、零运行时用户内容与网络请求；跨源 AccessKind=**Deny**（CS-334，2026-10-01 审计——远程页 fetch/热链探测一律失败，仅同源加载可用；防止任意站点探测识别 Aegis 用户） |

## 关键威胁与缓解

| 威胁 | 缓解（已落地） |
|---|---|
| 远程页面注入 native bridge → 本地命令（XSS→RCE） | 远程页面零桥能力（ADR-003——阶段 C/D——HostWebView/AegisWebViewClient 只事件转换） |
| 通用 bridge 网页输入升级为本地能力 | Broker 唯一副作用点（ADR-002——阶段 C/D——Default Deny） |
| 跨域导航/iframe/重定向绕过 | NavigationStarting/FrameNavigationStarting/NewWindowRequested 经 broker 真实取消（阶段 C） |
| 标签代际竞态（旧导航执行） | AuthorizedAction 绑定 document_generation（contracts action schema——代际变化失效） |
| 下载 MIME 混淆/危险内容 | 下载经 broker 判定（MIME/最终 URL/size/目录——阶段 C/D） |
| renderer crash 自动放行 | 错误页可见 + 恢复经 broker 重验（不自动放行——阶段 C/D） |
