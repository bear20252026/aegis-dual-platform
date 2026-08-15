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
