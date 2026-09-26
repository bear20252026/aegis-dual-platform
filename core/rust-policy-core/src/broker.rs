//! ContextBroker（照搬 fieldpass/picket ContextBroker 会话池模式）。
//!
//! 管理多个 persona context（会话池），每个 context 独立绑定 session/tab/generation，
//! 并支持原子消费 nonce（一次性、过期、重放拒绝）。
//!
//! 职责：
//! - 维护活跃会话池（HashMap<String, SessionContext>）
//! - 创建/销毁会话（生命周期管理）
//! - 一次性 nonce 消费（原子性——重放拒绝）
//! - 上下文绑定验证（session/tab/generation/scope/policy_version）
//! - 策略评估（policy.evaluate）+ 能力验证（capability.validate）
//!
//! 安全管线（evaluate 方法）：
//!   policy.evaluate(scope, origin) → capability.validate(scope, origin) → session/nonce 验证
//!
//! ⚠️ H-7 审计注记（2026-08-31）：上述三层管线仅在嵌入式宿主直接调用
//! `ContextBroker::evaluate` 时生效。FFI 导航通路（ffi/broker.rs 的
//! evaluate_navigation）执行的是 validate_action——会话/代际/nonce 验证；
//! 策略层与能力层未接入 FFI 通路（直接接线会以默认 deny-all 引擎拒绝
//! 全部导航，属产品级变更）。该口径由 ffi/broker.rs 的
//! ffi_navigation_tests 回归测试锁定。
//!
//! 可拆卸：本模块不依赖 UI/网络/文件，纯内存数据结构。
//! 可拼接：通过 `Decision` trait 与 broker/executor 层对接。

use std::collections::HashMap;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use crate::capability::{CapabilityRegistry, CapabilityResult};
use crate::decision::{AuthorizedAction, Decision, DenyReason};
use crate::policy::PolicyEngine;

/// 已消费 nonce 账本上限——防止长期会话下无界内存增长。
/// fail-closed：达到上限后拒绝新的消费，绝不淘汰旧 nonce（以免削弱一次性/重放保护）。
///
/// RS-171（审计 2026-09-25）：可测试注入——生产 50K 无法在单测内填满
/// （5 万次 consume 的用例是负担）；test profile 下缩小为 256，账本满
/// 的 fail-closed 分支得以真实触达（语义与生产常量无关——分支代码同一份）。
#[cfg(not(test))]
const MAX_CONSUMED_NONCES: usize = 50_000;
#[cfg(test)]
const MAX_CONSUMED_NONCES: usize = 256;

/// RS-034（审计 2026-09-24）：nonce 合法长度上限（字节）——生成端为
/// 32 字节 hex（64 字符）；上限留足余量。空 nonce 与超长 nonce 一律拒绝，
/// 防止攻击者用超长 nonce 撑爆消费账本（键无界驻留内存）。
const MAX_NONCE_LENGTH: usize = 128;

/// M-16 修复（审计 2026-08-31）：会话池软上限——宿主（含 C ABI 直暴露的
/// create_session）无法再无限创建会话耗尽内存；达上限先 evict_expired，
/// 仍满即拒绝新会话（fail-closed）。
///
/// RS-108（审计 2026-09-25）：逐出口径为**过期驱动**而非 LRU 触达——
/// 长 TTL 会话在池满前不会被逐出（ttl 由宿主传入，核心不做时间注入即
/// 无法定义「最久未用」的可靠度量）。宿主约定：对常驻 persona 会话应
/// 使用合理 TTL 并在页面关闭时显式 destroy_session；池满 + 全部未过期
/// 时新会话被拒（fail-closed），不会淘汰任何未过期会话。
const MAX_SESSIONS: usize = 1024;

/// RS-155（审计 2026-09-25）：UNIX 秒单一时间源——本文件内唯一的
/// `SystemTime::now()` 读取点（此前散在 validate_action 内联）。生产路径
/// 经 validate_action 调用；测试经 validate_action_at 注入固定时刻，
/// 不动系统时钟。
fn now_unix_secs() -> Option<u64> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .ok()
        .map(|duration| duration.as_secs())
}

/// 单个会话上下文（persona session——隔离绑定）。
/// 注意：策略版本校验在 `validate_action` 中直接与 broker 的 `policy_version`
/// 比对（fail-closed），而不是挂在会话上，因此会话不再保存一份冗余的
/// `policy_version`，避免"会话级"与"broker 级"版本语义混淆。
#[derive(Debug, Clone)]
pub struct SessionContext {
    /// 会话全局唯一标识（宿主生成——persona 维度隔离键）。
    pub session_id: String,
    /// 会话绑定的标签页 ID——跨标签使用该会话的动作验证将拒绝。
    pub tab_id: String,
    /// 顶层文档代际（页面切换递增）——旧代际签发的授权在推进后即撤销。
    pub generation: u64,
    /// 创建时刻（`Instant::is_expired` 的单调时钟基准，不受系统时间回拨影响）。
    pub created_at: Instant,
    /// 会话存活时长——过期后 `validate_action` 拒绝（原生活动判定过期驱动）。
    pub ttl: Duration,
}

