# 贡献指南（Contributing）

欢迎参与 Aegis 双端安全浏览器的开发！本项目为政府/严谨工程背景，代码质量与安全是最高优先级。请在贡献前阅读本指南与 [SECURITY.md](SECURITY.md)。

## 目录

- [代码规范](#代码规范)
- [提交规范](#提交规范)
- [分支与工作流](#分支与工作流)
- [质量门槛](#质量门槛)
- [评审清单](#评审清单)
- [问题与讨论](#问题与讨论)

## 代码规范

1. **单文件单职责**：每个文件只做一件事；不为了拆而拆，也不把无关逻辑堆进一个文件。
2. **行数红线**：新文件 ≤ 300 行（目标 100-200）；改造后文件 ≤ 500 行。任何文件触碰 500 行即应拆分。
3. **命名**（WB-071，审计 2026-09-23 清单·W5 批补 C# 口径）：Python 用 `snake_case`；Kotlin 用
   `camelCase`（类型 PascalCase）；C# 遵循 .NET 惯例——类型/方法/属性/常量 `PascalCase`，
   局部变量/参数 `camelCase`，私有字段 `_camelCase`（与 windows/ 现有代码一致）；新代码用英文
   标识符，保留既有中文注释。
4. **注释**：解释"为什么"，不解释"是什么"；重要设计决策在文件头 docstring 记录背景与理由。
5. **不引入不必要依赖**（WB-072，审计 2026-09-23 清单·W5 批补双栈口径——与 SECURITY.md
   「依赖与发布安全」一致）：优先标准库/平台内置。新增依赖必须：
   - Python：`requirements-ci.in` 顶层声明（SP-189，2026-10-01 审计更正——根目录
     并无 `requirements.txt`，活跃声明的单源是 `.in` 文件）+ `requirements-ci.txt`
     （pip-compile --generate-hashes 生成的 hash 锁）随批重锁并注明理由；
   - C#/NuGet（SP-177，2026-10-01 审计落地）：三个 csproj 已启用
     `RestorePackagesWithLockFile` 且 `packages.lock.json` 入库——CI/本地 restore
     与 publish 以 `--locked-mode` 消费（传递依赖变更必须随批更新锁文件），PR 说明新增理由；
   - Android/Gradle：无 lock 文件——PR 必须说明新增/升级理由并过 android-quality 门禁；
   - Rust：`Cargo.lock` 随改随更，`cargo build --locked`/`cargo audit` 门禁通过。

## 提交规范

使用 Conventional Commits：

```
<type>(<scope>): <subject>

<body>
```

- `type`: `feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `security`
- `scope`: `windows` / `android` / `shared` / `scripts` / `docs` 等
- 示例：`fix(windows): nav_queue 使用 partial 避免 lambda 捕获循环变量`

**每次修改要有记录、可回溯**：小步提交，一个提交只做一件事；禁止把无关改动混入同一提交。

## 分支与工作流

- 主分支：`master`（受保护，禁止直接推送）
- 新功能/修复：从 `master` 切出 `feat/<name>` 或 `fix/<name>` 分支，通过 Pull Request 合并
- 合并前必须通过全部质量门槛（见下）

## 质量门槛

> **云端验证纪律（WB-212，2026-10-02 审计补——最高优先级，与 CLAUDE.md
> 「验证纪律」节同源）**：本地环境仅用于代码编辑与 `git diff` 自查，
> **禁止在本地运行任何构建/测试/lint/SAST/验证命令**；改动推送 GitHub
> （audit 分支 → PR）后由 GitHub Actions 全套门禁验证，**Actions 结果是
> 唯一通过依据**（红灯迭代修复后再推，全绿才可合并）。下列命令仅作
> CI 同口径参考，按纪律本地不执行。

合并前必须全部通过（与 CLAUDE.md「关键命令」口径一致——WB-006 整改补全双栈）：

```bash
# —— Windows 正典栈（C#/.NET 10，ADR-009 唯一发布制品）——
cd windows
dotnet build src/Aegis.Windows.App/Aegis.Windows.App.csproj -r win-x64 -p:RestoreLockedMode=true   # 0 警告 0 错误——SP-220/S-03：-r 与 NuGet 锁一致，锁模式防改写
dotnet test tests/Aegis.Windows.Core.Tests -r win-x64 -p:RestoreLockedMode=true    # 核心套件全绿
dotnet test tests/Aegis.Windows.Broker.Tests -r win-x64 -p:RestoreLockedMode=true  # Broker 套件全绿

# —— Rust 策略核心 ——
cd ../core/rust-policy-core
# SP-183（2026-10-01 审计）：clippy 口径与 CI 统一——--all-features --all-targets -D warnings
# S-06（2026-10-02 审计）：补 --locked（test 另补 --all-features）——与 core-rust.yml 逐字同口径
cargo test --locked --all-features && cargo clippy --locked --all-features --all-targets -- -D warnings && cargo fmt --check  # 全绿 + 0 警告

# —— 契约/版本/UI 回归门禁（回到仓库根执行；SP-163：node 21+ glob 展开——
#    新测试文件入目录即入门禁，Windows 本地与 ci.yml 一致）——
cd ../..
python validate_release.py                        # AST/JSON/XML 静态验证
python scripts/verify_versions.py                 # 版本单源一致性
python contracts/codegen/verify_bridge_guard.py   # Bridge 守卫单一事实源（ADR-007）
node --test "tests/ui-regression/*.test.mjs"    # UI 回归
node shared/shell/snake.test.js                   # 贪吃蛇逻辑回归
python -m pytest tests/python/ -q                 # 发布链离线单测

# —— contracts.yml 五脚本（WB-209，2026-10-02 审计补——契约门禁此前漏列，
#    与 .github/workflows/contracts.yml 同口径）——
python scripts/verify_release_schema.py                    # release.json 全 schema 校验（PY-102）
python scripts/verify_vectors.py                           # 契约 JSON 与预期决策校验（PY-064）
python contracts/codegen/validate_vector_schemas.py        # 向量对 JSON Schema 校验（PY-013）
python contracts/codegen/analyze_action_catalog.py         # action-catalog 静态分析门禁（PY-015）
python contracts/codegen/generate_csharp.py && \
python contracts/codegen/generate_kotlin.py && \
python contracts/codegen/verify_contract_compatibility.py  # 重生成 + 兼容性验证

# —— Agent 红队（WB-209 补——agent-redteam.yml 同口径）——
python -m pytest agent/tests -q

# —— Android 端（四模块与 android-quality.yml 一致——WB-116 对齐 CI）——
cd android
./gradlew.bat :app:ktlintCheck :broker:ktlintCheck :webview-adapter:ktlintCheck :contracts:ktlintCheck
./gradlew.bat :app:detekt :broker:detekt :webview-adapter:detekt :contracts:detekt
./gradlew.bat :app:lintDebug                      # Android Lint（0 错误）
./gradlew.bat :broker:testDebugUnitTest :app:testDebugUnitTest :webview-adapter:testDebugUnitTest

# —— legacy 归档栈（只读——禁止在此修复，仅归档基线参考）——
# python3 validate_release.py / ruff / bandit / mypy 仅在触及归档目录时运行
```

契约重生成 + 漂移门禁（WB-210，2026-10-02 审计补——触及 contracts/codegen
模板或其输入时必跑；与 contracts.yml「Regenerate jsapi schema and fail on
drift」「Fail if generated bindings are stale」两步同口径——生成物过期即红）：

```bash
python contracts/codegen/generate_csharp.py       # 重生成 C# 绑定
python contracts/codegen/generate_kotlin.py       # 重生成 Kotlin 绑定
python scripts/gen_jsapi_schema.py                # 重生成 jsapi schema（PY-014）
git diff --exit-code -- shared/jsapi-schema.json \
  windows/src/Aegis.Windows.App/Contracts/Generated \
  android/contracts/src/main/kotlin/com/aegis/contracts/generated   # 有 diff = 生成物过期 → 门禁红
python contracts/codegen/verify_contract_compatibility.py   # 契约兼容性验证
python contracts/codegen/verify_bridge_guard.py             # 守卫 JS 单源（ADR-007）
```

改动所涉技术栈的检查必须全过；**不允许**为通过检查而删除、注释或弱化已有测试与断言（"修好"而非"藏好"）。

## 评审清单

提交 PR 前自查：

- [ ] 是否通过全部质量门槛（见上）
- [ ] 是否保持单文件单职责与行数红线
- [ ] 是否更新了 [CHANGELOG.md](CHANGELOG.md)
- [ ] 是否涉及安全敏感路径（URL 过滤/密码/下载/权限）并补充了安全考虑
- [ ] 新增逻辑是否落在对应端的测试套件（SP-190，2026-10-01 审计更正——
  C# 两套件 / Kotlin 单测 / Node UI 回归 / `tests/python` pytest；
  `selftest_*.py` 仅属 legacy 归档栈 P0 评估通道，不再要求新增——WB-155/190）
- [ ] 是否保持 Windows/Android 双端决策一致（WB-033，审计 2026-09-23 清单·W5 批：
  架构决策口径以 **ADR 索引 `docs/adr/`**（ADR-001..009）为单源——正典栈/能力
  broker/无远程 native bridge/Rust 单一裁决等；此前指向的 README「当前决策记录」
  节已不存在）

## 问题与讨论

- Bug / 安全漏洞：**不要**在公开 Issue 描述可利用细节，先联系维护者或走 [SECURITY.md](SECURITY.md) 的披露流程
- 功能讨论 / 设计：GitHub Discussions 或 Issue 讨论
- 安全问题涉及认证/凭据时：仅通过安全渠道沟通，绝不在 Issue 中粘贴 token、密钥或证书

## 行为准则

保持专业与协作：评审聚焦代码而非个人；不同意见以证据与可验证测试为准。本项目为严谨工程，宁慢勿错。
