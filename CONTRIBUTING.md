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
3. **命名**：Python 用 `snake_case`，Kotlin 用 `camelCase`；新代码用英文标识符，保留既有中文注释。
4. **注释**：解释"为什么"，不解释"是什么"；重要设计决策在文件头 docstring 记录背景与理由。
5. **不引入不必要依赖**：优先标准库；新增依赖必须在 `requirements.txt` 锁版本并注明理由。

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

合并前必须全部通过（与 CLAUDE.md「关键命令」口径一致——WB-006 整改补全双栈）：

```bash
# —— Windows 正典栈（C#/.NET 10，ADR-009 唯一发布制品）——
dotnet build src/Aegis.Windows.App/Aegis.Windows.App.csproj   # 0 警告 0 错误
dotnet test tests/Aegis.Windows.Core.Tests                    # 核心套件全绿
dotnet test tests/Aegis.Windows.Broker.Tests                  # Broker 套件全绿

# —— Rust 策略核心 ——
cargo test && cargo clippy --all-targets && cargo fmt --check  # 全绿 + 0 警告

# —— 契约/版本/UI 回归门禁（仓库根）——
python validate_release.py                        # AST/JSON/XML 静态验证
python scripts/verify_versions.py                 # 版本单源一致性
python contracts/codegen/verify_bridge_guard.py   # Bridge 守卫单一事实源（ADR-007）
node --test tests/ui-regression/*.test.mjs        # 单源首页 UI 回归
python -m pytest tests/python/ -q                 # 发布链离线单测

# —— Android 端 ——
./gradlew.bat :app:lintDebug                      # Android Lint（0 错误）
./gradlew.bat :app:testDebugUnitTest              # 单元测试（含 ktlint/detekt 门禁）

# —— legacy 归档栈（只读——禁止在此修复，仅归档基线参考）——
# python3 validate_release.py / ruff / bandit / mypy 仅在触及归档目录时运行
```

改动所涉技术栈的检查必须全过；**不允许**为通过检查而删除、注释或弱化已有测试与断言（"修好"而非"藏好"）。

## 评审清单

提交 PR 前自查：

- [ ] 是否通过全部质量门槛（见上）
- [ ] 是否保持单文件单职责与行数红线
- [ ] 是否更新了 [CHANGELOG.md](CHANGELOG.md)
- [ ] 是否涉及安全敏感路径（URL 过滤/密码/下载/权限）并补充了安全考虑
- [ ] 是否补充/更新了自检脚本（`selftest_*.py`）
- [ ] 是否保持 Windows/Android 双端决策一致（见 README「当前决策记录」）

## 问题与讨论

- Bug / 安全漏洞：**不要**在公开 Issue 描述可利用细节，先联系维护者或走 [SECURITY.md](SECURITY.md) 的披露流程
- 功能讨论 / 设计：GitHub Discussions 或 Issue 讨论
- 安全问题涉及认证/凭据时：仅通过安全渠道沟通，绝不在 Issue 中粘贴 token、密钥或证书

## 行为准则

保持专业与协作：评审聚焦代码而非个人；不同意见以证据与可验证测试为准。本项目为严谨工程，宁慢勿错。