impl SessionContext {
    /// RS-203（审计 2026-09-25）：过期判定的可注入内核——`now` 由调用方
    /// 传入（测试用 `Instant::now() - Duration` 构造虚拟时刻，不动真实
    /// 时钟，无需 sleep）。口径：`> ttl` 严格大于才过期，== ttl 未过期
    /// （与 RS-156 授权过期 `<= now` 的方向一致：边界属于「仍有效」一侧
    /// 语义由各调用点口径锁定，此处严格大于即「到界即拒」由验证方解释）。
    pub fn is_expired_at(&self, now: Instant) -> bool {
        now.saturating_duration_since(self.created_at) > self.ttl
    }

    pub fn is_expired(&self) -> bool {
        self.is_expired_at(Instant::now())
    }
}

/// 一次性 nonce 消费记录（防重放）。
#[derive(Debug, Clone)]
struct NonceRecord {
    session_id: String,
}

/// ContextBroker——会话池 + nonce 消费 + 策略/能力验证管理。
pub struct ContextBroker {
    sessions: HashMap<String, SessionContext>,
    consumed_nonces: HashMap<String, NonceRecord>,
    policy_version: String,
    policy_engine: PolicyEngine,
    capabilities: CapabilityRegistry,
}

impl ContextBroker {
    pub fn new(
        policy_version: String,
        policy_engine: PolicyEngine,
        capabilities: CapabilityRegistry,
    ) -> Self {
        Self {
            sessions: HashMap::new(),
            consumed_nonces: HashMap::new(),
            policy_version,
            policy_engine,
            capabilities,
        }
    }

    /// 创建新会话（persona context）。
    ///
    /// M-16 修复（审计 2026-08-31）：会话池软上限——达到上限先清理过期
    /// 会话（evict_expired 首次接入生产路径），仍满则拒绝（fail-closed），
    /// 堵住宿主无限 create_session 的内存耗尽 DoS 面。原实现同时存在
    /// `insert 后 get 的 unwrap()`（逻辑上不可达的 panic 路径），一并消除。
    ///
    /// RS-033（审计 2026-09-24）：同 id 重复创建为**显式 replace（续期）
    /// 语义**——Android 会话续期契约（renewSession）依赖同 id 覆盖式
    /// 重注册（generation 传当前值，created_at/TTL 重置）。覆盖时旧 nonce
    /// 账本记录保留（重放保护不回退）。此语义由本注释显式声明，勿改回
    /// "静默覆盖"或"拒绝重复 id"（会破坏续期契约）。
    pub fn create_session(
        &mut self,
        session_id: String,
        tab_id: String,
        generation: u64,
        ttl: Duration,
    ) -> Option<&SessionContext> {
        if self.sessions.len() >= MAX_SESSIONS && !self.sessions.contains_key(&session_id) {
            self.evict_expired();
            if self.sessions.len() >= MAX_SESSIONS {
                return None;
            }
        }
        let ctx = SessionContext {
            session_id: session_id.clone(),
            tab_id,
            generation,
            created_at: Instant::now(),
            ttl,
        };
        self.sessions.insert(session_id.clone(), ctx);
        self.sessions.get(&session_id)
    }

    /// 销毁会话（清理 nonce 记录）。
    pub fn destroy_session(&mut self, session_id: &str) {
        self.sessions.remove(session_id);
        self.consumed_nonces
            .retain(|_, r| r.session_id != session_id);
    }

    /// RS-158（审计 2026-09-25）：会话 TTL 查询——可观测性 API（宿主
    /// 诊断会话状态）；FFI TTL 钳制测试经此读取实际生效的 TTL。
    pub fn session_ttl(&self, session_id: &str) -> Option<Duration> {
        self.sessions.get(session_id).map(|ctx| ctx.ttl)
    }

    /// 推进会话的顶层文档代际；只允许同一标签严格单步推进，拒绝回退和跳跃。
    pub fn advance_document_generation(
        &mut self,
        session_id: &str,
        tab_id: &str,
        next_generation: u64,
    ) -> bool {
        let Some(session) = self.sessions.get_mut(session_id) else {
            return false;
        };
        let Some(expected_generation) = session.generation.checked_add(1) else {
            return false;
        };
        if session.tab_id != tab_id || next_generation != expected_generation {
            return false;
        }
        session.generation = next_generation;
        true
    }

    /// 清理过期会话（LRU 淘汰）。
    pub fn evict_expired(&mut self) {
        let expired: Vec<String> = self
            .sessions
            .iter()
            .filter(|(_, ctx)| ctx.is_expired())
            .map(|(id, _)| id.clone())
            .collect();
        for id in expired {
            self.destroy_session(&id);
        }
    }

