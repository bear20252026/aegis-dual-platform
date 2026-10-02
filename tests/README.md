# tests/ —— 回归测试分层说明（SP-137，审计 2026-09-23 清单·SP1 批）

本目录是仓库回归测试的入口。缺陷→登记→断言→CI 永久回归的闭环流程见
`KNOWN_DEFECTS.md`（新缺陷修复必须：①登记 ②断言入库 ③CI 自动纳入）。

## 分层一览

| 目录/文件 | 层级 | 运行方式 | 覆盖面 |
|-----------|------|----------|--------|
| `python/` | 发布链与脚本门禁单测 | `py -m pytest tests/python/ -q` | release/ 工具链（verify_artifact_set/verify_manifest/verify_provenance/generate_sbom）、update_verifier、build_metadata、scripts 门禁（verify_vectors/verify_release_schema 等）、contracts codegen/catalog |
| `ui-regression/` | 已知缺陷 UI 回归（node:test） | `node --test "tests/ui-regression/*.test.mjs"` | `shared/shell/` 单源首页的缺陷断言面（BUG-*）与 WB 系列行为/ARIA 断言 |
| `KNOWN_DEFECTS.md` | 缺陷登记库（文档） | ——（被上面两层引用） | BUG-NNN 登记/根因/回归断言/修复 账本 |
| `../shared/shell/snake.test.js` | 贪吃蛇逻辑回归（独立 assert runner——WB-196，2026-10-02 审计更正：非 node:test，自研 test()/计数 runner） | `node shared/shell/snake.test.js` | start.snake.js 单源游戏逻辑 |
| `../agent/tests/` | 红队端到端（pytest） | `python -m pytest agent/tests -q` | broker default-deny：注入/投毒/重放/预算/会话/代际/撤销全拒绝 |
| `../windows/tests/` | C# 双套件（Core.Tests / Broker.Tests——WB-207，2026-10-02 审计补行） | `dotnet test`（带 `-r win-x64 -p:RestoreLockedMode=true`，见 CLAUDE.md）｜CI：contracts.yml 构建验证 + release-windows.yml | Windows 正典栈回归 |
| `../android/`（app/broker/webview-adapter 的 src/test） | Android 单测（WB-207 补行；contracts 模块无独立测试源码，ktlint/detekt 四模块覆盖） | `./gradlew.bat :broker:testDebugUnitTest :app:testDebugUnitTest :webview-adapter:testDebugUnitTest`｜CI：android-quality.yml | Kotlin 端回归 |
| `../core/rust-policy-core/tests/` | Rust 单测 + 跨语言契约向量（vectors.rs——WB-207 补行） | `cargo test --locked --all-features`｜CI：core-rust.yml；向量另经 `python scripts/verify_vectors.py` 逐条校验（contracts.yml） | Rust 策略核心 + 契约向量 |

## ui-regression 断言面拆分（WB-124）

- `start_page.test.mjs` —— 页面结构/资源/打包链（含 Android MainActivity 静态断言）
- `start_host.test.mjs` —— Host 适配层通用语义（kind()/has()/能力面）
- `start_main.test.mjs` —— 主逻辑（壁纸/书签/恢复）
- `start_import.test.mjs` —— 导入向导
- `import_contract.test.mjs` —— 导入桥契约（与 helpers.mjs 单一事实源）
- `helpers.mjs` —— 共享桩（cs 桥/chrome 桩——勿在用例内复制）
- `defect_registry.test.mjs` —— 缺陷库↔断言面互检 lint（SP-044）

## CI 接线

- `ui-regression` job（.github/workflows/ci.yml）：每次 push/PR 跑全部
  `tests/ui-regression/*.test.mjs`（glob 发现式——新增测试文件自动纳入）
  与贪吃蛇回归；失败即红。
- python 单测在 CI 质量门禁内运行；agent 红队测试由 agent-redteam workflow 承担。
