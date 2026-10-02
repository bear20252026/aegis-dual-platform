# 已知缺陷回归用例库（KNOWN_DEFECTS）

> 每次修复一个缺陷，必须：①在本表登记；②按缺陷归属在 `tests/ui-regression/`
> 对应文件增加断言（WB-124，2026-09-26 审计——断言面已由单文件拆为多文件：
> 页面结构/资源 → `start_page.test.mjs`；Host 适配层通用语义 →
> `start_host.test.mjs`；导入桥契约 → `import_contract.test.mjs`；主逻辑
> （壁纸/书签/恢复）→ `start_main.test.mjs`；导入向导 → `start_import.test.mjs`；
> 贪吃蛇逻辑 → `shared/shell/snake.test.js`）；③CI `ui-regression` job
> 自动纳入回归范围。
> 断言失败 = 门禁阻断（.github/workflows/ci.yml → ui-regression）。

| ID | 现象 | 根因 | 回归断言 | 修复 |
|----|------|------|----------|------|
| BUG-001 | 启动即崩「无法注册安全浏览会话」 | `View.setTag(generateViewId(),…)`——generateViewId 的 package id=0x01（framework 区段），setTag(int) 要求 ≥0x02 | start.html 不得含 setTag；Android 端 WeakHashMap 注册表 | `3d2c421` |
| BUG-002 | 搜索回车无响应 | 中文 IME「前往/搜索」action 不发 keydown Enter | form onsubmit + type=search + enterkeyhint 存在 | `42fcb40` |
| BUG-003 | 搜索框 UI 错乱（placeholder/按钮溢出） | form 块级元素打断 .search flex 行 | #searchForm flex 样式断言 | `8afc99e` |
| BUG-004 | 手机端首页壁纸缺失 | APK assets 从未打包壁纸图片（引用全 404） | wallpapers 文件存在 + 被引用 | `6e9b2f7` |
| BUG-005 | 画板按钮跳转失效（两次） | ①CI 步骤被前置 grep 静默短路未写入；②策略级 require_confirmation 在确认开关关闭后被 fail-closed 拒绝 | geoBtn/Host.openGeo/双端打包配置/入口断言 | `6e9b2f7`+`c210567`+本轮 |
| BUG-006 | 启动闪退（allowedOriginRules） | AndroidX 不接受 `https://*` 通配 | 不得出现该规则写法 | `623c8bc` |
| BUG-007 | 移动端按桌面宽度渲染 | 缺 viewport meta | viewport 断言 | `6e9b2f7` |
| BUG-008 | 宿主桥调用漂移（多副本直调） | 两份 start.html 并行 + pywebview 直调散落 | 无 pywebview 直调；Host 层存在且被使用 | `6e9b2f7` |
| BUG-009 | 部分设备/文件协议下搜索回车仍无响应（submit 不触发） | file:// 页面 form submit 事件可能不派发（仅依赖 submit 单路径——WB-064/SP-039 补登记：此前被 start.html/start.main.js 注释引用却未在本库登记行） | BUG-002 断言含双路径锁定：form submit + 按钮 click 都必须直调 go()（start_page.test.mjs「搜索按钮必须 click 直调」） | start.main.js wireStaticHandlers（submit+click 双保底） |
| BUG-011 | Android 地址栏贪吃蛇完全不动（滑动无效） | `tick` 状态只在循环自增、从未在组合中读取——Canvas 读的 `game` 引用不变，Compose 永不重绘，蛇视觉冻结 | 贪吃蛇渲染循环节拍断言（单源 `shared/shell/start.snake.js`） | 已修——载体由已删除的 AddressBarSnake.kt 迁至 start.snake.js（SP-007 纠正） |
| BUG-012 | 首页返回按钮双端缺失/贪吃蛇 Win 缺失 | 返回键只存在于 Win 原生工具栏；贪吃蛇为 Android 独占 | 返回形态统一后（95d9bac）改为反向锁定：HTML/CSS 无 back-fab 残留（返回由平台 chrome 承担）+ Host.goBack 适配能力保留 + 贪吃蛇双端单源断言（start_page.test.mjs——WB-157，2026-10-01 审计改述：原描述「单源内置返回按钮」与现行断言相反） | `shared/shell/start.html` |
| BUG-013 | 手势导航设备上边缘滑动/返回键直接退出应用（回退从未生效） | targetSdk 36 起系统默认经 OnBackInvokedCallback 分发返回事件——onKeyDown(KEYCODE_BACK) 在手势导航设备上永远收不到；此前"验证通过"实为误读（进程存活 ≠ Activity 存活，截图实为桌面） | OnBackPressedCallback 接管断言（手势/按键双路径） | `MainActivity.kt` |
| BUG-014 | 贪吃蛇版本替换残留（旧地址栏版未清）+ 最高分不持久化 | 地址栏版迁首页全屏版时旧实现（AddressBarSnake.kt 与 MainActivity 调用）残留；新版本最高分只存内存——重开即清零（SP-040 补登记：此前被 start_page.test.mjs「BUG-014 版本替换」断言引用却未在本库登记行） | snakeBest 最高分显示 + localStorage 持久化 + 全屏覆盖层样式 + AddressBarSnake.kt 必须已删除（start_page.test.mjs） | `shared/shell/start.snake.js` |