    /// 完整安全管线：策略评估 → 能力验证 → 会话/nonce 验证。
    ///
    /// 这是修复安全管线断裂的核心方法。之前的 validate_action 只做会话验证，
    /// 现在 evaluate 串联 policy + capability + session 三层检查。
    pub fn evaluate(&mut self, action: &AuthorizedAction) -> Decision {
        // ===== 第 1 层：策略评估 =====
        let verdict = self.policy_engine.evaluate(&action.scope, &action.origin);
        match verdict.decision {
            Decision::Allow(_) => {} // 策略允许，继续下一层
            Decision::Deny(reason) => return Decision::Deny(reason),
            Decision::RequireConfirmation(request) => {
                return Decision::RequireConfirmation(request);
            }
        }

        // ===== 第 2 层：能力验证 =====
        match self.capabilities.validate(&action.scope, &action.origin) {
            CapabilityResult::Allowed(_) => {} // 能力允许，继续下一层
            CapabilityResult::Denied(reason) => {
                return Decision::Deny(DenyReason {
                    code: "capability_denied".into(),
                    detail: reason.clone(),
                    explanation: format!("denied — capability check failed: {}", reason),
                });
            }
        }

        // ===== 第 3 层：会话 + nonce 验证 =====
        self.validate_and_consume(action)
    }

    /// 验证 AuthorizedAction 上下文（fail-closed）。
    /// 保留用于向后兼容和测试，新代码应使用 evaluate()。
    pub fn validate_action(&self, action: &AuthorizedAction) -> Decision {
        // RS-155（审计 2026-09-25）：UNIX 秒单一时间源 now_unix_secs——
        // 授权过期判定的时刻由此注入，边界语义（RS-156）经
        // validate_action_at 固定时刻锁定，测试不动系统时钟。
        // 口径说明：时钟不可用优先于会话查找返回（两个结果均为 fail-closed
        // Deny，顺序仅影响错误码归因，不改变拒绝语义）。
        match now_unix_secs() {
            Some(now) => self.validate_action_at(action, now),
            None => Decision::Deny(DenyReason {
                code: "system_clock".into(),
                detail: "系统时间不可用".into(),
                explanation: "denied — system clock is before UNIX epoch".into(),
            }),
        }
    }

    /// validate_action 的可测内核——`now` 由调用方注入（RS-155）。
    ///
    /// 检查顺序：会话存在 → 会话过期（单调时钟 Instant）→ 授权过期
    /// （UNIX 秒）→ 策略版本 → 代际绑定 → 标签绑定。
    fn validate_action_at(&self, action: &AuthorizedAction, now: u64) -> Decision {
        // 检查会话存在
        let session = match self.sessions.get(&action.session_id) {
            Some(s) => s,
            None => {
                return Decision::Deny(DenyReason {
                    code: "session_not_found".into(),
                    detail: format!("会话 {} 不存在或已过期", action.session_id),
                    explanation: format!(
                        "denied — session {} not found — policy version {}",
                        action.session_id, action.policy_version
                    ),
                });
            }
        };

        // 检查会话过期
        if session.is_expired() {
            return Decision::Deny(DenyReason {
                code: "session_expired".into(),
                detail: format!("会话 {} 已过期", action.session_id),
                explanation: format!(
                    "denied — session {} expired — policy version {}",
                    action.session_id, action.policy_version
                ),
            });
        }

        // RS-156（审计 2026-09-25）：边界口径 == now 即过期——expires_at
        // 是「失效时刻」而非「最后有效时刻」，等于当前时刻的授权已到界。
        // 由 action_expires_at_boundary_* 测试锁定（注入固定 now）。
        if action.expires_at <= now {
            return Decision::Deny(DenyReason {
                code: "action_expired".into(),
                detail: "授权动作已过期".into(),
                explanation: format!(
                    "denied — action expired at {}, current time {}",
                    action.expires_at, now
                ),
            });
        }

        // 检查策略版本
        if action.policy_version != self.policy_version {
            return Decision::Deny(DenyReason {
                code: "policy_version_mismatch".into(),
                detail: format!(
                    "策略版本不匹配：期望 {}，实际 {}",
                    self.policy_version, action.policy_version
                ),
                explanation: format!(
                    "denied — policy version mismatch: expected {}, got {}",
                    self.policy_version, action.policy_version
                ),
            });
        }

        // 检查代际绑定
        if action.document_generation != session.generation {
            return Decision::Deny(DenyReason {
                code: "generation_mismatch".into(),
                detail: format!(
                    "代际不匹配：会话代际 {}，操作代际 {}",
                    session.generation, action.document_generation
                ),
                explanation: format!(
                    "denied — generation mismatch: session {}, action {}",
                    session.generation, action.document_generation
                ),
            });
        }

        if action.tab_id != session.tab_id {
            return Decision::Deny(DenyReason {
                code: "tab_mismatch".into(),
                detail: format!(
                    "标签不匹配：期望 {}，实际 {}",
                    session.tab_id, action.tab_id
                ),
                explanation: format!(
                    "denied — tab mismatch: expected {}, got {}",
                    session.tab_id, action.tab_id
                ),
            });
        }

        Decision::Allow(action.clone())
    }

