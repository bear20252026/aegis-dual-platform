"""agent/tests/redteam_e2e_test.py —— 阶段 G 红队端到端（蓝图 agent/tests/）。

端到端断言：提示注入/工具投毒/scope 重放/标签代际/超预算/过期/跨会话重放/
并发竞态/撤销都不能导致未批准副作用（阶段 G 完成标准——ADR-004——kill switch
撤销）。

审计第六轮（2026-10-03）：安全闭环——本文件此前**自带**一个测试局部
broker 类（E2EBroker），全部端到端断言都在打它，出厂代码零参与；
`agent/local-ipc/identity.md`（SP-064）又把"现役等价实现"指向这个测试局部
类，等于"红面在测脚手架"。决策面已提取到 `agent/broker.py`（PolicyBroker——
消费 contracts/policy/action-catalog.yaml 单源），本文件只保留断言，
被测对象 = 出厂模块。语义与原测试局部实现逐条保持（SP-A1/SP-N1 全部
不变量随迁——SP-009/010/012/013/014/015/016/017/019/022/066/067/068/
140/141/142/148/149/150/156/157/158/159/237/252/260/282）。

红队 fixtures（agent/redteam/*-fixtures/*.json）驱动的是同一个
`agent.broker.PolicyBroker`——见 redteam_test.py。
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import sys
import threading
import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
# 被测对象为出厂模块（非本文件内定义）——pytest 与直跑（scripts/run-security-e2e）
# 两种形态都以 agent/ 目录为导入根。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from broker import (
    Decision,
    PolicyBroker,
    ProposedAction,
    well_formed_action,
)


def _ok(intent: str = "get_current_title", **kw) -> ProposedAction:
    """well-formed 动作工厂——委托 broker.well_formed_action（单源），
    仅补测试用例需要的"每次默认新 nonce"语义。"""
    kw.setdefault("nonce", uuid.uuid4().hex)
    return well_formed_action(intent, **kw)


def test_prompt_injection_denied():
    """网页内容提示注入（ignore instructions——导出书签）——无法产生副作用。"""
    broker = PolicyBroker()
    injected = ProposedAction(intent="export_bookmarks", scope="tabs:read",
                              budget_used=1, nonce="n1", document_generation=0,
                              tab_id="tab-1", origin="https://example.test",
                              method="GET", canonical_parameters="{}")
    assert broker.evaluate(injected) == Decision.DENY_UNKNOWN  # 未登记 action（default_deny）


def test_tool_poisoning_description_hash():
    """工具投毒（工具描述注入恶意指令）——描述哈希变更需重新批准（CSA 官方）。"""
    broker = PolicyBroker()
    broker.approved_descriptions["get_current_title"] = "hash-approved"
    poisoned = _ok(tool_description_hash="hash-poisoned")  # 投毒后描述
    assert broker.evaluate(poisoned) == Decision.DENY_DESCRIPTION_HASH


def test_description_hash_honored_when_approved():
    """已批准哈希精确匹配——放行（哈希语义正路径）。"""
    broker = PolicyBroker()
    broker.approved_descriptions["get_current_title"] = "hash-approved"
    assert broker.evaluate(_ok(tool_description_hash="hash-approved")) == Decision.ALLOW


def test_description_hash_required_when_registered():
    """SP-141（2026-09-26 审计）：注册过 approved_descriptions 的工具——哈希必填：
    省略字段（None）/空串均拒绝（真值检查绕过面消除）；未注册工具不受影响。"""
    broker = PolicyBroker()
    broker.approved_descriptions["get_current_title"] = "hash-approved"
    assert broker.evaluate(_ok(nonce="h1")) == Decision.DENY_DESCRIPTION_HASH  # 省略哈希字段
    assert broker.evaluate(_ok(nonce="h2", tool_description_hash="")) == Decision.DENY_DESCRIPTION_HASH
    assert broker.evaluate(_ok(nonce="h3", tool_description_hash="hash-approved")) == Decision.ALLOW
    # 未注册哈希绑定的工具：省略哈希不受影响（哈希绑定按工具配对注册生效）
    origin = _ok(intent="get_current_origin", nonce="h4")
    assert origin.tool_description_hash is None
    assert broker.evaluate(origin) == Decision.ALLOW


def test_replay_and_generation():
    """scope 重放（nonce 复用）+ 标签代际变化——拒绝。"""
    broker = PolicyBroker()
    ok = _ok(nonce="n3")
    assert broker.evaluate(ok) == Decision.ALLOW
    replayed = _ok(budget_used=2, nonce="n3")  # 重放同一 nonce
    assert broker.evaluate(replayed) == Decision.DENY_REPLAY
    stale = _ok(nonce="n4", document_generation=2)  # 标签代际过期
    assert broker.evaluate(stale) == Decision.DENY_GENERATION


def test_generation_advances_with_broker_state():
    """SP-158（2026-09-26 审计）：broker 持当前代际（可推进）——合法新代际
    （推进后 =1）放行，旧代际（=0）随即失效；代际回退尝试被忽略（fail-closed）。"""
    broker = PolicyBroker()
    assert broker.evaluate(_ok(nonce="gen0")) == Decision.ALLOW  # 当前代际 0
    assert broker.evaluate(_ok(nonce="gen1", document_generation=1)) == Decision.DENY_GENERATION
    broker.advance_generation(1)  # 标签刷新/导航——代际推进
    assert broker.evaluate(_ok(nonce="gen2", document_generation=1)) == Decision.ALLOW
    assert broker.evaluate(_ok(nonce="gen3", document_generation=0)) == Decision.DENY_GENERATION
    broker.advance_generation(0)  # 回退尝试——被忽略
    assert broker.current_generation == 1
    assert broker.evaluate(_ok(nonce="gen4", document_generation=0)) == Decision.DENY_GENERATION


def test_resource_budget():
    """超预算——自报 budget_used 本身超限即拒（SP-149 冗余校验——保留原拒绝
    路径；真实判定以 broker 侧 per-session 累计计数为准——见累计计数用例）。"""
    broker = PolicyBroker(max_actions=5)
    over = _ok(budget_used=6, nonce="n5")
    assert broker.evaluate(over) == Decision.DENY_BUDGET


def test_budget_bytes():
    """SP-016：超 max_bytes（数据体预算）——拒绝。"""
    broker = PolicyBroker(max_bytes=1024)
    assert broker.evaluate(_ok(max_bytes=2048)) == Decision.DENY_BYTES
    assert broker.evaluate(_ok(max_bytes=512)) == Decision.ALLOW


def test_per_action_budget_from_catalog():
    """SP-148（2026-09-26 审计）：预算按 action.intent 逐条查 catalog 判定
    （DEFAULT_BUDGET 全局 fallback 字典已删——逐条预算字段真实生效）。
    （临时替换类级 ACTION_BUDGETS——mock 自恢复，不经 pytest 也能跑。）"""
    budgets = {name: dict(spec) for name, spec in PolicyBroker.ACTION_BUDGETS.items()}
    budgets["get_current_title"]["max_actions"] = 2
    with mock.patch.object(PolicyBroker, "ACTION_BUDGETS", budgets):
        broker = PolicyBroker()
        assert broker.evaluate(_ok(nonce="pb1")) == Decision.ALLOW
        assert broker.evaluate(_ok(nonce="pb2")) == Decision.ALLOW
        assert broker.evaluate(_ok(nonce="pb3")) == Decision.DENY_BUDGET  # title 限额 2——第 3 次拒
        # 其他 action 不受影响——按各自 catalog 预算独立判定
        assert broker.evaluate(_ok(intent="get_current_origin", nonce="pb4")) == Decision.ALLOW


def test_session_cumulative_budget_counter():
    """SP-148/149（2026-09-26 审计）：broker 侧 per-session 累计计数判定——
    catalog per-action 预算（max_actions=5）达限后第 N+1 次拒绝；deny 不计数。"""
    broker = PolicyBroker()
    for i in range(5):
        assert broker.evaluate(_ok(nonce=f"cum{i}")) == Decision.ALLOW
    assert broker.evaluate(_ok(nonce="cum-deny-first", scope="")) == Decision.DENY_SCOPE
    assert broker.session_usage("session-default") == (5, 0)  # deny 未计入
    assert broker.evaluate(_ok(nonce="cum-over")) == Decision.DENY_BUDGET


def test_self_reported_budget_lie_still_denied():
    """SP-149（2026-09-26 审计）：自报预算不可信——broker 侧 per-session 累计
    计数判定：恒报 budget_used=1 的谎报在真实计数达限后仍被拒；字节数逐笔
    累计——拆分传输累计超限同样拒绝（计数在锁窗口内推进——并发安全）。"""
    broker = PolicyBroker()
    for i in range(5):
        # 每次自报 budget_used=1（谎报——从未承认累计用量）
        assert broker.evaluate(_ok(nonce=f"lie{i}", budget_used=1)) == Decision.ALLOW
    # broker 真实计数已达 5——第 6 次即使仍自报 1 也被拒
    assert broker.evaluate(_ok(nonce="lie-over", budget_used=1)) == Decision.DENY_BUDGET

    broker2 = PolicyBroker()
    assert broker2.evaluate(_ok(nonce="by1", max_bytes=32768)) == Decision.ALLOW
    assert broker2.evaluate(_ok(nonce="by2", max_bytes=32768)) == Decision.ALLOW  # 累计 = 上限
    assert broker2.evaluate(_ok(nonce="by3", max_bytes=1)) == Decision.DENY_BYTES  # 累计超限
    assert broker2.session_usage("session-default") == (2, 65536)


def test_explicit_zero_override_honored():
    """SP-159（2026-09-26 审计）：构造器显式 0 上限生效（is None 判定——显式
    falsy 值不再被默认吞掉——0 = 全部拒绝，fail-closed）。"""
    broker = PolicyBroker(max_actions=0)
    assert broker.evaluate(_ok(nonce="z1")) == Decision.DENY_BUDGET


def test_scope_minimal_privilege():
    """工具级 scope 最小权限——登记的 action 携带未授权 scope——一律拒绝。"""
    broker = PolicyBroker()
    assert broker.evaluate(_ok(intent="get_current_origin", scope="downloads:read")) == Decision.DENY_SCOPE
    assert broker.evaluate(_ok(scope="")) == Decision.DENY_SCOPE
    assert broker.evaluate(_ok(scope="navigation:read", intent="get_current_origin")) == Decision.ALLOW


def test_intent_scope_cross_pairing_denied():
    """SP-142（2026-09-26 审计）：intent→scope 配对一致（catalog 逐条绑定）——
    get_current_origin 搭配另一 action 的 tabs:read 必须拒绝（独立成员判定消除）。"""
    broker = PolicyBroker()
    cross = _ok(intent="get_current_origin", scope="tabs:read", nonce="x1")
    assert broker.evaluate(cross) == Decision.DENY_SCOPE
    # 正配对不受影响（不误伤合法组合）
    assert broker.evaluate(_ok(intent="get_current_origin", scope="navigation:read",
                               nonce="x2")) == Decision.ALLOW
    assert broker.evaluate(_ok(intent="get_current_title", scope="tabs:read",
                               nonce="x3")) == Decision.ALLOW


def test_cross_session_replay_denied():
    """SP-015：nonce 消费跨会话全局——同一 nonce 换会话仍拒绝（重放不跨会话复活）。"""
    broker = PolicyBroker()
    assert broker.evaluate(_ok(nonce="shared")) == Decision.ALLOW
    cross = _ok(session_id="other-session", nonce="shared")
    assert broker.evaluate(cross) == Decision.DENY_REPLAY


def test_empty_session_rejected():
    """SP-015：缺/空 session_id——deny_session（会话上下文是授权前提）。"""
    assert PolicyBroker().evaluate(_ok(session_id="")) == Decision.DENY_SESSION


def test_omitted_session_id_rejected():
    """SP-140（2026-09-26 审计）：省略 session_id 字段（默认 None）——deny_session
    （默认值不再自带合法会话——fail-open 默认消除）。"""
    broker = PolicyBroker()
    omitted = ProposedAction(intent="get_current_title", scope="tabs:read",
                             budget_used=1, nonce=uuid.uuid4().hex,
                             document_generation=0, tab_id="tab-1",
                             origin="https://example.test", method="GET",
                             canonical_parameters="{}")
    assert omitted.session_id is None  # 默认 None——不再预置合法会话
    assert broker.evaluate(omitted) == Decision.DENY_SESSION


def test_expiry_enforced():
    """SP-017：expires_at 过期——deny_expired；未过期——放行。
    SP-150：expires_at 为 schema 口径 RFC3339 date-time 字符串。
    SP-157：解析失败 fail-closed 视同过期（无宽限）。
    R7-TOOL-02：契约把 expires_at 列为 required——省略曾是"永久有效授权"，现判 deny_schema。"""
    broker = PolicyBroker()
    now = datetime.now(UTC)
    assert broker.evaluate(_ok(
        nonce="e1", expires_at=(now - timedelta(seconds=10)).isoformat())) == Decision.DENY_EXPIRED
    assert broker.evaluate(_ok(
        nonce="e2", expires_at=(now + timedelta(seconds=10)).isoformat())) == Decision.ALLOW
    assert broker.evaluate(_ok(nonce="e3", expires_at=None)) == Decision.DENY_SCHEMA  # 缺 required
    assert broker.evaluate(_ok(nonce="e4", expires_at="not-a-timestamp")) == Decision.DENY_EXPIRED


def test_expiry_boundary_inclusive_denied():
    """PY-237（2026-10-01 审计）：expires_at 恰等于 now 即过期——与
    update_verifier 的 <= 口径对齐（此前用 < 留出同瞬放行窗口，
    发布链验证器与红队面边界分叉）。"""
    import time as _time
    broker = PolicyBroker()
    frozen = datetime(2030, 1, 1, tzinfo=UTC)
    original = _time.time
    try:
        _time.time = lambda: frozen.timestamp()
        assert broker.evaluate(_ok(
            nonce="eq1", expires_at=frozen.isoformat())) == Decision.DENY_EXPIRED
        one_ns_later = frozen + timedelta(microseconds=1)
        assert broker.evaluate(_ok(
            nonce="eq2", expires_at=one_ns_later.isoformat())) == Decision.ALLOW
    finally:
        _time.time = original


def test_session_tab_binding_enforced():
    """PY-252（2026-10-01 审计）：session 绑定 tab_id——同 session 首笔固定
    绑定，换 tab_id 即 DENY_TAB（session.md 声称的跨标签失效语义落地——
    此前只比对代际，窄于文档）。"""
    broker = PolicyBroker()
    assert broker.evaluate(_ok(nonce="t1", tab_id="tab-1")) == Decision.ALLOW
    # 同 session 换 tab：拒绝（跨标签重放/劫持面）
    assert broker.evaluate(_ok(nonce="t2", tab_id="tab-2")) == Decision.DENY_TAB
    # 原 tab 继续：放行（绑定未失效）
    assert broker.evaluate(_ok(nonce="t3", tab_id="tab-1")) == Decision.ALLOW
    # 不同 session 各自独立绑定同一 tab：互不影响
    assert broker.evaluate(_ok(nonce="t4", tab_id="tab-1",
                               session_id="session-b")) == Decision.ALLOW
    assert broker.evaluate(_ok(nonce="t5", tab_id="tab-9",
                               session_id="session-b")) == Decision.DENY_TAB


def test_deny_does_not_burn_tab_binding():
    """PY-260（2026-10-02 审计）：deny 不燃烧会话-tab 绑定——绑定写入移进
    _state_lock、置于全部门禁通过后。此前绑定在全部 deny 门之前且在锁外：
    首笔被 deny（scope/撤销/预算/重放…）的请求也会固定 tab 绑定，后续合法
    tab 的请求被无端 DENY_TAB（deny 燃烧绑定）；且锁外写入与并发评估竞态。"""
    # 场景①：撤销后首笔（tab-1）被拒——绑定不得落在 tab-1 上
    broker = PolicyBroker()
    broker.revoke()
    assert broker.evaluate(_ok(nonce="nb1", tab_id="tab-1")) == Decision.DENY_REVOKED
    assert broker._session_tabs == {}  # deny 未燃烧绑定（绑定表空）
    broker.revoked = False  # 撤销恢复（仅测试构造）
    assert broker.evaluate(_ok(nonce="nb2", tab_id="tab-2")) == Decision.ALLOW
    # 场景②：换 tab 的请求被 DENY_TAB 拒绝后，原 tab 请求继续放行——
    # 拒绝路径不覆盖/不破坏既有绑定
    assert broker.evaluate(_ok(nonce="nb3", tab_id="tab-9")) == Decision.DENY_TAB
    assert broker.evaluate(_ok(nonce="nb4", tab_id="tab-2")) == Decision.ALLOW
    # 场景③：scope deny 首笔同样不燃烧绑定
    broker2 = PolicyBroker()
    denied = _ok(scope="downloads:read", nonce="nb5", tab_id="tab-1")
    assert broker2.evaluate(denied) == Decision.DENY_SCOPE
    assert broker2._session_tabs == {}
    assert broker2.evaluate(_ok(nonce="nb6", tab_id="tab-7")) == Decision.ALLOW


def test_concurrent_first_binding_single_winner():
    """PY-260（2026-10-02 审计）：并发首笔绑定无竞态——多线程同时以不同
    tab_id 评估同一 session 时，恰好一笔完成绑定（其余 DENY_TAB），绑定表
    不因锁外写入出现后写覆盖先写的双绑定窗口。"""
    n_threads = 8
    broker = PolicyBroker(max_actions=n_threads)  # 提升限额——隔离绑定语义
    results: list[str] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        decision = broker.evaluate(_ok(nonce=f"race{i}", tab_id=f"tab-{i}"))
        with lock:
            results.append(decision)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 恰好一笔 ALLOW（首笔绑定者），其余全部 DENY_TAB——无双绑定/无丢失
    assert results.count(Decision.ALLOW) == 1, results
    assert results.count(Decision.DENY_TAB) == n_threads - 1
    assert len(broker._session_tabs) == 1


def test_expires_at_rfc3339_anchored():
    """PY-282（2026-10-02 审计）：expires_at 解析与 update_verifier._RFC3339
    锚定口径对齐——裸日期/空格分隔/无时区等宽松形态同样拒绝
    （DENY_EXPIRED fail-closed），不再被裸 fromisoformat 悄悄放行。"""
    broker = PolicyBroker()
    # 宽松形态（fromisoformat 可解析但非 RFC3339）→ 拒绝（对齐 schema 口径）
    for bad in ("2026-01-01", "2026-01-01 12:00:00Z", "2026-01-01T12:00:00"):
        assert broker.evaluate(_ok(nonce=f"an{bad}", expires_at=bad)) == Decision.DENY_EXPIRED, bad
    # 小写 t/z 分隔符——正则放行 + 归一后可解析（PY-262 同款归一口径）
    near = datetime.now(UTC) + timedelta(seconds=30)  # TTL 上限内
    assert broker.evaluate(_ok(
        nonce="an-lower",
        expires_at=near.strftime("%Y-%m-%dt%H:%M:%Sz"))) == Decision.ALLOW
    # 标准 RFC3339（大写 T/Z 与 ±HH:MM 偏移）不受影响
    assert broker.evaluate(_ok(
        nonce="an-upper",
        expires_at=near.strftime("%Y-%m-%dT%H:%M:%SZ"))) == Decision.ALLOW
    assert broker.evaluate(_ok(
        nonce="an-off",
        expires_at=near.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00")) == Decision.ALLOW


def test_max_ttl_enforced():
    """SP-157（2026-09-26 审计）：expires_at 超过 max_ttl——拒绝（now+10 年的
    授权不再永久有效）；TTL 内仍放行；构造器可收紧 max_ttl。"""
    broker = PolicyBroker()
    far = (datetime.now(UTC) + timedelta(days=3650)).isoformat()
    assert broker.evaluate(_ok(nonce="ttl1", expires_at=far)) == Decision.DENY_MAX_TTL
    near = (datetime.now(UTC) + timedelta(seconds=10)).isoformat()
    assert broker.evaluate(_ok(nonce="ttl2", expires_at=near)) == Decision.ALLOW
    tight = PolicyBroker(max_ttl=5.0)
    assert tight.evaluate(_ok(nonce="ttl3", expires_at=near)) == Decision.DENY_MAX_TTL


def test_policy_version_enforced():
    """SP-014：policy_version 不匹配——deny_policy（策略升级后旧授权失效）。
    SP-159：显式空串 policy_version 不再回退 broker 默认（falsy 吞没消除）。"""
    broker = PolicyBroker(policy_version="1.0")
    assert broker.evaluate(_ok(nonce="p1", policy_version="0.9")) == Decision.DENY_POLICY
    assert broker.evaluate(_ok(nonce="p2", policy_version="1.0")) == Decision.ALLOW
    assert broker.evaluate(_ok(nonce="p3", policy_version="")) == Decision.DENY_POLICY


def test_canonical_parameters_required():
    """SP-019：canonical_parameters 缺失——deny_canonical（STDIO 参数注入面）。"""
    assert PolicyBroker().evaluate(_ok(canonical_parameters=None)) == Decision.DENY_CANONICAL


def test_deny_does_not_consume_nonce():
    """SP-066：deny 不消费 nonce——失败分支后同 nonce 仍可合法放行一次。"""
    broker = PolicyBroker()
    denied = _ok(scope="downloads:read", nonce="keep")
    assert broker.evaluate(denied) == Decision.DENY_SCOPE
    assert broker.evaluate(_ok(nonce="keep")) == Decision.ALLOW  # 未被 deny 消费


def test_revoke_blocks_everything():
    """SP-013：revoke()（kill switch）后一切 approve 尝试拒绝。"""
    broker = PolicyBroker()
    broker.revoke()
    assert broker.evaluate(_ok()) == Decision.DENY_REVOKED
    assert broker.evaluate(_ok(intent="get_current_origin")) == Decision.DENY_REVOKED


def test_concurrent_nonce_consumption():
    """SP-012：8 线程并发唯一 nonce——恰好消费一次（无双消费/丢失）。
    SP-149：per-session 预算计数并发安全——限额提升到用例规模后全部放行，
    broker 侧计数恰等于放行数。"""
    n_threads, per_thread = 8, 32
    broker = PolicyBroker(max_actions=n_threads * per_thread)  # 提升限额——隔离 nonce 并发语义
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
    assert broker.session_usage("session-default") == (n_threads * per_thread, 0)  # 计数无丢失


def test_nonce_cache_bounded():
    """SP-156（2026-09-26 审计）：consumed_nonces 有界——容量上限+最旧逐出
    （真机 broker 语义：有界重放缓存——窗口内重放必拒；窗口外随逐出失效）。
    （临时调小容量常量——mock 自恢复，不经 pytest 也能跑。）"""
    with mock.patch.object(PolicyBroker, "NONCE_CACHE_CAPACITY", 8):
        broker = PolicyBroker(max_actions=64)
        for i in range(12):
            assert broker.evaluate(_ok(nonce=f"cap{i}")) == Decision.ALLOW
        assert len(broker.consumed_nonces) == 8          # 容量封顶——不再无界增长
        assert "cap0" not in broker.consumed_nonces      # 最旧已逐出
        assert "cap11" in broker.consumed_nonces         # 最新仍在窗口内
        assert broker.evaluate(_ok(nonce="cap11")) == Decision.DENY_REPLAY  # 窗口内重放仍拒


def test_field_set_matches_schema():
    """SP-067/SP-150（2026-09-26 审计）：直接加载冻结 action.schema.json 提取
    required/properties 集合与 ProposedAction 字段集对比——不再手写集合自证
    （契约新增/删除字段即元断言失败，强制 broker 模型对齐冻结契约）。"""
    schema = json.loads(
        (ROOT.parent / "contracts/schemas/action.schema.json").read_text(encoding="utf-8"))
    fields = {f.name for f in dataclasses.fields(ProposedAction)}
    required = set(schema["required"])
    assert required <= fields, f"broker 模型缺 schema 必填字段: {sorted(required - fields)}"
    properties = set(schema.get("properties", {}))
    assert properties <= fields, f"broker 模型缺 schema 声明字段: {sorted(properties - fields)}"
    # SP-150：expires_at 类型以 schema 为准（string date-time——不再是 unix 秒 float）
    expires_at = next(f for f in dataclasses.fields(ProposedAction) if f.name == "expires_at")
    assert expires_at.type == "str | None"


def test_broker_is_shipped_code_not_test_local():
    """审计第六轮（2026-10-03）：被测 broker 必须是出厂模块——若决策类又回到
    本文件内定义（__module__ 指向测试模块），"红队面在测脚手架"即复发。
    断言 broker 类的归属模块与模块文件真实存在。"""
    owner = PolicyBroker.__module__
    assert owner == "broker", f"被测 broker 来自 {owner}——应为出厂模块 agent/broker.py"
    module_file = pathlib.Path(sys.modules[owner].__file__).resolve()
    assert module_file == (ROOT / "broker.py"), f"broker 模块路径异常: {module_file}"


def test_payload_construction_is_fail_closed():
    """审计第六轮（2026-10-03）：构造边界（proposed_action_from_dict）——未知字段/缺必填/
    bool 冒充 int 都拒，decide 对无法构造的载荷返回 deny（"无法判定"绝不等于放行）。
    R7-TOOL-02：必填面改取 dataclass 无默认字段 ∪ 冻结 schema required。"""
    from broker import BrokerInputError, proposed_action_from_dict

    valid = {"intent": "get_current_title", "scope": "tabs:read", "budget_used": 1,
             "nonce": "pc1", "document_generation": 0, "tab_id": "tab-1",
             "origin": "https://example.test", "method": "GET", "policy_version": "1.0",
             "session_id": "session-default", "canonical_parameters": "{}",
             "expires_at": (datetime.now(UTC) + timedelta(seconds=60)).isoformat()}  # 写死远期值会被 max_ttl 拒
    assert proposed_action_from_dict(valid).intent == "get_current_title"
    for label, mutation in (
        ("未知字段", {"descriptions_hash": "x"}),           # 拼错的字段被静默吞掉=守卫消失
        ("缺构造必填", "nonce"),                             # 删掉 nonce（dataclass 无默认值字段）
        ("缺契约必填", "expires_at"),                        # R7-TOOL-02：省 expires_at ≠ 永久授权
        ("bool 冒充 int", {"budget_used": True}),            # PY-251 口径
    ):
        payload = dict(valid)
        if isinstance(mutation, str):
            payload.pop(mutation)
        else:
            payload.update(mutation)
        try:
            proposed_action_from_dict(payload)
        except BrokerInputError:
            continue
        raise AssertionError(f"载荷构造未拒绝（{label}）: {payload}")
    # schema required 的键**缺失**在构造层即拒（R7-TOOL-02）；显式 null 仍可构造，门在
    # 判定层——canonical_parameters 走 DENY_CANONICAL（比 deny_schema 更具体，口径不变）。
    no_canon = dict(valid, canonical_parameters=None)
    assert PolicyBroker().evaluate(proposed_action_from_dict(no_canon)) == Decision.DENY_CANONICAL
    # decide 入口对畸形载荷同样拒绝（不抛、不放行）
    assert PolicyBroker().decide({"intent": "get_current_title"}) == Decision.DENY_PAYLOAD


if __name__ == "__main__":
    # R7-TOOL-06（第七轮 2026-10-04）：删除本文件的 __main__ 手工运行器。
    # 本套件断言全为裸 `assert`，`python -O` / `PYTHONOPTIMIZE=1` 下在字节码
    # 编译期被整体剥离——原独立运行器实测「声明 deny 实 allow」的注入样例时
    # 打印 ALL OK、exit 0，等于一条环境变量摘掉整套行为门。唯一安全入口是
    # pytest（其重写器把 assert 改写成显式断言，-O 下仍红：实测 `-O -m pytest`
    # 照样 failed）。故直接执行本文件一律响亮失败，不再自行收集运行。
    print("本套件必须经 pytest 运行：python -m pytest -q agent/tests/redteam_e2e_test.py",
          file=sys.stderr)
    raise SystemExit(2)
