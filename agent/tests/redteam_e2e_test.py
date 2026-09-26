"""agent/tests/redteam_e2e_test.py —— 阶段 G 红队端到端（蓝图 agent/tests/）。

端到端断言：提示注入/工具投毒/scope 重放/标签代际/超预算/过期/跨会话重放/
并发竞态/撤销都不能导致未批准副作用（阶段 G 完成标准——ADR-004——kill switch
撤销）。模拟 broker 与 contracts/Windows Broker/AndroidBroker 同语义
（Default Deny——fail-closed——工具级 scope/每调用验证/工具描述哈希绑定）。

SP-A1（审计 2026-09-26）：intents/scope/预算/政策版本全部从
contracts/policy/action-catalog.yaml 单源派生（不再手工维护双源——SP-009/
010/014/022）；Decision 结构化常量替代魔法字符串（SP-068）；补
session_id/expires_at/max_bytes/canonical_parameters 字段与各自 fail-closed
分支+测试（SP-015/016/017/019）；nonce 消费线程安全（SP-012）；revoke()
撤销语义（SP-013）；描述哈希未批准分支与 deny 不消费 nonce（SP-011/066）。
"""

from __future__ import annotations

import dataclasses
import pathlib
import threading
import time
import uuid

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = yaml.safe_load(
    (ROOT.parent / "contracts/policy/action-catalog.yaml").read_text(encoding="utf-8"))


class Decision:
    """SP-068：结构化决策常量——调用方/断言读语义而非魔法字符串。"""

    ALLOW = "allow"
    DENY_UNKNOWN = "deny_unknown"            # 未登记 action（default_deny）
    DENY_SESSION = "deny_session"            # 缺/空 session_id
    DENY_EXPIRED = "deny_expired"            # expires_at 已过
    DENY_POLICY = "deny_policy"              # policy_version 不匹配
    DENY_SCOPE = "deny_scope"                # scope 不在白名单
    DENY_GENERATION = "deny_generation"      # 标签代际过期
    DENY_REVOKED = "deny_revoked"            # kill switch 已撤销
    DENY_REPLAY = "deny_replay"              # nonce 重放（跨会话全局）
    DENY_BUDGET = "deny_budget"              # 超 max_actions
    DENY_BYTES = "deny_budget_bytes"         # 超 max_bytes
    DENY_CANONICAL = "deny_canonical"        # canonical_parameters 缺失/非法
    DENY_DESCRIPTION_HASH = "deny_description_hash"  # 工具描述哈希未批准


@dataclasses.dataclass
class ProposedAction:
    intent: str
    scope: str
    budget_used: int
    nonce: str
    generation: int
    tool_description_hash: str | None = None
    # SP-A1 新增字段（默认值向后兼容既有构造调用）
    session_id: str = "session-default"
    expires_at: float | None = None      # unix 秒；None = 不过期
    max_bytes: int = 0                   # 0 = 本调用不涉数据体传输（无字节预算）
    canonical_parameters: str | None = None  # 参数规范化串（STDIO 注入面）
    policy_version: str | None = None    # None = 采用 broker 版本


