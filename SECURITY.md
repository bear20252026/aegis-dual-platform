# Security Policy（SECURITY.md）

> 依据：蓝图目标树 SECURITY.md + 代码门禁（危险 API 有审查清单）+ ADR-002/003
> （安全边界——三信任域——Capability Broker 唯一副作用点）+ 阶段 E（发布链）。

## 安全边界（ADR-002/003——三信任域）

- 远程网页域：无 native bridge/无 MCP token/无本地命令（ADR-003）
- 本地 chrome UI 域：固定 origin——经 Broker 请求 action
- Capability broker 域：唯一副作用点——Default Deny（ADR-002）
- 发布链：逐工件闭合 fail-closed（阶段 E）——supply-chain 依赖审计

## 漏洞报告

- 私密披露（GitHub Security Advisory 协调披露流程）
- 报告内容：影响面/复现/缓解建议——不含敏感载荷
- 响应：确认 → 评估（threat-model：trust-boundaries/agent/release-threat-model）→
  修复 → 回归测试（CI 分层——contracts/core-rust/agent-redteam/supply-chain）→
  发布（release-checklist——阶段 E 独立验证）

## 危险 API 审查清单（代码门禁补充——蓝图"危险 API 有审查清单"）

| 语言 | 危险 API | 审查要点（禁止/受限） |
|---|---|---|
| Python | eval/exec/compile | 禁止（动态执行——无未过滤输入可执行） |
| Python | subprocess/os.system | 受限（参数经校验——无 shell 拼接面——CVE-2025-6514 场景） |
| Python | 反射（getattr 动态调用） | 受限（仅受信来源——白名单——不自动暴露命令） |
| Python | pickle/yaml.load | 禁止 yaml.load（用 safe_load）——pickle 仅受信数据 |
| C# | 反射（Activator/GetMethod 动态调用） | 禁止自动暴露命令（ADR-001——无动态反射命令面） |
| C# | dynamic/动态绑定 | 受限（强类型 IPC——Chrome → Broker） |
| Kotlin | 反射（KClass 动态调用） | 受限（webview-adapter 只事件转换——无动态命令） |

## 依赖与发布安全

- 依赖：requirements-lock（**hash 锁定仅限 Python requirements**——pip-compile
  --generate-hashes，WB-130，2026-09-26 审计——hash 表述不外推到其他端）+
  Cargo.lock（版本锁定）+ supply-chain.yml（pip-audit/cargo audit/SBOM）
- Android（WB-130，2026-09-26 审计）：Gradle 依赖无 lock 文件——新增/升级依赖须
  在 PR 说明并经 android-quality 门禁；APK 发布前经 apksigner 强制验签
  （release-android.yml fail-closed）
- C#/.NET（WB-130，2026-09-26 审计）：NuGet 依赖经 packages.lock.json 锁定
  （CI 缓存键消费）；WebView2 Runtime 为 evergreen 自更新组件——兼容性探测
  走 WebView2-Compat 定时工作流，安全修复依赖 Edge 发布通道
- 发布：release.yml（v* 标签——失败闭合）+ 发布链独立验证（阶段 E 工具）——无 || true/截断验证
- 更新：signatures[] 阈值 + 防回滚（P0-04/contracts 统一）