    /// 校验并消费授权动作。调用方应只在即将执行本地副作用时调用，
    /// 以确保通过校验的 nonce 不能被重放。
    pub fn validate_and_consume(&mut self, action: &AuthorizedAction) -> Decision {
        match self.validate_action(action) {
            Decision::Allow(authorized) => {
                match self.consume_nonce(&authorized.nonce, &authorized.session_id) {
                    Ok(()) => Decision::Allow(authorized),
                    Err(reason) => Decision::Deny(reason),
                }
            }
            Decision::RequireConfirmation(request) => Decision::RequireConfirmation(request),
            Decision::Deny(reason) => Decision::Deny(reason),
        }
    }

    /// 原子消费 nonce（一次性——重放拒绝）。
    pub fn consume_nonce(&mut self, nonce: &str, session_id: &str) -> Result<(), DenyReason> {
        // RS-034（审计 2026-09-24）：空 nonce 与超长 nonce 拒绝入账——
        // 此前无界接受（超长 nonce 直接作为账本键驻留内存）
        if nonce.is_empty() || nonce.len() > MAX_NONCE_LENGTH {
            return Err(DenyReason {
                code: "nonce_invalid".into(),
                detail: format!(
                    "nonce 长度非法（{} 字节，允许 1..={MAX_NONCE_LENGTH}）",
                    nonce.len()
                ),
                explanation: format!(
                    "denied — nonce length {} out of range 1..={MAX_NONCE_LENGTH}",
                    nonce.len()
                ),
            });
        }
        if self.consumed_nonces.contains_key(nonce) {
            let record = &self.consumed_nonces[nonce];
            return Err(DenyReason {
                code: "nonce_replay".into(),
                detail: format!(
                    "nonce {} 已被消费（会话 {}）——重放拒绝",
                    nonce, record.session_id
                ),
                explanation: format!(
                    "denied — nonce {} already consumed by session {} — replay rejected",
                    nonce, record.session_id
                ),
            });
        }

        // 账本已达上限：fail-closed 拒绝，绝不淘汰旧记录。
        if self.consumed_nonces.len() >= MAX_CONSUMED_NONCES {
            return Err(DenyReason {
                code: "nonce_ledger_full".into(),
                detail: format!("nonce 账本已达上限 {MAX_CONSUMED_NONCES}"),
                explanation: format!(
                    "denied — nonce ledger full ({MAX_CONSUMED_NONCES}) — fail-closed"
                ),
            });
        }

        self.consumed_nonces.insert(
            nonce.to_string(),
            NonceRecord {
                session_id: session_id.to_string(),
            },
        );
        Ok(())
    }

    /// 当前活跃会话数。
    pub fn active_session_count(&self) -> usize {
        self.sessions.len()
    }

