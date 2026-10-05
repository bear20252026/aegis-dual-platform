# ADR-008：Rust 策略核心为唯一裁决源（URL 校验单源口径）

- 状态：已接受
- 日期：2026-09-02
- 关联：ADR-002（capability broker）、ADR-005/006（Rust 策略核心）、ADR-007（单源守卫）；Windows 正典口径另见 CLAUDE.md 与 ADR-009（单轨——双栈语义已收敛）

## 背景

全库审计（2026-09-02）实锤：URL 安全校验规则（长度上限 8192、控制字符
0x20/0x7F 拒绝、userinfo 拒绝、scheme 白名单、65535 端口上限等）在**四处**
重复实现：

| 位置 | 角色 |
|---|---|
| `core/rust-policy-core/src/origin.rs` | 权威实现（含 contracts url-origin-* 向量对拍） |
| `android/broker/.../OriginPolicy.kt` | Android 宿主侧副本 |
| `windows/src/.../Broker/OriginPolicy.cs` | C# 宿主侧副本 |
| `legacy/windows-pywebview/app/security.py` | Python 归档栈副本（只读冻结——ADR-009 D4；仅 P0 披露通道评估） |

四处长期各自演进必然漂移：同一 URL 展示层与裁决层可得出不同判定
（BrowserEngine A-3 修复即是此类漂移的实例）。且 `AndroidBroker` 部分路径
仍直接调用 Kotlin 版 `OriginPolicy` 而不经 native 门禁。

## 决策

1. **Rust 策略核心（`core/rust-policy-core`）是 URL/导航裁决的唯一权威**。
  contracts 的 `url-origin-*` 测试向量是对该权威的机器可执行规约。
2. Kotlin / C# / Python 三份宿主实现**降级为 defense-in-depth**：只做
   「快速失败前置过滤」，允许但不应依赖其拒绝能力；任何校验语义变更
   必须先改 Rust + 向量，再同步宿主副本，并在 PR 中声明。
3. 宿主实现存在的理由：native 核心不可用时的 fail-closed 前置、纯 JVM
   单测便利、把明显非法输入挡在 FFI 边界之外。**不得**新增「只有宿主版
   才有」的放行类语义（白名单扩面、豁免通路）。
4. 后续演进方向（按需排期，非本次强制）：
   - `AndroidBroker` 全路径收敛到 `NativePolicyCoreGate` 之后的 native
     裁决，Kotlin 版仅保留向量对拍测试；
   - C# 端迁移到目标栈后同样口径。

## 后果

- 正面：单一真相，四份副本从「平行实现」变为「有主从关系的镜像」；
  审计时只需对拍向量。
- 代价：改校验语义时要同步多处（与现状相同），但顺序与权威被明确固化。
- 验证：contracts.yml 已含向量 JSON 校验与 codegen diff 门禁；向量新增
  时 Rust 侧必须先绿。

## 参考

- 审计记录：会话工作日志 2026-09-02（三路并行审计 + 人工复核）。
- 实锤文件行号见该日志；本文不重复引用易漂移的行号。

---

## 现状注记（第八轮 B8，2026-10-05）——「唯一裁决源」的范围限定

本 ADR 立的是 **URL 校验单源**（长度/控制字符/userinfo/scheme/端口），这一面确实
收敛了。但 README/CLAUDE/SECURITY/architecture-overview/supported-features 长期把它
转述为无限定语的「唯一裁决者」，与实树不符：

- FFI 通路实际承载：URL 归一 + 黑名单 + 高危判定 + nonce 兑换；
- `PolicyEngine::default()` 与 `CapabilityRegistry::new()` 在 `ffi/broker.rs` 里被
  构造却从不参与 `evaluate`（核心自述 H-7 未撤）——**能力评估裁决仍在各端托管
  Broker**，没有单一裁决源；
- 跨端对账也不齐：`bridge_guard` 单源只覆盖 Rust（`include_str!`）与 Android
  （手抄 + 逐行比对），C# 的文档创建前注入面不在范围内；向量覆盖 C# 只链 2 份、
  Kotlin 只消费 `url-origin-*`。

因此上述五处文档的措辞统一改为「**导航**裁决单源」并注明 H-7。本 ADR 的正文与
状态不改写（决策仍成立），只是转述层不得再省略限定语。证据行号见
`docs/audit/full-audit-2026-10-04-round8.md` §5.2。
