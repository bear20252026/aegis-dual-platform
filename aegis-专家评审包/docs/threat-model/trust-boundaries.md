# 信任边界威胁模型（trust-boundaries.md）

> 依据：蓝图 docs/threat-model/trust-boundaries + ADR-002（Capability Broker 唯一
> 副作用点）/ADR-003（禁止远程 native bridge）+ 阶段 C/D 落地（三信任域）。

## 信任域（蓝图最终路线——三个信任域）

| 信任域 | 内容 | 能力边界 |
|---|---|---|
| 远程网页域 | 不可信 renderer（互联网内容——脚本/iframe/重定向/下载） | 仅渲染——无 native bridge/无 MCP token/无本地命令/无标签全量读取（ADR-003） |
| 本地 chrome UI 域 | 固定 bundled origin（file://）——展示/意图发起/确认 | 仅显示/提交意图——不持有全局后台权限（经 Broker 请求 action） |
| Capability broker 域 | 唯一产生本地副作用的边界（Windows/Android Broker） | 验证来源/会话/代际/scope/参数/预算/批准/nonce——没有 AuthorizedAction 不能产生副作用（ADR-002——default_deny） |

## 关键威胁与缓解

| 威胁 | 缓解（已落地） |
|---|---|
| 远程页面注入 native bridge → 本地命令（XSS→RCE） | 远程页面零桥能力（ADR-003——阶段 C/D——HostWebView/AegisWebViewClient 只事件转换） |
| 通用 bridge 网页输入升级为本地能力 | Broker 唯一副作用点（ADR-002——阶段 C/D——Default Deny） |
| 跨域导航/iframe/重定向绕过 | NavigationStarting/FrameNavigationStarting/NewWindowRequested 经 broker 真实取消（阶段 C） |
| 标签代际竞态（旧导航执行） | AuthorizedAction 绑定 document_generation（contracts action schema——代际变化失效） |
| 下载 MIME 混淆/危险内容 | 下载经 broker 判定（MIME/最终 URL/size/目录——阶段 C/D） |
| renderer crash 自动放行 | 错误页可见 + 恢复经 broker 重验（不自动放行——阶段 C/D） |