    /// 当前已消费 nonce 数。
    pub fn consumed_nonce_count(&self) -> usize {
        self.consumed_nonces.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::capability::{Capability, CapabilityScope};
    use crate::decision::AuthorizedAction;
    use crate::policy::PolicyEngine;

    // edition 2024：`gen` 成为保留关键字——参数更名 generation
    fn make_action(session: &str, generation: u64, nonce: &str) -> AuthorizedAction {
        AuthorizedAction {
            session_id: session.into(),
            tab_id: "tab-0".into(),
            document_generation: generation,
            origin: "https://example.com".into(),
            method: "GET".into(),
            canonical_parameters: "/".into(),
            scope: "navigation:read".into(),
            expires_at: 9999999999,
            nonce: nonce.into(),
            policy_version: "1.0".into(),
            explanation: String::new(),
        }
    }

    fn make_broker_with_defaults() -> ContextBroker {
        ContextBroker::new(
            "1.0".into(),
            PolicyEngine::default(),
            CapabilityRegistry::new(),
        )
    }

    fn make_broker_with_policy_and_capability() -> ContextBroker {
        let mut registry = CapabilityRegistry::new();
        registry.register(Capability::new(
            "navigation:read",
            CapabilityScope::Read,
            vec![],
            None,
        ));
        ContextBroker::new("1.0".into(), PolicyEngine::default(), registry)
    }

    #[test]
    fn create_and_validate_session() {
        let mut broker = make_broker_with_defaults();
        broker.create_session("s1".into(), "tab-0".into(), 1, Duration::from_secs(3600));
        let action = make_action("s1", 1, "n1");
        let result = broker.validate_action(&action);
        assert!(matches!(result, Decision::Allow(_)));
    }

    #[test]
    fn session_not_found_is_deny() {
        let broker = make_broker_with_defaults();
        let action = make_action("missing", 1, "n1");
        let result = broker.validate_action(&action);
        assert!(matches!(result, Decision::Deny(_)));
    }

    #[test]
    fn policy_version_mismatch_is_deny() {
        let mut broker = make_broker_with_defaults();
        broker.create_session("s1".into(), "t1".into(), 1, Duration::from_secs(3600));
        let mut action = make_action("s1", 1, "n1");
        action.policy_version = "2.0".into();
        let result = broker.validate_action(&action);
        assert!(matches!(result, Decision::Deny(_)));
    }

    #[test]
    fn generation_mismatch_is_deny() {
        let mut broker = make_broker_with_defaults();
        broker.create_session("s1".into(), "t1".into(), 1, Duration::from_secs(3600));
        let action = make_action("s1", 999, "n1");
        let result = broker.validate_action(&action);
        assert!(matches!(result, Decision::Deny(_)));
    }

    #[test]
    fn nonce_consume_once_ok() {
        let mut broker = make_broker_with_defaults();
        assert!(broker.consume_nonce("n1", "s1").is_ok());
    }

    #[test]
    fn nonce_replay_rejected() {
        let mut broker = make_broker_with_defaults();
        broker.consume_nonce("n1", "s1").unwrap();
        let result = broker.consume_nonce("n1", "s2");
        assert!(result.is_err());
    }

    #[test]
    fn nonce_empty_and_oversized_rejected() {
        // RS-034 回归：空 nonce 与超长 nonce 一律拒绝入账
        let mut broker = make_broker_with_defaults();
        assert!(broker.consume_nonce("", "s1").is_err(), "空 nonce 拒绝");
        assert_eq!(broker.consumed_nonce_count(), 0);
        let oversized = "x".repeat(129);
        assert!(
            broker.consume_nonce(&oversized, "s1").is_err(),
            "超长 nonce 拒绝"
        );
        assert_eq!(broker.consumed_nonce_count(), 0);
        // 边界内（128 字节）放行
        let at_cap = "x".repeat(128);
        assert!(broker.consume_nonce(&at_cap, "s1").is_ok());
    }

    #[test]
    fn expired_action_is_denied() {
        let mut broker = make_broker_with_defaults();
        broker.create_session("s1".into(), "tab-0".into(), 1, Duration::from_secs(3600));
        let mut action = make_action("s1", 1, "n1");
        action.expires_at = 0;
        assert!(matches!(broker.validate_action(&action), Decision::Deny(_)));
    }

    #[test]
    fn wrong_tab_is_denied() {
        let mut broker = make_broker_with_defaults();
        broker.create_session("s1".into(), "tab-0".into(), 1, Duration::from_secs(3600));
        let mut action = make_action("s1", 1, "n1");
        action.tab_id = "other-tab".into();
        assert!(matches!(broker.validate_action(&action), Decision::Deny(_)));
    }

    #[test]
    fn validate_and_consume_rejects_replay() {
        let mut broker = make_broker_with_defaults();
        broker.create_session("s1".into(), "tab-0".into(), 1, Duration::from_secs(3600));
        let action = make_action("s1", 1, "n1");
        assert!(matches!(
            broker.validate_and_consume(&action),
            Decision::Allow(_)
        ));
        assert!(matches!(
            broker.validate_and_consume(&action),
            Decision::Deny(_)
        ));
    }

    #[test]
    fn document_generation_requires_the_same_tab_and_next_step() {
        let mut broker = make_broker_with_defaults();
        broker.create_session("s1".into(), "tab-0".into(), 4, Duration::from_secs(3600));

        assert!(!broker.advance_document_generation("s1", "other-tab", 5));
        assert!(!broker.advance_document_generation("s1", "tab-0", 6));
        assert!(!broker.advance_document_generation("s1", "tab-0", 4));
        assert!(broker.advance_document_generation("s1", "tab-0", 5));
        assert!(matches!(
            broker.validate_action(&make_action("s1", 5, "n2")),
            Decision::Allow(_)
        ));
    }

    #[test]
    fn destroyed_session_cannot_advance_document_generation() {
        let mut broker = make_broker_with_defaults();
        broker.create_session("s1".into(), "tab-0".into(), 0, Duration::from_secs(3600));
        broker.destroy_session("s1");

        assert!(!broker.advance_document_generation("s1", "tab-0", 1));
    }

    // ===== 新增：安全管线集成测试 =====

    #[test]
    fn evaluate_denies_when_capability_not_registered() {
        // 默认 PolicyEngine 使用 DefaultLocalPolicy（deny-all），
        // 未注册的 capability 也应该被拒绝
        let mut broker = make_broker_with_defaults();
        broker.create_session("s1".into(), "tab-0".into(), 1, Duration::from_secs(3600));
        let action = make_action("s1", 1, "n1");
        let result = broker.evaluate(&action);
        assert!(matches!(result, Decision::Deny(_)));
    }

    #[test]
    fn evaluate_denies_under_default_deny_policy_even_with_capability() {
        // RS-042 更名：原名 evaluate_allows_when_capability_registered 与断言
        // 相反（实际期望 Deny）——默认 PolicyEngine 为 deny-all，策略层先拒绝
        let mut broker = make_broker_with_policy_and_capability();
        broker.create_session("s1".into(), "tab-0".into(), 1, Duration::from_secs(3600));
        let action = make_action("s1", 1, "n1");
        let result = broker.evaluate(&action);
        assert!(matches!(result, Decision::Deny(_)));
    }

    /// RS-042：本地策略显式 Allow 的正向用例——策略层放行 + 能力层放行 +
    /// 会话/nonce 校验通过 → evaluate 全链路 Allow；同 nonce 二次评估被重放拒绝。
    struct AlwaysAllowLocalPolicy;

    impl crate::policy::LocalPolicy for AlwaysAllowLocalPolicy {
        fn evaluate(&self, _action: &str, _context: &str) -> Option<Decision> {
            Some(Decision::Allow(AuthorizedAction {
                session_id: String::new(),
                tab_id: String::new(),
                document_generation: 0,
                origin: String::new(),
                method: String::new(),
                canonical_parameters: String::new(),
                scope: String::new(),
                expires_at: 0,
                nonce: String::new(),
                policy_version: String::new(),
                explanation: "always allow (test mock)".into(),
            }))
        }
    }

    #[test]
    fn evaluate_full_chain_allows_and_consumes_nonce_once() {
        let mut registry = CapabilityRegistry::new();
        registry.register(Capability::new(
            "navigation:read",
            CapabilityScope::Read,
            // 空白名单 = fail-closed 拒绝——全放行必须显式 "*"（is_origin_allowed）
            vec!["*".into()],
            None,
        ));
        let mut broker = ContextBroker::new(
            "1.0".into(),
            PolicyEngine::new(Box::new(AlwaysAllowLocalPolicy), None),
            registry,
        );
        broker.create_session("s1".into(), "tab-0".into(), 1, Duration::from_secs(3600));
        let action = make_action("s1", 1, "n1");
        let first = broker.evaluate(&action);
        assert!(
            matches!(first, Decision::Allow(_)),
            "策略+能力+会话三层全过必须 Allow，实际 {first:?}"
        );
        assert_eq!(broker.consumed_nonce_count(), 1, "nonce 必须入账");
        // evaluate 内部走 validate_and_consume——同 nonce 第二次评估重放拒绝
        let replay = broker.evaluate(&action);
        match replay {
            Decision::Deny(reason) => assert_eq!(reason.code, "nonce_replay"),
            other => panic!("同 nonce 重放必须拒绝，实际 {other:?}"),
        }
    }

    #[test]
    fn destroy_session_clears_consumed_nonces() {
        // RS-043 回归：destroy_session 必须同步清理该会话的 nonce 账本记录；
        // 其他会话的记录不受影响（retain 精确过滤）
        let mut broker = make_broker_with_defaults();
        broker.consume_nonce("n1", "s1").unwrap();
        broker.consume_nonce("n2", "s2").unwrap();
        assert_eq!(broker.consumed_nonce_count(), 2);
        broker.destroy_session("s1");
        assert_eq!(broker.consumed_nonce_count(), 1, "s1 的 nonce 记录应被清除");
        // n1 记录已清——换个会话重新消费可入账（账本不再含旧记录）
        assert!(broker.consume_nonce("n1", "s3").is_ok());
        // s2 的 nonce 记录不受影响——重放依旧拒绝
        assert!(broker.consume_nonce("n2", "s2").is_err());
    }
    #[test]
    fn session_pool_cap_fails_closed() {
        // M-16 回归：会话池达上限后拒绝新会话；销毁后可复用容量
        let mut broker = ContextBroker::new(
            "pv".into(),
            PolicyEngine::default(),
            CapabilityRegistry::new(),
        );
        for i in 0..MAX_SESSIONS {
            assert!(broker
                .create_session(format!("s{i}"), "t".into(), 1, Duration::from_secs(60))
                .is_some());
        }
        assert!(broker
            .create_session("overflow".into(), "t".into(), 1, Duration::from_secs(60))
            .is_none());
        broker.destroy_session("s0");
        assert!(broker
            .create_session("overflow".into(), "t".into(), 1, Duration::from_secs(60))
            .is_some());
    }

    // —— RS-107 回归（审计 2026-09-25）：过期/逐出/续期语义 ——

    #[test]
    fn zero_ttl_session_expires_and_evicts() {
        // RS-107：过期判定 + evict_expired 真实逐出（ttl=0 即创建即过期）
        let mut broker = make_broker_with_defaults();
        broker.create_session("ephemeral".into(), "t".into(), 1, Duration::ZERO);
        broker.create_session("durable".into(), "t".into(), 1, Duration::from_secs(3600));
        // sleep 2ms 保证 elapsed > 0（纳秒时钟竞态防御）
        std::thread::sleep(Duration::from_millis(2));
        broker.evict_expired();
        assert!(
            !broker.sessions.contains_key("ephemeral"),
            "ttl=0 会话必须被逐出"
        );
        assert!(broker.sessions.contains_key("durable"), "未过期会话保留");
    }

    #[test]
    fn expired_sessions_evicted_before_deny_at_cap() {
        // RS-107：池满时先清过期——有过期会话在池中则新会话不拒绝（M-16
        // fail-closed 仅对「全满且全部未过期」生效）
        let mut broker = ContextBroker::new(
            "pv".into(),
            PolicyEngine::default(),
            CapabilityRegistry::new(),
        );
        broker.create_session("dead".into(), "t".into(), 1, Duration::ZERO);
        // sleep 2ms 保证 dead 会话过期（纳秒时钟竞态防御）
        std::thread::sleep(Duration::from_millis(2));
        for i in 1..MAX_SESSIONS {
            broker.create_session(format!("s{i}"), "t".into(), 1, Duration::from_secs(60));
        }
        assert_eq!(broker.active_session_count(), MAX_SESSIONS);
        // 池满但含过期会话——新会话成功（evict_expired 腾位）
        assert!(
            broker
                .create_session("fresh".into(), "t".into(), 1, Duration::from_secs(60))
                .is_some(),
            "池满但有过期会话时必须先逐出再接纳"
        );
    }

    #[test]
    fn same_id_create_is_renewal_not_reset() {
        // RS-107/RS-033：同 id 重复创建 = 续期语义——nonce 账本记录保留
        //（重放保护不回退），新会话可继续消费新 nonce
        let mut broker = make_broker_with_defaults();
        broker.create_session("s1".into(), "t".into(), 1, Duration::from_secs(60));
        assert!(broker.consume_nonce("n1", "s1").is_ok());
        // 续期（同 id 覆盖式重注册——renewSession 契约）
        broker
            .create_session("s1".into(), "t".into(), 1, Duration::from_secs(120))
            .expect("同 id 续期必须成功");
        // 旧 nonce 记录保留——重放依旧拒绝（重放保护不因续期回退）
        assert!(
            broker.consume_nonce("n1", "s1").is_err(),
            "续期后旧 nonce 重放仍必须拒绝"
        );
        // 新 nonce 正常入账
        assert!(broker.consume_nonce("n2", "s1").is_ok());
    }

    #[test]
    fn nonce_length_bounds_enforced() {
        // RS-107：nonce 长度边界——空与超 128 字节拒绝入账（RS-034 语义）
        let mut broker = make_broker_with_defaults();
        assert!(broker.consume_nonce("", "s1").is_err(), "空 nonce 拒绝");
        let long = "a".repeat(MAX_NONCE_LENGTH + 1);
        assert!(
            broker.consume_nonce(&long, "s1").is_err(),
            "超长 nonce 拒绝"
        );
        let max_ok = "a".repeat(MAX_NONCE_LENGTH);
        assert!(
            broker.consume_nonce(&max_ok, "s1").is_ok(),
            "恰 128 字节放行"
        );
    }

    // —— RS-155/156（审计 2026-09-25）：时钟注入 + expires_at 边界 ——

    /// 注入式边界测试通用会话：默认 make_broker_with_defaults 均可，
    /// 会话 ttl 取 3600s 保证测试期间不因会话过期干扰归因。
    fn broker_for_expiry_tests() -> ContextBroker {
        let mut broker = make_broker_with_defaults();
        broker.create_session("s1".into(), "tab-0".into(), 1, Duration::from_secs(3600));
        broker
    }

    #[test]
    fn action_expires_at_equal_to_now_is_denied() {
        // RS-156：expires_at == now 即过期——expires_at 是「失效时刻」
        // 而非「最后有效时刻」，等于当前时刻的授权已到界（`<=` 口径锁定）
        let broker = broker_for_expiry_tests();
        let mut action = make_action("s1", 1, "n1");
        action.expires_at = 1_000_000_000;
        match broker.validate_action_at(&action, 1_000_000_000) {
            Decision::Deny(reason) => assert_eq!(reason.code, "action_expired"),
            other => panic!("expires_at == now 必须拒绝，实际 {other:?}"),
        }
    }

    #[test]
    fn action_expires_at_one_second_after_now_is_allowed() {
        // RS-156：边界内侧——now+1 仍在窗口内（授权语义：签发即含
        // ACTION_EXPIRY_SECONDS 窗口，到期前一秒必须可用）
        let broker = broker_for_expiry_tests();
        let mut action = make_action("s1", 1, "n1");
        action.expires_at = 1_000_000_001;
        assert!(matches!(
            broker.validate_action_at(&action, 1_000_000_000),
            Decision::Allow(_)
        ));
    }

    #[test]
    fn action_expires_at_past_is_denied() {
        let broker = broker_for_expiry_tests();
        let mut action = make_action("s1", 1, "n1");
        action.expires_at = 999_999_999;
        match broker.validate_action_at(&action, 1_000_000_000) {
            Decision::Deny(reason) => assert_eq!(reason.code, "action_expired"),
            other => panic!("expires_at < now 必须拒绝，实际 {other:?}"),
        }
    }

    #[test]
    fn validate_action_time_source_is_single_point() {
        // RS-155：validate_action 生产路径自身取时——此处验证拆分后
        // 生产入口与注入内核语义一致（同 action 同判定，取 now 自然推进）
        let broker = broker_for_expiry_tests();
        let action = make_action("s1", 1, "n1"); // expires_at 9999999999（2286 年）
        assert!(matches!(
            broker.validate_action(&action),
            Decision::Allow(_)
        ));
        assert!(now_unix_secs().is_some(), "生产时间源必须可用");
    }

    #[test]
    fn session_ttl_query_reports_effective_ttl() {
        // RS-158 配套：session_ttl 可观测性 API
        let mut broker = make_broker_with_defaults();
        broker.create_session("s1".into(), "t".into(), 1, Duration::from_secs(120));
        broker.create_session("s2".into(), "t".into(), 1, Duration::ZERO);
        assert_eq!(broker.session_ttl("s1"), Some(Duration::from_secs(120)));
        assert_eq!(broker.session_ttl("s2"), Some(Duration::ZERO));
        assert_eq!(broker.session_ttl("missing"), None);
        broker.destroy_session("s1");
        assert_eq!(broker.session_ttl("s1"), None, "销毁后查询为 None");
    }

    // —— RS-171/183/203（审计 2026-09-25）——

    #[test]
    fn nonce_ledger_full_fails_closed_at_injected_cap() {
        // RS-171：test profile 下 MAX_CONSUMED_NONCES=256——账本满后新
        // nonce 消费拒绝（fail-closed，绝不淘汰旧记录），分支此前因生产
        // 常量 50K 无法在单测内触达
        let mut broker = make_broker_with_defaults();
        for i in 0..MAX_CONSUMED_NONCES {
            broker
                .consume_nonce(&format!("nonce-{i:016x}"), "s-ledger")
                .unwrap_or_else(|e| panic!("第 {i} 条必须入账: {e:?}"));
        }
        assert_eq!(broker.consumed_nonce_count(), MAX_CONSUMED_NONCES);
        // 满后新 nonce：nonce_ledger_full 拒绝
        let err = broker
            .consume_nonce("nonce-after-full", "s-ledger")
            .expect_err("账本满必须拒绝");
        assert_eq!(err.code, "nonce_ledger_full");
        assert_eq!(
            broker.consumed_nonce_count(),
            MAX_CONSUMED_NONCES,
            "拒绝路径不得改变账本规模（无淘汰）"
        );
        // 既有 nonce 重放语义不受账本满影响（重放检查先于上限检查）
        let replay = broker
            .consume_nonce("nonce-0000000000000000", "s-ledger")
            .expect_err("已入账 nonce 重放必须拒绝");
        assert_eq!(replay.code, "nonce_replay");
    }

    #[test]
    fn generation_advance_at_u64_max_rejects_overflow() {
        // RS-183：checked_add 溢出分支——generation == u64::MAX 时再推进
        // 必须拒绝（此前分支不可达未测：正常会话代际永远到不了 MAX）
        let mut broker = make_broker_with_defaults();
        broker.create_session(
            "s-max".into(),
            "tab-0".into(),
            u64::MAX - 1,
            Duration::from_secs(120),
        );
        // 最后一步正常推进到 u64::MAX
        assert!(
            broker.advance_document_generation("s-max", "tab-0", u64::MAX),
            "u64::MAX-1 → u64::MAX 必须成功"
        );
        // 溢出分支：MAX + 1 无可表示值 → false（fail-closed）
        assert!(
            !broker.advance_document_generation("s-max", "tab-0", u64::MAX),
            "自 MAX 再推进应拒绝"
        );
        // 会话代际保持 MAX（未推进）
        let action = make_action("s-max", u64::MAX, "nonce-overflow");
        assert!(matches!(
            broker.validate_action(&action),
            Decision::Allow(_)
        ));
    }

    #[test]
    fn session_expiry_injected_clock_boundaries() {
        // RS-203：is_expired_at 注入内核——虚拟时刻构造（Instant 回拨
        // 减法），边界口径锁定：== ttl 未过期（严格大于才过期），
        // 无需真实 sleep
        let ttl = Duration::from_secs(60);
        let ctx = SessionContext {
            session_id: "s".into(),
            tab_id: "t".into(),
            generation: 1,
            created_at: Instant::now(),
            ttl,
        };
        // 刚创建：远未过期
        assert!(!ctx.is_expired_at(Instant::now()));
        // == ttl：未过期（> 严格大于口径）
        let at_boundary = ctx.created_at + ttl;
        assert!(
            !ctx.is_expired_at(at_boundary),
            "== ttl 未过期（严格大于口径锁定）"
        );
        // ttl + 1ns：过期
        assert!(ctx.is_expired_at(at_boundary + Duration::from_nanos(1)));
        // 早于 created_at 的时刻（时钟回拨形态）：差值为 0 方向饱和，未过期
        assert!(!ctx.is_expired_at(ctx.created_at - Duration::from_secs(1)));
    }
}
