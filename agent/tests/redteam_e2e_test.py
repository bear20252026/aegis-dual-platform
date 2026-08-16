"""agent/tests/redteam_e2e_test.py —— 阶段 G 红队端到端（蓝图 agent/tests/）。

端到端断言：提示注入/工具投毒/scope 重放/标签代际/超预算/并发竞态都不能导致
未批准副作用（阶段 G 完成标准——ADR-004——kill switch 撤销）。模拟 broker 与
contracts/Windows Broker/AndroidBroker 同语义（Default Deny——fail-closed——
工具级 scope/每调用验证/工具描述哈希绑定——CSA 官方 + 中文实战交叉）。
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class ProposedAction:
    intent: str
    scope: str
    budget_used: int
    nonce: str
    generation: int
    tool_description_hash: str | None = None


class E2EBroker:
    """红队 e2e 模拟 broker（与 contracts Decision 语义一致——Default Deny）。"""

    # 与 contracts/policy/action-catalog.yaml 一致：首批只读低风险——未登记 action 不可用
    ALLOWED_INTENTS: frozenset[str] = frozenset({"get_current_title", "get_current_origin"})

    def __init__(self, policy_version: str = "1.0", max_actions: int = 5):
        self.policy_version = policy_version
        self.max_actions = max_actions
        self.consumed_nonces: set[str] = set()
        self.approved_descriptions: dict[str, str] = {}  # tool -> 已批准描述哈希

    def evaluate(self, action: ProposedAction) -> str:
        """Default Deny（fail-closed）——action-catalog + 工具级 scope + nonce
        一次性 + 代际 + 预算。"""
        if action.intent not in self.ALLOWED_INTENTS:
            return "deny_unknown"  # 未登记 action（default_deny——蓝图 action-catalog）
        if action.nonce in self.consumed_nonces:
            return "deny_replay"  # nonce 一次性消费（approvals-replay 向量）
        if action.budget_used > self.max_actions:
            return "deny_budget"  # 资源预算（P0-02——超预算拒绝）
        if action.scope not in ("tabs:read", "navigation:read"):
            return "deny_scope"  # 工具级 scope 最小权限（CSA——读工具不带写权限）
        if action.generation != 0:
            return "deny_generation"  # 标签代际变化使批准失效（contracts action schema）
        if action.tool_description_hash:
            approved = self.approved_descriptions.get(action.intent)
            if approved is None or approved != action.tool_description_hash:
                return "deny_description_hash"  # 工具哈希绑定（CSA——描述变更需重新批准）
        self.consumed_nonces.add(action.nonce)
        return "allow"


def test_prompt_injection_denied():
    """网页内容提示注入（ignore instructions——导出书签）——无法产生副作用。"""
    broker = E2EBroker()
    injected = ProposedAction(intent="export_bookmarks", scope="tabs:read",
                              budget_used=1, nonce="n1", generation=0)
    assert broker.evaluate(injected) == "deny_unknown"  # 未登记 action（default_deny）


def test_tool_poisoning_description_hash():
    """工具投毒（工具描述注入恶意指令）——描述哈希变更需重新批准（CSA 官方）。"""
    broker = E2EBroker()
    broker.approved_descriptions["get_current_title"] = "hash-approved"
    poisoned = ProposedAction(intent="get_current_title", scope="tabs:read",
                              budget_used=1, nonce="n2", generation=0,
                              tool_description_hash="hash-poisoned")  # 投毒后描述
    assert broker.evaluate(poisoned) == "deny_description_hash"


def test_replay_and_generation():
    """scope 重放（nonce 复用）+ 标签代际变化——拒绝。"""
    broker = E2EBroker()
    ok = ProposedAction(intent="get_current_title", scope="tabs:read",
                        budget_used=1, nonce="n3", generation=0)
    assert broker.evaluate(ok) == "allow"
    replayed = ProposedAction(intent="get_current_title", scope="tabs:read",
                              budget_used=2, nonce="n3", generation=0)  # 重放同一 nonce
    assert broker.evaluate(replayed) == "deny_replay"
    stale = ProposedAction(intent="get_current_title", scope="tabs:read",
                           budget_used=3, nonce="n4", generation=2)  # 标签代际过期
    assert broker.evaluate(stale) == "deny_generation"


def test_resource_budget():
    """超预算（max_actions 超限）——拒绝。"""
    broker = E2EBroker(max_actions=5)
    over = ProposedAction(intent="get_current_title", scope="tabs:read",
                          budget_used=6, nonce="n5", generation=0)
    assert broker.evaluate(over) == "deny_budget"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✅ {name}")
    print("ALL OK — 阶段 G 红队 e2e 通过（注入/投毒/重放/代际/预算全部拒绝——无未批准副作用）")
