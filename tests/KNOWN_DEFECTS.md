# 已知缺陷回归用例库（KNOWN_DEFECTS）

> 每次修复一个缺陷，必须：①在本表登记；②在 `tests/ui-regression/start_page.test.mjs`
> 增加对应断言（BUG-XXX）；③CI `ui-regression` job 自动纳入回归范围。
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

## 测试分层与门禁

| 层级 | 内容 | 触发点 | 阻断 |
|------|------|--------|------|
| 单元 | selftest_*.py（Windows 桥）、broker JVM 测试 | ci.yml python-checks / android 构建 | ✅ |
| UI 回归 | tests/ui-regression（已知缺陷断言，node:test） | ci.yml ui-regression（每次 push/PR） | ✅ |
| 静态门禁 | validate_release / ruff / mypy / bridge_guard / detekt / ktlint | ci.yml + android-quality.yml | ✅ |
| 端到端 | scripts/e2e-android-search.sh（需真机：装/启/搜/退） | 手动或自建设备 runner（REQUIRES_DEVICE 跳过） | 报告 |
| 发布门禁 | verify_versions + checksum/attestation 校验 + 入口断言 | release-*.yml | ✅ |

## 报告与告警

- CI 每个 job 输出 TAP/摘要；**任何 job 失败 = GitHub Run 红 = 阻断合并/发布**
- E2E 失败输出 `[e2e][FAIL]` 行 + 截图（/tmp/e2e_after.png）人工复核
- 新缺陷修复流程：修复 → 本库登记 → 断言入库 → CI 永久回归

| BUG-011 | Android 地址栏贪吃蛇完全不动（滑动无效） | `tick` 状态只在循环自增、从未在组合中读取——Canvas 读的 `game` 引用不变，Compose 永不重绘，蛇视觉冻结 | `neverEqualPolicy` + 每 tick 重赋 `game` 强制重绘 | AddressBarSnake.kt |
| BUG-012 | 首页返回按钮双端缺失/贪吃蛇 Win 缺失 | 返回键只存在于 Win 原生工具栏；贪吃蛇为 Android Compose 独占 | start.html 单源内置返回按钮（Host.goBack 分发）+ 贪吃蛇游戏（键盘/滑动双控），双端一致 | shared/shell/start.html, AegisHomeBridge.kt |