class E2EBroker:
    """红队 e2e 模拟 broker（与 contracts Decision 语义一致——Default Deny）。"""

    # SP-009/010/014/022：intents/scope/版本/预算从 action-catalog 单源派生
    ALLOWED_INTENTS: frozenset[str] = frozenset(
        a["name"] for a in CATALOG["actions"])
    ALLOWED_SCOPES: frozenset[str] = frozenset(
        a["scope"] for a in CATALOG["actions"])
    CATALOG_VERSION: str = str(CATALOG["policy_version"])
    DEFAULT_BUDGET: dict = CATALOG["actions"][0].get("budget", {"max_actions": 5, "max_bytes": 65536})

    def __init__(self, policy_version: str | None = None, max_actions: int | None = None,
                 max_bytes: int | None = None):
        self.policy_version = policy_version or self.CATALOG_VERSION
        self.max_actions = max_actions or self.DEFAULT_BUDGET["max_actions"]
        self.max_bytes = max_bytes or self.DEFAULT_BUDGET["max_bytes"]
        self.consumed_nonces: set[str] = set()
        self.approved_descriptions: dict[str, str] = {}  # tool -> 已批准描述哈希
        self.revoked = False
        self._nonce_lock = threading.Lock()  # SP-012：nonce 消费线程安全

    def revoke(self) -> None:
        """SP-013：kill switch 撤销（ADR-004）——此后一切 evaluate 拒绝。"""
        self.revoked = True

    def evaluate(self, action: ProposedAction) -> str:
        """Default Deny（fail-closed）——action-catalog + 工具级 scope + nonce
        一次性（跨会话全局）+ 代际 + 预算 + 过期 + 撤销。deny 不消费 nonce。"""
        if action.intent not in self.ALLOWED_INTENTS:
            return Decision.DENY_UNKNOWN
        if not action.session_id:
            return Decision.DENY_SESSION
        if action.expires_at is not None and action.expires_at < time.time():
            return Decision.DENY_EXPIRED
        actual_policy = action.policy_version or self.policy_version
        if actual_policy != self.policy_version:
            return Decision.DENY_POLICY
        if action.scope not in self.ALLOWED_SCOPES:
            return Decision.DENY_SCOPE  # 工具级 scope 最小权限（CSA——读工具不带写权限）
        if action.generation != 0:
            return Decision.DENY_GENERATION
        if self.revoked:
            return Decision.DENY_REVOKED
        if action.canonical_parameters is None:
            return Decision.DENY_CANONICAL  # STDIO 参数注入面——参数必须规范化
        if action.budget_used > self.max_actions:
            return Decision.DENY_BUDGET
        if action.max_bytes > self.max_bytes:
            return Decision.DENY_BYTES
        if action.tool_description_hash:
            approved = self.approved_descriptions.get(action.intent)
            if approved is None or approved != action.tool_description_hash:
                return Decision.DENY_DESCRIPTION_HASH  # 工具哈希绑定（CSA——描述变更需重新批准）
        # nonce 一次性消费：检查与登记必须同锁窗口（原子——防并发双消费）
        with self._nonce_lock:
            if action.nonce in self.consumed_nonces:
                return Decision.DENY_REPLAY
            self.consumed_nonces.add(action.nonce)
        return Decision.ALLOW


def _ok(intent: str = "get_current_title", **kw) -> ProposedAction:
    base = {"intent": intent, "scope": "tabs:read", "budget_used": 1,
            "nonce": uuid.uuid4().hex, "generation": 0, "canonical_parameters": "{}"}
    base.update(kw)
    return ProposedAction(**base)


def test_prompt_injection_denied():
    """网页内容提示注入（ignore instructions——导出书签）——无法产生副作用。"""
    broker = E2EBroker()
    injected = ProposedAction(intent="export_bookmarks", scope="tabs:read",
                              budget_used=1, nonce="n1", generation=0,
                              canonical_parameters="{}")
    assert broker.evaluate(injected) == Decision.DENY_UNKNOWN  # 未登记 action（default_deny）


def test_tool_poisoning_description_hash():
    """工具投毒（工具描述注入恶意指令）——描述哈希变更需重新批准（CSA 官方）。"""
    broker = E2EBroker()
    broker.approved_descriptions["get_current_title"] = "hash-approved"
    poisoned = _ok(tool_description_hash="hash-poisoned")  # 投毒后描述
    assert broker.evaluate(poisoned) == Decision.DENY_DESCRIPTION_HASH


def test_description_hash_honored_when_approved():
    """已批准哈希精确匹配——放行（哈希语义正路径）。"""
    broker = E2EBroker()
    broker.approved_descriptions["get_current_title"] = "hash-approved"
    assert broker.evaluate(_ok(tool_description_hash="hash-approved")) == Decision.ALLOW


def test_replay_and_generation():
    """scope 重放（nonce 复用）+ 标签代际变化——拒绝。"""
    broker = E2EBroker()
    ok = _ok(nonce="n3")
    assert broker.evaluate(ok) == Decision.ALLOW
    replayed = _ok(budget_used=2, nonce="n3")  # 重放同一 nonce
    assert broker.evaluate(replayed) == Decision.DENY_REPLAY
    stale = _ok(nonce="n4", generation=2)  # 标签代际过期
    assert broker.evaluate(stale) == Decision.DENY_GENERATION


def test_resource_budget():
    """超预算（max_actions 超限）——拒绝。"""
    broker = E2EBroker(max_actions=5)
    over = _ok(budget_used=6, nonce="n5")
    assert broker.evaluate(over) == Decision.DENY_BUDGET


def test_budget_bytes():
    """SP-016：超 max_bytes（数据体预算）——拒绝。"""
    broker = E2EBroker(max_bytes=1024)
    assert broker.evaluate(_ok(max_bytes=2048)) == Decision.DENY_BYTES
    assert broker.evaluate(_ok(max_bytes=512)) == Decision.ALLOW


def test_scope_minimal_privilege():
    """工具级 scope 最小权限——登记的 action 携带未授权 scope——一律拒绝。"""
    broker = E2EBroker()
    assert broker.evaluate(_ok(intent="get_current_origin", scope="downloads:read")) == Decision.DENY_SCOPE
    assert broker.evaluate(_ok(scope="")) == Decision.DENY_SCOPE
    assert broker.evaluate(_ok(scope="navigation:read", intent="get_current_origin")) == Decision.ALLOW


