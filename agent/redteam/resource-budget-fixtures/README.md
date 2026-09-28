# 资源预算红队 Fixtures（阶段 G——蓝图 agent/redteam/resource-budget-fixtures/）

> 超长输入/超预算请求（蓝图完成标准——官方 CSA 资源预算）——红队断言：
> 超长输入/超预算**不能**导致未批准副作用（阶段 G 完成标准）。

## 超长输入

```json
{
  "vector": "2MB 导航文本（P0-02 模拟场景——MAX_TEXT_BYTES 8KB）",
  "expected": "deny",
  "note": "MAX_TEXT_BYTES/MAX_ARGUMENT_BYTES/MAX_RAW_REQUEST_BYTES——mcp.py P0-02 时代已实现；SP-065（审计 2026-09-23 清单·SP1 批）：常量归属 legacy 归档栈，现役预算面见 agent/tests/redteam_e2e_test.py（ACTION_BUDGETS——SP-148）"
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

> **WB-063（审计 2026-09-23 清单·W5 批）**：本目录当前仅含本设计说明——
> 注入/重放/预算向量为**内联用例**，落在 `agent/tests/redteam_e2e_test.py`
>（SP-A1 批起的可执行红队面）；本 README 保留攻击链依据与设计意图，
> 独立 fixture 数据文件待测试规模外置时再落盘。
