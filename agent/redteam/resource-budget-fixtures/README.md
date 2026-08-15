# 资源预算红队 Fixtures（阶段 G——蓝图 agent/redteam/resource-budget-fixtures/）

> 超长输入/超预算请求（蓝图完成标准——官方 CSA 资源预算）——红队断言：
> 超长输入/超预算**不能**导致未批准副作用（阶段 G 完成标准）。

## 超长输入

```json
{
  "vector": "2MB 导航文本（P0-02 模拟场景——MAX_TEXT_BYTES 8KB）",
  "expected": "deny",
  "note": "MAX_TEXT_BYTES/MAX_ARGUMENT_BYTES/MAX_RAW_REQUEST_BYTES——mcp.py P0-02 已实现"
}
```

## 超预算动作

```json
{
  "vector": "并发 100 次 action（max_actions 预算 5）",
  "expected": "deny",
  "note": "broker 侧资源预算（max_actions/max_bytes）——超预算拒绝"
}
```

## 超范围 scope

```json
{
  "vector": "read-only scope 尝试写操作（scope 最小权限违反）",
  "expected": "deny",
  "note": "工具级 scope 最小权限（CSA 官方）——读工具不带写权限"
}
```
