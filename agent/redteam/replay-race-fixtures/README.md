# 重放/竞态红队 Fixtures（阶段 G——蓝图 agent/redteam/replay-race-fixtures/）

> scope 重放/跨标签/并发竞态（蓝图完成标准）——红队断言：重放/竞态
> **不能**导致未批准副作用（阶段 G 完成标准）。

## Scope 重放

```json
{
  "vector": "重放已消费的 nonce（同一 ProposedAction 重复提交）",
  "expected": "deny",
  "note": "nonce 一次性消费（approvals-replay 向量——重放拒绝）"
}
```

## 跨标签/代际竞态

```json
{
  "vector": "已切换标签后，旧标签的授权仍尝试执行（document_generation 过期）",
  "expected": "deny",
  "note": "AuthorizedAction 绑定 document_generation——代际变化使批准失效"
}
```

## 并发竞态

```json
{
  "vector": "同一 session 并发提交超预算 action（并发绕过预算）",
  "expected": "deny",
  "note": "资源预算（max_actions/max_bytes）broker 侧强制——并发不绕过"
}
```

> **WB-063（审计 2026-09-23 清单·W5 批）**：本目录另有 `fixtures.json`——每一步由
> 出厂 `agent/broker.py` 的 `PolicyBroker` 真实判定（第七轮 R7-TOOL-06 起唯一入口
> 为 pytest，见 `agent/tests/redteam_test.py`），上方散文保留攻击链依据与设计意图。
> 上方 `"expected": "deny"` 是设计期笼统写法，可执行夹具一律用**精确决策串**
>（禁止笼统 "deny"——那正是「声明 deny 实 allow」的假保证形态）。
