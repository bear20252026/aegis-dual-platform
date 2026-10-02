<!-- 提交前自查（与 CLAUDE.md / CONTRIBUTING.md 口径一致）：

- [ ] 改动所涉技术栈的门禁全过：
      C#：dotnet build（0 警告）+ dotnet test 两套件
      Rust：cargo test && clippy --all-features --all-targets -D warnings && fmt --check（SP-183 统一口径）
      Android：四模块 ktlint + detekt + 单测 + :app:lintDebug
      shared/shell：node --test（目录 glob——SP-163/187）+ node shared/shell/snake.test.js
      scripts/contracts/release：validate_release.py + verify_versions.py +
      verify_release_schema.py + verify_cross_end_lists.py + verify_vectors.py +
      verify_xaml_resources.py + verify_bridge_guard.py（SP-243：契约五脚本
      补全——与 contracts.yml/release-windows.yml 门禁同口径）+
      pytest（tests/python 与 agent/tests）
- [ ] agent/catalog 改动过红队门禁：pytest agent/tests + verify_agent_catalog.py（SP-191）
- [ ] 依赖/锁文件改动过供应链门禁：--require-hashes 可装 + pip-audit 干净（SP-191）
- [ ] 遵守单文件单职责与行数红线（新文件 ≤300，改造后 ≤500）
- [ ] 涉及 URL/密码/下载/权限/导航时已说明安全考虑（fail-closed）
- [ ] 有对应测试/断言入库（tests/ 或对应端测试套件；不为过检弱化断言）
- [ ] 更新了 CHANGELOG.md（随下一版本合并记账）
- [ ] 遵循 Conventional Commits（feat/fix/refactor/docs/chore/security）
- [ ] 未触及 legacy/windows-pywebview 归档栈（只读冻结——ADR-009；P0 仅走
      安全披露通道）

安全敏感改动（桥暴露面/信任边界/发布链）请在描述中显式标注威胁模型影响
（docs/threat-model/）。 -->

## 变更说明

……

## 动机与背景

……

## 验证方式

……