> **SP-087（审计 2026-09-23 清单·SP1 批）编号注记**：BUG-010 编号保留空缺——
> 历史登记序列跳号（无对应缺陷内容流传），后续登记继续沿用序列不回收该号。

## 测试分层与门禁

| 层级 | 内容 | 触发点 | 阻断 |
|------|------|--------|------|
| 单元 | C# Core.Tests / Broker.Tests（单轨正典主单元面，dotnet build+test）、Rust cargo test、broker/app/webview-adapter JVM 单测（testDebugUnitTest）；selftest_*.py 为 legacy 归档守护（SP-041/SP-151 口径——单元层主口径随 C# 单轨迁移，归档自检移独立低频守护） | contracts.yml（dotnet build+test + cargo test）/ android-quality.yml（gradle 单测）/ legacy-python-guard.yml（selftest，周 cron） | ✅ |
| UI 回归 | tests/ui-regression（已知缺陷断言，node:test） | ci.yml ui-regression（每次 push/PR——WB-158，2026-10-01 审计改挂：ci.yml 仅剩本 job） | ✅ |
| 静态门禁 | validate_release / ruff / mypy（活跃树+归档栈）、bridge_guard、detekt / ktlint | legacy-python-guard.yml（validate_release/ruff/bandit/mypy）+ contracts.yml（bridge_guard/verify_*）+ android-quality.yml（ktlint/detekt）——WB-158 改挂：原「ci.yml + android-quality.yml」中 ci.yml 已不含静态工具 | ✅ |
| 端到端 | scripts/e2e-android-search.sh（需真机：装/启/搜/退） | 手动或自建设备 runner（REQUIRES_DEVICE 跳过） | 报告 |
| 发布门禁 | verify_versions + checksum/attestation 校验 + 入口断言 | release-*.yml | ✅ |

> **SP-088（审计 2026-09-23 清单·SP1 批）跳过语义注记**：端到端层的
> "REQUIRES_DEVICE 跳过"= 检测到无真机环境时以 **exit 0（跳过不阻断）**
> 结束并打印 skip 报告——真机执行失败才输出 `[e2e][FAIL]`（该层不阻断
> CI，失败转人工复核）。其余四层跳过/失败语义见各行"阻断"列。

## 报告与告警

- CI 每个 job 输出 TAP/摘要；**任何 job 失败 = GitHub Run 红 = 阻断合并/发布**
- E2E 失败输出 `[e2e][FAIL]` 行 + 截图（/tmp/e2e_after.png）人工复核
- 新缺陷修复流程：修复 → 本库登记 → 断言入库 → CI 永久回归