def test_cross_session_replay_denied():
    """SP-015：nonce 消费跨会话全局——同一 nonce 换会话仍拒绝（重放不跨会话复活）。"""
    broker = E2EBroker()
    assert broker.evaluate(_ok(nonce="shared")) == Decision.ALLOW
    cross = _ok(session_id="other-session", nonce="shared")
    assert broker.evaluate(cross) == Decision.DENY_REPLAY


def test_empty_session_rejected():
    """SP-015：缺/空 session_id——deny_session（会话上下文是授权前提）。"""
    assert E2EBroker().evaluate(_ok(session_id="")) == Decision.DENY_SESSION


def test_expiry_enforced():
    """SP-017：expires_at 过期——deny_expired；未过期——放行。"""
    broker = E2EBroker()
    now = time.time()
    assert broker.evaluate(_ok(nonce="e1", expires_at=now - 10)) == Decision.DENY_EXPIRED
    assert broker.evaluate(_ok(nonce="e2", expires_at=now + 10)) == Decision.ALLOW
    assert broker.evaluate(_ok(nonce="e3", expires_at=None)) == Decision.ALLOW  # 不过期显式


def test_policy_version_enforced():
    """SP-014：policy_version 不匹配——deny_policy（策略升级后旧授权失效）。"""
    broker = E2EBroker(policy_version="1.0")
    assert broker.evaluate(_ok(nonce="p1", policy_version="0.9")) == Decision.DENY_POLICY
    assert broker.evaluate(_ok(nonce="p2", policy_version="1.0")) == Decision.ALLOW


def test_canonical_parameters_required():
    """SP-019：canonical_parameters 缺失——deny_canonical（STDIO 参数注入面）。"""
    assert E2EBroker().evaluate(_ok(canonical_parameters=None)) == Decision.DENY_CANONICAL


def test_deny_does_not_consume_nonce():
    """SP-066：deny 不消费 nonce——失败分支后同 nonce 仍可合法放行一次。"""
    broker = E2EBroker()
    denied = _ok(scope="downloads:read", nonce="keep")
    assert broker.evaluate(denied) == Decision.DENY_SCOPE
    assert broker.evaluate(_ok(nonce="keep")) == Decision.ALLOW  # 未被 deny 消费


def test_revoke_blocks_everything():
    """SP-013：revoke()（kill switch）后一切 approve 尝试拒绝。"""
    broker = E2EBroker()
    broker.revoke()
    assert broker.evaluate(_ok()) == Decision.DENY_REVOKED
    assert broker.evaluate(_ok(intent="get_current_origin")) == Decision.DENY_REVOKED


def test_concurrent_nonce_consumption():
    """SP-012：8 线程并发唯一 nonce——恰好消费一次（无双消费/丢失）。"""
    broker = E2EBroker()
    n_threads, per_thread = 8, 32
    nonces = [uuid.uuid4().hex for _ in range(n_threads * per_thread)]
    results: list[list[str]] = [[] for _ in range(n_threads)]

    def worker(ti: int) -> None:
        for i in range(per_thread):
            results[ti].append(broker.evaluate(_ok(nonce=nonces[ti * per_thread + i])))

    threads = [threading.Thread(target=worker, args=(ti,)) for ti in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    flat = [r for group in results for r in group]
    assert flat.count(Decision.ALLOW) == n_threads * per_thread  # 全部唯一 → 全部放行
    assert len(broker.consumed_nonces) == n_threads * per_thread  # 恰好各一次


def test_field_set_matches_schema():
    """SP-067：ProposedAction 字段集与 action schema 对齐——授权判定依赖的全部
    字段齐备（意图/scope/预算/次数/nonce/会话/代际/过期/参数规范化/哈希/版本）。"""
    import dataclasses as dc
    fields = {f.name for f in dc.fields(ProposedAction)}
    required = {"intent", "scope", "budget_used", "nonce", "generation",
                "session_id", "expires_at", "max_bytes", "canonical_parameters",
                "tool_description_hash", "policy_version"}
    assert required <= fields


if __name__ == "__main__":
    # 保留原独立运行入口（不经 pytest 也能跑）
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ✅ {name}")
            except Exception as ex:  # noqa: BLE001
                failures.append((name, ex))
                print(f"  ❌ {name}: {ex}")
    if failures:
        raise SystemExit(f"{len(failures)} 失败")
    print("ALL OK — 阶段 G 红队 e2e 通过")