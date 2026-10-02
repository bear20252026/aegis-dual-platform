//! FfiBroker——UniFFI 有状态对象（H-4 拆分自 ffi.rs，行为不变）。

use super::*;

// ===== UniFFI Object（有状态对象——跨调用保持状态）=====

/// FFI 版 Broker——跨语言导航决策（委托 ContextBroker）。
///
/// 平台运行时接入须使用生成的绑定和受验证的原生制品；在此之前此类型仅定义共享边界。
/// 内部用 Mutex 提供可变性——UniFFI Object 方法只支持 &self（Arc 只读）。
#[derive(uniffi::Object)]
pub struct FfiBroker {
    inner: std::sync::Mutex<crate::broker::ContextBroker>,
    /// 仅允许消费本 Broker 签发且仍处于当前会话生命周期内的授权。
    /// 这阻止宿主伪造结构正确的 FFI 授权对象绕过策略评估。
    issued_actions: std::sync::Mutex<HashMap<String, IssuedAuthorization>>,
    /// 仅由策略核心登记的待审批动作；平台不能凭展示用请求重建授权。
    pending_navigation_approvals: std::sync::Mutex<HashMap<String, AuthorizedAction>>,
    policy_version: String,
    /// RS-270：授权过期窗口（秒）——生产恒为 ACTION_EXPIRY_SECONDS；
    /// 测试构造器注入极小值触达过期分支
    action_expiry_seconds: u64,
    /// RS-300（2026-10-02 审计）：授权账本容量——生产恒为 MAX_ISSUED_ACTIONS
    ///（50K）；测试构造器注入小容量，fail-closed 满账本分支经公共路径
    ///（evaluate/approve/consume）真实触达（50K 次公共调用在单测内是负担）
    max_issued_actions: usize,
}

/// 原生策略核心签发的授权状态。已消费记录保留到会话撤销，
/// 使精确重放仍可返回 `nonce_replay`，而不是退化为未签发。
#[derive(Debug, Clone)]
enum IssuedAuthorization {
    Pending(Box<AuthorizedAction>),
    Consumed { session_id: String },
}

/// RS-270（2026-10-01 审计）：ACTION_EXPIRY_SECONDS 可测参数化——
/// FfiBroker 持有过期窗口（生产构造器恒取默认常量；测试构造器注入
/// 极小窗口使「过期 approve/consume 拒绝」分支可真实触达）。
#[cfg(test)]
const TEST_ACTION_EXPIRY_SECONDS: u64 = 0;

/// M-15 修复（审计 2026-08-31）：授权账本上限——镜像 consumed_nonces 的
/// fail-closed 模式（满时先惰性清理，仍满即拒绝，绝不无界增长）。
const MAX_ISSUED_ACTIONS: usize = 50_000;

/// P1-10 修复（全量复审 2026-09-01）：导航授权动作有效期（秒）——
/// 原 120 为硬编码字面量（无语义名、多处漂移风险）。注意与「会话 TTL」
/// 是两个概念：这是签发授权的可消费窗口，超期后 consume 过期拒绝。
const ACTION_EXPIRY_SECONDS: u64 = 120;
/// 审计整改（2026-09-07）：待审批导航账本上限。此前无容量/清理——可被
/// 待审批请求堆叠造成内存 DoS；满则 fail-closed 拒绝（镜像 MAX_ISSUED_ACTIONS）。
const MAX_PENDING_APPROVALS: usize = 1024;
/// P1-11 修复（全量复审 2026-09-01）：FFI create_session 的 TTL 下限（秒）。
/// 宿主传 0 会得到"返回成功、即刻过期"的静默失效会话——钳到下限保底。
const MIN_SESSION_TTL_SECONDS: u64 = 30;
/// RS-158（审计 2026-09-25）：FFI create_session 的 TTL 上限（秒，24h）——
/// 与下限对称的钳制口径。此前上限自由：宿主可传 u64::MAX 使会话近乎永生，
/// 会话与 nonce/授权账本的驻留暴露面随之无界。超过钳到上限；常驻 persona
/// 会话按宿主约定应显式续期（RS-033 replace 语义）而非一次签发永生会话。
/// 会话总量的内存上限另由 M-16 会话池 fail-closed 容量约束（两个正交维度）。
const MAX_SESSION_TTL_SECONDS: u64 = 86_400;
/// RS-223（2026-09-26 审计）：FFI create_session 的键长度上限（字节）——
/// 与 core 层 session_state::from_json 的 MAX_TAB_ID_LEN=256 对齐。此前仅
/// 查空串：会话池 1024 × 64KB 双键 ≈128MB 键驻留面（宿主 FFI 边界是
/// 键长度的第一道防线，core 层上限管不到本入口）。
const MAX_SESSION_KEY_BYTES: usize = 256;

/// RS-253（2026-10-01 审计）：UniFFI 构造器的空 policy_version 默认值——
/// C ABI（aegis_policy_core_broker_new）对空版本返回 null 拒绝；UniFFI
/// constructor 签名必须返回 Self（不可失败），无法同拒。行为分叉按
/// 「默认版本」收口：空版本在此替换为显式哨兵（文档化），授权签发与
/// 校验仍自洽（action.policy_version == broker.policy_version）。
const DEFAULT_POLICY_VERSION: &str = "unversioned";

/// RS-254（2026-10-01 审计）：evaluate_navigation 的 scope 长度上限（字节）
/// ——与 RS-223 会话键 256 对齐。此前 scope 无长度上限（RS-223 只限会话
/// 键）：授权账本以 nonce 为键不受直接影响，但 issued action 携带任意长
/// scope 串驻留内存（宿主 FFI 边界是第一道防线）。
const MAX_SCOPE_BYTES: usize = 256;

/// RS-282（2026-10-02 审计）：redact_url_for_log 的 host 段截断上限（字节）
/// ——deny 文案内嵌 host，host 由 URL 攻击者可控；脱敏函数自身不得成为
/// 任意长文案的放大面。
const MAX_REDACT_HOST_BYTES: usize = 256;

/// RS-287（2026-10-02 审计）：Pending 授权/待审批的过期判定单源——与
/// RS-156 validate_action 的 `expires_at <= now` 口径一致（== now 即过期）。
/// 此前两处惰性清理用 `expires_at >= now` 保留 == 边界条目（已过期却
/// 驻留到下一秒，账本清理口径与验证口径分叉）。
fn pending_expired_at(expires_at: u64, now: u64) -> bool {
    expires_at <= now
}

impl IssuedAuthorization {
    fn session_id(&self) -> &str {
        match self {
            Self::Pending(action) => &action.session_id,
            Self::Consumed { session_id } => session_id,
        }
    }
}

#[uniffi::export]
impl FfiBroker {
    /// 创建 Broker（policy_version 锁定——INV-03 一致性）。
    ///
    /// RS-253（2026-10-01 审计）：空 policy_version 默认化——C ABI 对空版本
    /// 返回 null；UniFFI constructor 不可失败，无法同拒。空串在此替换为
    /// DEFAULT_POLICY_VERSION 哨兵（授权签发/校验自洽），行为分叉以
    /// 「默认版本」收口（audit 提供的两选项之一），一致性由
    /// empty_policy_version_defaults_on_uniffi_path 测试锁定。
    #[uniffi::constructor]
    pub fn new(policy_version: String) -> Self {
        Self::with_action_expiry(policy_version, ACTION_EXPIRY_SECONDS)
    }

    /// 评估导航意图（URL 解析 + 会话验证 → FfiDecision——fail-closed）。
    ///
    /// 职责边界（H-7）：本通路仅执行会话/代际/nonce 验证，policy.evaluate /
    /// capability.validate 未接入 FFI 通路——单一事实源见 broker.rs 模块文档
    /// H-7 审计注记，FFI 语义由本文件 ffi_navigation_tests 回归测试锁定。
    pub fn evaluate_navigation(
        &self,
        session_id: String,
        tab_id: String,
        generation: u64,
        raw_url: String,
        scope: String,
    ) -> FfiDecision {
        // RS-254：scope 长度上限（256——与 RS-223 会话键同口径）
        if scope.len() > MAX_SCOPE_BYTES {
            return ffi_deny(
                "ffi_scope_too_long",
                &format!("scope 超长（{} 字节，上限 {MAX_SCOPE_BYTES}）", scope.len()),
                "denied — scope exceeds the 256-byte FFI boundary cap",
            );
        }
        // RS-282（2026-10-02 审计）：raw_url 前置长度上限——URL 三入口
        //（try_parse/canonicalize/extract_host）有 MAX_FFI_URL_BYTES 防线，
        // 本入口此前直通 canonicalize_external（origin 侧 8KB 是第二道
        // 防线，深解析的 O(n) 已发生）。超长先拒，不做任何深解析
        if raw_url.len() > MAX_FFI_URL_BYTES {
            return ffi_deny(
                "ffi_url_too_long",
                &format!(
                    "URL 超长（{} 字节，上限 {MAX_FFI_URL_BYTES}）",
                    raw_url.len()
                ),
                "denied — raw URL exceeds the 64KB FFI boundary cap",
            );
        }
        // URL 解析（fail-closed：解析失败 → Deny）
        let canonical_url = match crate::origin::canonicalize_external(&raw_url) {
            Some(p) => p,
            None => {
                // RS-258（2026-10-01 审计）：deny 文案不内嵌完整明文 URL——
                // query（token 载体）/userinfo 剥除后再组装（AD-211 认识的
                // Rust 侧同步）
                let redacted = redact_url_for_log(&raw_url);
                return FfiDecision::Deny {
                    reason: FfiDenyReason {
                        code: "url_policy".into(),
                        detail: format!("拒绝 URL: {redacted}"),
                        explanation: format!("denied origin — URL parsing failed: {redacted}"),
                    },
                };
            }
        };
        let nonce = match generate_nonce() {
            Ok(value) => value,
            Err(reason) => return FfiDecision::Deny { reason },
        };
        // RS-220（2026-09-26 审计）：UNIX 秒经 broker::now_unix_secs 单源
        // （此前本文件 3 处内联 SystemTime::now——时钟不可用语义各自维护）。
        // RS-270：过期窗口经实例字段（生产默认 ACTION_EXPIRY_SECONDS）
        let expires_at = match crate::broker::now_unix_secs() {
            Some(secs) => secs.saturating_add(self.action_expiry_seconds),
            None => {
                return FfiDecision::Deny {
                    reason: FfiDenyReason {
                        code: "system_clock".into(),
                        detail: "系统时间不可用".into(),
                        explanation: "denied — system clock is before UNIX epoch".into(),
                    },
                };
            }
        };
        // RS-160（审计 2026-09-25）：参数在此处 move 进 action——三者在
        // 本函数后续不再使用，此前多余的 .clone() 每导航三次堆分配
        let action = AuthorizedAction {
            session_id,
            tab_id,
            document_generation: generation,
            origin: canonical_url.origin.clone(),
            method: "GET".into(),
            canonical_parameters: canonical_url.canonical_parameters,
            scope,
            expires_at,
            nonce,
            policy_version: self.policy_version.clone(),
            explanation: format!(
                "allowed origin {} — scheme {}, host {}",
                canonical_url.origin, canonical_url.scheme, canonical_url.host
            ),
        };
        // 会话验证（fail-closed）
        // RS-221（2026-09-26 审计）：validate_action 成功路径 Ok(())——
        // 此前 Decision::Allow(action.clone()) 每导航克隆整个授权结构
        //（12 个 String）；此处直接继续消费已持有的 action
        let guard = self.inner.lock().map_err(|_| ()).ok();
        let verdict = match guard {
            Some(g) => g.validate_action(&action),
            None => Err(DenyReason {
                code: "broker_lock".into(),
                detail: "Broker 锁获取失败".into(),
                explanation: "denied — broker lock poisoned".into(),
            }),
        };
        match verdict {
            Ok(()) => match self.issued_actions.lock() {
                Ok(mut issued_actions) => {
                    // M-15 修复（审计 2026-08-31）：账本容量 fail-closed
                    if !ledger_can_admit(&mut issued_actions, self.max_issued_actions) {
                        return ffi_deny(
                            "authorization_ledger_full",
                            "授权账本已达上限（惰性清理后仍满）",
                            "denied — authorization ledger exhausted its fail-closed capacity",
                        );
                    }
                    issued_actions.insert(
                        action.nonce.clone(),
                        IssuedAuthorization::Pending(Box::new(action.clone())),
                    );
                    FfiDecision::Allow {
                        action: FfiAuthorizedAction::from(action),
                    }
                }
                Err(_) => FfiDecision::Deny {
                    reason: FfiDenyReason {
                        code: "authorization_ledger".into(),
                        detail: "授权账本锁获取失败".into(),
                        explanation: "denied — issued authorization ledger lock poisoned".into(),
                    },
                },
            },
            Err(reason) => FfiDecision::Deny {
                reason: FfiDenyReason {
                    code: reason.code,
                    detail: reason.detail,
                    explanation: reason.explanation,
                },
            },
        }
    }

    /// 将当前导航登记为待审批请求。它复用完整的策略评估和会话验证，
    /// 但不会向宿主发放可消费授权；只有同一 Broker 的显式批准才能兑换原始动作。
    pub fn request_navigation_confirmation(
        &self,
        session_id: String,
        tab_id: String,
        generation: u64,
        raw_url: String,
        scope: String,
    ) -> FfiDecision {
        let authorized =
            match self.evaluate_navigation(session_id, tab_id, generation, raw_url, scope) {
                FfiDecision::Allow { action } => AuthorizedAction::from(action),
                other => return other,
            };
        let removed_from_issued = match self.issued_actions.lock() {
            Ok(mut issued_actions) => matches!(
                issued_actions.remove(&authorized.nonce),
                Some(IssuedAuthorization::Pending(issued)) if *issued == authorized
            ),
            Err(_) => {
                return ffi_deny(
                    "authorization_ledger",
                    "授权账本锁获取失败",
                    "denied — issued authorization ledger lock poisoned",
                );
            }
        };
        if !removed_from_issued {
            return ffi_deny(
                "authorization_ledger",
                "策略核心未能登记待审批授权",
                "denied — evaluated authorization was missing from the issued ledger",
            );
        }
        let request = FfiApprovalRequest {
            origin: authorized.origin.clone(),
            method: authorized.method.clone(),
            path: authorized.canonical_parameters.clone(),
            scope: authorized.scope.clone(),
            expires_at: authorized.expires_at,
            nonce: authorized.nonce.clone(),
        };
        match self.pending_navigation_approvals.lock() {
            Ok(mut pending_approvals) => {
                // 审计整改：有界账本——满则 fail-closed 拒绝（此前无上限，
                // 可被待审批请求堆叠造成内存 DoS）
                if pending_approvals.len() >= MAX_PENDING_APPROVALS {
                    // RS-035（审计 2026-09-24）：满时先清理已过期待审批——
                    // 此前过期请求永久驻留，1024 满后新请求被自拒绝服务
                    // RS-220：时刻经 broker::now_unix_secs 单源
                    // RS-287：过期口径 <= now（RS-156 一致——== now 即过期）
                    let now = crate::broker::now_unix_secs().unwrap_or(u64::MAX);
                    pending_approvals
                        .retain(|_, action| !pending_expired_at(action.expires_at, now));
                    if pending_approvals.len() >= MAX_PENDING_APPROVALS {
                        return ffi_deny(
                            "approval_ledger",
                            "待审批账本已达上限（1024）",
                            "denied — pending approval ledger at capacity",
                        );
                    }
                }
                pending_approvals.insert(authorized.nonce.clone(), authorized);
                FfiDecision::RequireConfirmation { request }
            }
            Err(_) => ffi_deny(
                "approval_ledger",
                "待审批账本锁获取失败",
                "denied — pending approval ledger lock poisoned",
            ),
        }
    }

    /// 显式批准当前待审批导航。该入口仅兑换策略核心保留的精确授权，
    /// 并再次绑定当前 URL/scope、会话、代际、策略版本与过期时间。
    pub fn approve_navigation_confirmation(
        &self,
        nonce: String,
        raw_url: String,
        scope: String,
    ) -> FfiDecision {
        if nonce.is_empty() {
            return ffi_deny(
                "approval_not_pending",
                "审批 nonce 为空",
                "denied — approval nonce was empty",
            );
        }
        // RS-282：raw_url 前置长度上限（与 evaluate/consume 同口径；先于
        // pending 移除检查——超长输入不得改变任何账本状态）
        if raw_url.len() > MAX_FFI_URL_BYTES {
            return ffi_deny(
                "ffi_url_too_long",
                &format!(
                    "URL 超长（{} 字节，上限 {MAX_FFI_URL_BYTES}）",
                    raw_url.len()
                ),
                "denied — raw URL exceeds the 64KB FFI boundary cap",
            );
        }
        let authorized = match self.pending_navigation_approvals.lock() {
            Ok(mut pending_approvals) => pending_approvals.remove(&nonce),
            Err(_) => {
                return ffi_deny(
                    "approval_ledger",
                    "待审批账本锁获取失败",
                    "denied — pending approval ledger lock poisoned",
                );
            }
        };
        let Some(authorized) = authorized else {
            return ffi_deny(
                "approval_not_pending",
                "审批请求不存在、已拒绝或已兑换",
                "denied — approval request was not pending",
            );
        };
        let Some(canonical_url) = crate::origin::canonicalize_external(&raw_url) else {
            return deny_url(raw_url);
        };
        if !matches_navigation_binding(&authorized, &scope, &canonical_url) {
            return ffi_deny(
                "approval_binding_mismatch",
                "审批请求与当前导航参数不匹配",
                "denied — approval URL or scope no longer matches the pending request",
            );
        }
        // RS-221：validate_action 成功路径 Ok(())——继续消费已持有的
        // authorized（此前 Allow 载荷是整结构克隆）
        let verdict = match self.inner.lock() {
            Ok(broker) => broker.validate_action(&authorized),
            Err(_) => Err(DenyReason {
                code: "broker_lock".into(),
                detail: "Broker 锁获取失败".into(),
                explanation: "denied — broker lock poisoned".into(),
            }),
        };
        if let Err(reason) = verdict {
            return FfiDecision::Deny {
                reason: FfiDenyReason {
                    code: reason.code,
                    detail: reason.detail,
                    explanation: reason.explanation,
                },
            };
        }
        match self.issued_actions.lock() {
            Ok(mut issued_actions) => {
                // M-15 修复（审计 2026-08-31）：账本容量 fail-closed——
                // 满时先惰性清理过期 Pending，仍满则拒绝签发（绝不无界增长）
                if !ledger_can_admit(&mut issued_actions, self.max_issued_actions) {
                    return ffi_deny(
                        "authorization_ledger_full",
                        "授权账本已达上限（惰性清理后仍满）",
                        "denied — authorization ledger exhausted its fail-closed capacity",
                    );
                }
                issued_actions.insert(
                    authorized.nonce.clone(),
                    IssuedAuthorization::Pending(Box::new(authorized.clone())),
                );
                FfiDecision::Allow {
                    action: FfiAuthorizedAction::from(authorized),
                }
            }
            Err(_) => ffi_deny(
                "authorization_ledger",
                "授权账本锁获取失败",
                "denied — issued authorization ledger lock poisoned",
            ),
        }
    }

    /// 显式拒绝待审批导航。未知、已过期、已兑换或已拒绝的 nonce 一律返回 false。
    pub fn reject_navigation_confirmation(&self, nonce: String) -> bool {
        if nonce.is_empty() {
            return false;
        }
        match self.pending_navigation_approvals.lock() {
            Ok(mut pending_approvals) => pending_approvals.remove(&nonce).is_some(),
            Err(_) => false,
        }
    }

    /// 创建新会话（ttl 秒）。
    ///
    /// P1-11 修复（全量复审 2026-09-01）：TTL 下限钳制——宿主传 0 会
    /// 得到"签发成功、即刻过期"的静默失效会话（fail-open 陷阱面）。
    /// 钳到 MIN_SESSION_TTL_SECONDS 保底；RS-158：上限同样钳制到
    /// MAX_SESSION_TTL_SECONDS（24h）——超长 TTL 会话近乎永生，扩大
    /// 授权/nonce 账本驻留暴露面。
    ///
    /// RS-159：空 session_id 拒绝（fail-closed，与 contracts Action schema
    /// 的 minLength 1 对齐）——空 id 会话即匿名共享会话，任何传空 id 的
    /// 调用方都会落到同一会话，破坏 persona 隔离语义。
    /// RS-223：session_id/tab_id 键长度上限 256 字节（与 core 层
    /// MAX_TAB_ID_LEN 对齐）——超长键拒绝，封堵会话池键驻留内存放大面。
    pub fn create_session(
        &self,
        session_id: String,
        tab_id: String,
        generation: u64,
        ttl_seconds: u64,
    ) -> bool {
        if session_id.is_empty() {
            return false;
        }
        if session_id.len() > MAX_SESSION_KEY_BYTES || tab_id.len() > MAX_SESSION_KEY_BYTES {
            return false;
        }
        let effective_ttl = ttl_seconds.clamp(MIN_SESSION_TTL_SECONDS, MAX_SESSION_TTL_SECONDS);
        match self.inner.lock() {
            // M-16 修复（审计 2026-08-31）：会话池满（fail-closed）时
            // 返回 false——原实现无条件 true，掩盖了容量拒绝
            Ok(mut g) => g
                .create_session(
                    session_id,
                    tab_id,
                    generation,
                    std::time::Duration::from_secs(effective_ttl),
                )
                .is_some(),
            Err(_) => false,
        }
    }

    /// 销毁会话。
    ///
    /// RS-286（2026-10-02 审计）：core 层 destroy_session 改返回 bool
    ///（remove().is_some()）——此前对不存在的 id 也恒 true，宿主无从区分
    /// 「已销毁」与「本来就不存在」。本入口透传 core 结果。
    pub fn destroy_session(&self, session_id: String) -> bool {
        let destroyed = match self.inner.lock() {
            Ok(mut g) => g.destroy_session(&session_id),
            Err(_) => false,
        };
        if let Ok(mut issued_actions) = self.issued_actions.lock() {
            issued_actions.retain(|_, authorization| authorization.session_id() != session_id);
        }
        if let Ok(mut pending_approvals) = self.pending_navigation_approvals.lock() {
            pending_approvals.retain(|_, action| action.session_id != session_id);
        }
        destroyed
    }

    /// 顶层文档切换后推进会话代际；错标签、跳跃与回退均拒绝。
    pub fn advance_document_generation(
        &self,
        session_id: String,
        tab_id: String,
        next_generation: u64,
    ) -> bool {
        let advanced = match self.inner.lock() {
            Ok(mut broker) => {
                broker.advance_document_generation(&session_id, &tab_id, next_generation)
            }
            Err(_) => false,
        };
        if advanced {
            if let Ok(mut issued_actions) = self.issued_actions.lock() {
                issued_actions.retain(|_, authorization| authorization.session_id() != session_id);
            }
            if let Ok(mut pending_approvals) = self.pending_navigation_approvals.lock() {
                pending_approvals.retain(|_, action| action.session_id != session_id);
            }
        }
        advanced
    }

    /// 在导航副作用执行点校验当前 URL/scope 并消费授权，拒绝参数替换或 nonce 重放。
    /// 绑定性比较：仅比较安全绑定属性，**不含 explanation**（人类可读审计
    /// 文本，不参与权限判定）。此前用 `*issued == action`（含 explanation），
    /// 而托管端序列化 NativeAction 不携带 explanation，导致合法一次消费被
    /// 误判 action_not_issued（"安装版崩溃"排查中暴露的确定性缺陷）。
    pub fn consume_navigation(
        &self,
        action: FfiAuthorizedAction,
        raw_url: String,
        scope: String,
    ) -> FfiDecision {
        // RS-282：raw_url 前置长度上限（三入口同口径；先于账本读取——
        // 超长输入不得触碰消费状态）
        if raw_url.len() > MAX_FFI_URL_BYTES {
            return ffi_deny(
                "ffi_url_too_long",
                &format!(
                    "URL 超长（{} 字节，上限 {MAX_FFI_URL_BYTES}）",
                    raw_url.len()
                ),
                "denied — raw URL exceeds the 64KB FFI boundary cap",
            );
        }
        let Some(canonical_url) = crate::origin::canonicalize_external(&raw_url) else {
            return deny_url(raw_url);
        };
        let action = AuthorizedAction::from(action);
        if !matches_navigation_binding(&action, &scope, &canonical_url) {
            return FfiDecision::Deny {
                reason: FfiDenyReason {
                    code: "action_binding_mismatch".into(),
                    detail: "授权动作与当前导航参数不匹配".into(),
                    explanation: "denied — action origin, path/query, method, or scope changed"
                        .into(),
                },
            };
        }
        let issued_action = match self.issued_actions.lock() {
            Ok(issued_actions) => issued_actions.get(&action.nonce).cloned(),
            Err(_) => {
                return FfiDecision::Deny {
                    reason: FfiDenyReason {
                        code: "authorization_ledger".into(),
                        detail: "授权账本锁获取失败".into(),
                        explanation: "denied — issued authorization ledger lock poisoned".into(),
                    },
                };
            }
        };
        match issued_action {
            Some(IssuedAuthorization::Pending(issued)) if same_binding(&issued, &action) => {}
            Some(IssuedAuthorization::Consumed { .. }) => {
                return FfiDecision::Deny {
                    reason: FfiDenyReason {
                        code: "nonce_replay".into(),
                        detail: "授权动作已被消费".into(),
                        explanation: "denied — issued authorization nonce already consumed".into(),
                    },
                };
            }
            _ => {
                return FfiDecision::Deny {
                    reason: FfiDenyReason {
                        code: "action_not_issued".into(),
                        detail: "授权动作不是当前策略核心签发或已被撤销".into(),
                        explanation: "denied — action was not issued by this broker or was revoked"
                            .into(),
                    },
                };
            }
        }
        // RS-221：validate_and_consume 成功路径 Ok(())——仅消费判别，
        // Allow 载荷由已持有的 action 构造（此前 Decision::Allow 整结构克隆）
        let verdict = match self.inner.lock() {
            Ok(mut broker) => broker.validate_and_consume(&action),
            Err(_) => Err(DenyReason {
                code: "broker_lock".into(),
                detail: "Broker 锁获取失败".into(),
                explanation: "denied — broker lock poisoned".into(),
            }),
        };
        match verdict {
            Ok(()) => {
                if let Ok(mut issued_actions) = self.issued_actions.lock() {
                    // M-15 修复（审计 2026-08-31）：Consumed 记录同样受账本
                    // 上限约束（惰性清理过期 Pending 后仍满 → 本次导航转为
                    // Deny——nonce 已被 validate_and_consume 消费，重放天然
                    // 失败，fail-closed 语义保持闭合）
                    if !ledger_can_admit(&mut issued_actions, self.max_issued_actions) {
                        return ffi_deny(
                            "authorization_ledger_full",
                            "授权账本已达上限（惰性清理后仍满）",
                            "denied — authorization ledger exhausted its fail-closed capacity",
                        );
                    }
                    issued_actions.insert(
                        action.nonce.clone(),
                        IssuedAuthorization::Consumed {
                            session_id: action.session_id.clone(),
                        },
                    );
                }
                FfiDecision::Allow {
                    action: FfiAuthorizedAction::from(action),
                }
            }
            Err(reason) => FfiDecision::Deny {
                reason: FfiDenyReason {
                    code: reason.code,
                    detail: reason.detail,
                    explanation: reason.explanation,
                },
            },
        }
    }
}

impl FfiBroker {
    /// RS-270：参数化构造器——生产入口恒为 `new`（uniffi constructor，
    /// ACTION_EXPIRY_SECONDS 默认）；测试注入极小窗口以真实触达
    /// 「过期 approve/consume 拒绝」分支。uniffi 导出块不支持自由关联函数，
    /// 本构造器只走 Rust 内部（不进跨语言绑定面）。
    /// 空 policy_version 的默认化（RS-253）在此单点实现。
    fn with_action_expiry(policy_version: String, action_expiry_seconds: u64) -> Self {
        let policy_version = if policy_version.is_empty() {
            DEFAULT_POLICY_VERSION.to_string()
        } else {
            policy_version
        };
        Self {
            inner: std::sync::Mutex::new(crate::broker::ContextBroker::new(
                policy_version.clone(),
                PolicyEngine::default(),
                CapabilityRegistry::new(),
            )),
            issued_actions: std::sync::Mutex::new(HashMap::new()),
            pending_navigation_approvals: std::sync::Mutex::new(HashMap::new()),
            policy_version,
            action_expiry_seconds,
            max_issued_actions: MAX_ISSUED_ACTIONS,
        }
    }

    /// RS-300：账本容量注入构造器——生产入口恒为 `new`（MAX_ISSUED_ACTIONS
    /// 默认）；测试注入小容量使满账本 fail-closed 分支经公共路径触达。
    /// 只走 Rust 内部（不进跨语言绑定面，同 with_action_expiry 口径）。
    #[cfg(test)]
    fn with_ledger_capacity(
        policy_version: String,
        action_expiry_seconds: u64,
        max_issued_actions: usize,
    ) -> Self {
        let mut broker = Self::with_action_expiry(policy_version, action_expiry_seconds);
        broker.max_issued_actions = max_issued_actions;
        broker
    }
}

/// 绑定性比较：仅比较安全绑定属性，**不含 explanation**（人类可读审计
/// 文本，不参与权限判定）。此前 consume 用 `*issued == action`（含
/// explanation），而托管端序列化 NativeAction 不携带 explanation，
/// 导致合法一次消费被误判 action_not_issued（确定性缺陷）。
fn same_binding(a: &AuthorizedAction, b: &AuthorizedAction) -> bool {
    a.session_id == b.session_id
        && a.tab_id == b.tab_id
        && a.document_generation == b.document_generation
        && a.origin == b.origin
        && a.method == b.method
        && a.canonical_parameters == b.canonical_parameters
        && a.scope == b.scope
        && a.expires_at == b.expires_at
        && a.nonce == b.nonce
        && a.policy_version == b.policy_version
}

/// RS-184（审计 2026-09-25）：导航绑定比较单源——approve 与 consume 的
/// 四属性清单此前重复内联两处（287/441 行形态一致），新增绑定属性时
/// 漏改一处即两端口径分裂（binding_mismatch 与放行互斥失败）。与
/// [`same_binding`] 同口径：explanation 不参与比较（M-15）。
fn matches_navigation_binding(
    action: &AuthorizedAction,
    scope: &str,
    canonical_url: &crate::origin::CanonicalExternalUrl,
) -> bool {
    action.method == "GET"
        && action.scope == scope
        && action.origin == canonical_url.origin
        && action.canonical_parameters == canonical_url.canonical_parameters
}

/// M-15 修复（审计 2026-08-31）：授权账本容量门（fail-closed）。
/// 未达上限直接放行；达上限先惰性清理已过期的 Pending 记录
/// （Consumed 记录保留到会话撤销，不参与清理），仍满则拒绝登记。
///
/// RS-136（审计 2026-09-25）：原子性契约——本函数与随后的
/// `issued_actions.insert(...)` **必须处在同一次
/// `issued_actions.lock()` 持有窗口内**（检查-插入不可跨锁拆分）。
/// 拆分即 TOCTOU：两个并发 evaluate 在各自持锁窗口内检查通过、
/// 交错插入，账本容量被突破（M-15 fail-closed 语义失效）。现有
/// 三处调用点（evaluate / approve / consume）均满足单锁窗口。
fn ledger_can_admit(issued: &mut HashMap<String, IssuedAuthorization>, cap: usize) -> bool {
    if issued.len() < cap {
        return true;
    }
    // RS-220：时刻经 broker::now_unix_secs 单源（时钟不可用 → u64::MAX
    // 即「全部 Pending 视为已过期」——fail-closed 方向与原内联一致）
    // RS-287：过期口径 <= now（RS-156 一致——== now 即过期）
    let now = crate::broker::now_unix_secs().unwrap_or(u64::MAX);
    issued.retain(|_, authorization| match authorization {
        IssuedAuthorization::Pending(action) => !pending_expired_at(action.expires_at, now),
        IssuedAuthorization::Consumed { .. } => true,
    });
    issued.len() < cap
}

fn deny_url(raw_url: String) -> FfiDecision {
    // RS-258：deny 文案不内嵌完整明文 URL——query/userinfo 剥除后组装
    let redacted = redact_url_for_log(&raw_url);
    FfiDecision::Deny {
        reason: FfiDenyReason {
            code: "url_policy".into(),
            detail: format!("拒绝 URL: {redacted}"),
            explanation: format!("denied origin — URL parsing failed: {redacted}"),
        },
    }
}

/// RS-258（2026-10-01 审计）：日志/文案面的 URL 脱敏——detail/explanation
/// 此前双份内嵌完整明文 URL（query 中的 token、userinfo 中的凭据随拒绝
/// 响应外泄，AD-211 已在 Windows 侧立认识）。此处剥 query/fragment/userinfo，
/// 仅保留 scheme://host[:port] 形态；无法定位 authority 的输入整体占位。
fn redact_url_for_log(raw_url: &str) -> String {
    let Some(scheme_end) = raw_url.find("://").map(|i| i + 3) else {
        return "<opaque-url>".to_string();
    };
    let authority_end = raw_url[scheme_end..]
        .find(['/', '?', '#'])
        .map(|i| scheme_end + i)
        .unwrap_or(raw_url.len());
    let authority = &raw_url[scheme_end..authority_end];
    // 剥 userinfo（最后一个 @ 之前是凭据）
    let host_part = match authority.rfind('@') {
        Some(at) => &authority[at + 1..],
        None => authority,
    };
    // RS-282（2026-10-02 审计）：host 段截断（256B）——deny 文案内嵌
    // host，host 由 URL 攻击者可控；字符边界内截断（host 多为 ASCII，
    // 边界回退防御多字节形态）
    let host_display = if host_part.len() > MAX_REDACT_HOST_BYTES {
        let mut cut = MAX_REDACT_HOST_BYTES;
        while cut > 0 && !host_part.is_char_boundary(cut) {
            cut -= 1;
        }
        &host_part[..cut]
    } else {
        host_part
    };
    format!("{}{}", &raw_url[..scheme_end], host_display)
}

fn ffi_deny(code: &str, detail: &str, explanation: &str) -> FfiDecision {
    FfiDecision::Deny {
        reason: FfiDenyReason {
            code: code.into(),
            detail: detail.into(),
            explanation: explanation.into(),
        },
    }
}

fn generate_nonce() -> Result<String, FfiDenyReason> {
    let mut bytes = [0u8; 32];
    // RS-153：getrandom 0.3 API——getrandom() 更名 fill()
    // RS-199（审计 2026-09-25）：熵不足路径参数化——填充与错误映射/
    // 编码拆分后，失败分支（此前完全不可注入、零测试）可单测：
    // entropy_error 的拒绝码与 nonce_from_entropy 的编码契约独立锁定
    getrandom::fill(&mut bytes).map_err(entropy_error)?;
    Ok(nonce_from_entropy(&bytes))
}

/// RS-199：熵获取失败的类型化拒绝构造（code/explanation 单源）。
fn entropy_error(error: getrandom::Error) -> FfiDenyReason {
    FfiDenyReason {
        code: "entropy_unavailable".into(),
        detail: "无法生成安全随机 nonce".into(),
        explanation: format!("denied — operating-system entropy unavailable: {error}"),
    }
}

/// RS-199：熵字节 → 64 字符小写 hex nonce（RS-137 查表单缓冲——零临时分配）。
fn nonce_from_entropy(bytes: &[u8; 32]) -> String {
    const HEX_TABLE: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(64);
    for byte in bytes {
        out.push(HEX_TABLE[(byte >> 4) as usize] as char);
        out.push(HEX_TABLE[(byte & 0x0f) as usize] as char);
    }
    out
}

// ============================ H-7 审计回归测试 ============================ //
// 锁定 FFI 导航通路的 fail-closed 语义（仅会话/代际/nonce 验证，policy/
// capability 层未接线）——职责边界的完整背景与决策记录以 broker.rs 模块文档
// H-7 注记为单一事实源，此处不再重复展开。

#[cfg(test)]
mod ffi_navigation_tests {
    use super::*;

    const POLICY_VERSION: &str = "test-policy-1";

    #[test]
    fn evaluate_navigation_denies_unknown_session() {
        let broker = FfiBroker::new(POLICY_VERSION.into());
        let decision = broker.evaluate_navigation(
            "no-such-session".into(),
            "tab-1".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        );
        assert!(
            matches!(decision, FfiDecision::Deny { .. }),
            "未知会话必须拒绝（fail-closed）"
        );
    }

    #[test]
    fn evaluate_navigation_allows_valid_session() {
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s1".into(), "tab-1".into(), 1, 60));
        let decision = broker.evaluate_navigation(
            "s1".into(),
            "tab-1".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        );
        assert!(
            matches!(
                decision,
                FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
            ),
            "有效会话 + 可解析 https URL 应放行或要求确认"
        );
    }

    #[test]
    fn evaluate_navigation_denies_unparseable_url() {
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s2".into(), "tab-1".into(), 1, 60));
        let decision = broker.evaluate_navigation(
            "s2".into(),
            "tab-1".into(),
            1,
            "file:///etc/passwd".into(),
            "navigation".into(),
        );
        assert!(
            matches!(decision, FfiDecision::Deny { .. }),
            "file:// 非 http(s) scheme 必须在 URL 解析层拒绝"
        );
    }

    /// P1-11 回归（全量复审 2026-09-01）：ttl=0 必须钳到下限——
    /// 原实现会签发"成功、即刻过期"的静默失效会话。
    #[test]
    fn create_session_clamps_zero_ttl_to_minimum() {
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s-min".into(), "tab-1".into(), 1, 0));
        let decision = broker.evaluate_navigation(
            "s-min".into(),
            "tab-1".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        );
        assert!(
            matches!(
                decision,
                FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
            ),
            "ttl=0 钳到 MIN_SESSION_TTL_SECONDS 后会话应在窗口内有效"
        );
    }

    // —— RS-158（审计 2026-09-25）：TTL 上限钳制 ——

    #[test]
    fn create_session_clamps_huge_ttl_to_maximum() {
        // u64::MAX 会话近乎永生——必须钳到 MAX_SESSION_TTL_SECONDS（24h）。
        // 实际生效 TTL 经 core session_ttl 可观测性 API 读取（测试不可
        // 反射宿主传参，只认签发结果）。
        // 注意：锁作用域最小化——持有 inner 锁期间不得再调
        // broker.create_session（内部二次 lock 同一 Mutex = 自死锁）
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s-max".into(), "tab-1".into(), 1, u64::MAX));
        {
            let inner = broker.inner.lock().expect("broker 锁必须可用");
            assert_eq!(
                inner.session_ttl("s-max"),
                Some(std::time::Duration::from_secs(MAX_SESSION_TTL_SECONDS)),
                "超长 TTL 必须钳到 24h 上限"
            );
        }
        // 边界内侧：86400 恰好等于上限——原样接受（锁已释放，安全再入）
        assert!(broker.create_session("s-cap".into(), "tab-1".into(), 1, 86_400));
        let inner = broker.inner.lock().expect("broker 锁必须可用");
        assert_eq!(
            inner.session_ttl("s-cap"),
            Some(std::time::Duration::from_secs(86_400)),
            "恰等于上限的 TTL 原样生效"
        );
    }

    // —— RS-159（审计 2026-09-25）：session_id 直测 ——

    #[test]
    fn create_session_rejects_empty_session_id() {
        // 空 session_id 拒绝（fail-closed，对齐 Action schema minLength 1）——
        // 空 id 会话即匿名共享会话，破坏 persona 隔离语义
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(!broker.create_session(String::new(), "tab-1".into(), 1, 60));
        // 创建失败即无会话——后续导航必须拒绝（fail-closed 闭环）
        let decision = broker.evaluate_navigation(
            String::new(),
            "tab-1".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        );
        assert!(
            matches!(decision, FfiDecision::Deny { .. }),
            "空 id 会话不存在——导航必须拒绝"
        );
    }

    // —— RS-223（审计 2026-09-26）：会话键长度上限 ——

    #[test]
    fn create_session_rejects_oversized_keys() {
        // 键长度上限 256 字节（与 core 层 MAX_TAB_ID_LEN 对齐）——此前仅查
        // 空串，1024 会话 × 64KB 双键 ≈128MB 键驻留面
        let broker = FfiBroker::new(POLICY_VERSION.into());
        let oversized = "x".repeat(MAX_SESSION_KEY_BYTES + 1);
        assert!(
            !broker.create_session(oversized.clone(), "t".into(), 1, 60),
            "超长 session_id 拒绝"
        );
        assert!(
            !broker.create_session("s".into(), oversized.clone(), 1, 60),
            "超长 tab_id 拒绝"
        );
        // 边界内（256 字节）放行
        let at_cap = "y".repeat(MAX_SESSION_KEY_BYTES);
        assert!(broker.create_session(at_cap.clone(), "t".into(), 1, 60));
        // 创建失败即无会话——超长 id 导航必须拒绝（fail-closed 闭环）
        assert!(matches!(
            broker.evaluate_navigation(
                oversized,
                "t".into(),
                1,
                "https://example.com/".into(),
                "navigation".into(),
            ),
            FfiDecision::Deny { .. }
        ));
    }

    #[test]
    fn create_session_session_id_uniqueness_and_isolation() {
        // session_id 隔离语义直测：同 id replace（RS-033 续期契约）+
        // 异 id 各自独立（不同 id 不串会话）
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("sa".into(), "tab-a".into(), 1, 60));
        assert!(broker.create_session("sb".into(), "tab-b".into(), 1, 60));
        // sa 的会话不能在 tab-b 上用（会话 ↔ 标签绑定）
        let cross = broker.evaluate_navigation(
            "sa".into(),
            "tab-b".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        );
        assert!(
            matches!(cross, FfiDecision::Deny { .. }),
            "跨标签复用会话必须拒绝"
        );
        // 同 id replace 语义（续期）——与 RS-033 契约一致
        assert!(broker.create_session("sa".into(), "tab-a".into(), 1, 120));
    }

    // —— RS-135（审计 2026-09-25）：容量/清理/覆盖语义 ——

    #[test]
    fn destroy_session_clears_issued_and_pending_ledgers() {
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s1".into(), "t1".into(), 0, 60));
        let FfiDecision::Allow { action } = broker.evaluate_navigation(
            "s1".into(),
            "t1".into(),
            0,
            "https://example.com/a".into(),
            "navigation".into(),
        ) else {
            panic!("expected allow");
        };
        let FfiDecision::RequireConfirmation { request } = broker.request_navigation_confirmation(
            "s1".into(),
            "t1".into(),
            0,
            "https://example.com/b".into(),
            "navigation".into(),
        ) else {
            panic!("expected pending");
        };
        assert!(broker.destroy_session("s1".into()));
        // 已签发授权随销毁清理（不退化为 nonce_replay——是撤销）
        match broker.consume_navigation(action, "https://example.com/a".into(), "navigation".into())
        {
            FfiDecision::Deny { reason } => {
                assert_ne!(reason.code, "nonce_replay", "销毁清理 ≠ 已消费重放");
            }
            _ => panic!("destroyed session must not consume"),
        }
        // 待审批请求随销毁清理
        match broker.approve_navigation_confirmation(
            request.nonce,
            "https://example.com/b".into(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "approval_not_pending"),
            _ => panic!("pending approval must be revoked on session destroy"),
        }
    }

    #[test]
    fn reject_and_empty_nonce_are_fail_closed() {
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s1".into(), "t1".into(), 0, 60));
        // 未知 nonce / 空 nonce / 已拒绝后的二次拒绝——一律 false
        assert!(!broker.reject_navigation_confirmation("no-such".into()));
        assert!(!broker.reject_navigation_confirmation(String::new()));
        let FfiDecision::RequireConfirmation { request } = broker.request_navigation_confirmation(
            "s1".into(),
            "t1".into(),
            0,
            "https://example.com/c".into(),
            "navigation".into(),
        ) else {
            panic!("expected pending");
        };
        assert!(broker.reject_navigation_confirmation(request.nonce.clone()));
        assert!(
            !broker.reject_navigation_confirmation(request.nonce),
            "二次拒绝 false"
        );
        // 空 nonce 的审批入口同样 fail-closed
        match broker.approve_navigation_confirmation(
            String::new(),
            "https://example.com/c".into(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "approval_not_pending"),
            _ => panic!("empty nonce must not approve"),
        }
    }

    #[test]
    fn pending_approval_capacity_is_fail_closed() {
        // MAX_PENDING_APPROVALS=1024：填满后第 1025 个请求 fail-closed
        // 拒绝（此前无上限可堆叠内存 DoS）；全部未过期，惰性清理不腾位
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s1".into(), "t1".into(), 0, 60));
        for i in 0..MAX_PENDING_APPROVALS {
            let url = format!("https://example.com/pending/{i}");
            let decision = broker.request_navigation_confirmation(
                "s1".into(),
                "t1".into(),
                0,
                url.clone(),
                "navigation".into(),
            );
            assert!(
                matches!(decision, FfiDecision::RequireConfirmation { .. }),
                "第 {i} 个待审批请求必须登记成功"
            );
        }
        let overflow = broker.request_navigation_confirmation(
            "s1".into(),
            "t1".into(),
            0,
            "https://example.com/overflow".into(),
            "navigation".into(),
        );
        match overflow {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "approval_ledger"),
            FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. } => {
                panic!("capacity overflow must deny")
            }
        }
    }

    #[test]
    fn create_session_same_id_replaces_prior_generation() {
        // RS-033 契约在 FFI 层的镜像：同 id create_session = 显式 replace——
        // 旧代际授权/验证立即失效，新代际生效
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s1".into(), "t1".into(), 1, 60));
        assert!(broker.create_session("s1".into(), "t1".into(), 2, 60));
        assert!(
            matches!(
                broker.evaluate_navigation(
                    "s1".into(),
                    "t1".into(),
                    1,
                    "https://example.com/".into(),
                    "navigation".into(),
                ),
                FfiDecision::Deny { .. }
            ),
            "replace 后旧代际必须失效"
        );
        assert!(matches!(
            broker.evaluate_navigation(
                "s1".into(),
                "t1".into(),
                2,
                "https://example.com/".into(),
                "navigation".into(),
            ),
            FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
        ));
    }

    // —— RS-136（审计 2026-09-25）：ledger_can_admit 白盒直测 ——

    fn craft_action(expires_in: i64) -> AuthorizedAction {
        // RS-220：测试辅助同样经 broker::now_unix_secs 单源取时
        let now = crate::broker::now_unix_secs().unwrap_or(0);
        AuthorizedAction {
            session_id: "s".into(),
            tab_id: "t".into(),
            document_generation: 0,
            origin: "https://example.com".into(),
            method: "GET".into(),
            canonical_parameters: "/".into(),
            scope: "navigation".into(),
            expires_at: (now as i64 + expires_in) as u64,
            nonce: format!("nonce-{expires_in}-{}", std::process::id()),
            policy_version: "test".into(),
            explanation: String::new(),
        }
    }

    #[test]
    fn ledger_can_admit_direct_capacity_semantics() {
        let mut ledger: HashMap<String, IssuedAuthorization> = HashMap::new();
        // 未满：直接放行
        ledger.insert(
            "n1".into(),
            IssuedAuthorization::Pending(Box::new(craft_action(3600))),
        );
        assert!(ledger_can_admit(&mut ledger, MAX_ISSUED_ACTIONS));
        // 满 + 全部未过期 Pending：拒绝（fail-closed，不淘汰）
        let mut full: HashMap<String, IssuedAuthorization> = HashMap::new();
        for i in 0..MAX_ISSUED_ACTIONS {
            full.insert(
                format!("k{i}"),
                IssuedAuthorization::Pending(Box::new(craft_action(3600))),
            );
        }
        assert!(!ledger_can_admit(&mut full, MAX_ISSUED_ACTIONS));
        // 满 + 存在过期 Pending：惰性清理后放行（清理不触及 Consumed）
        let key0 = "k0".to_string();
        full.insert(
            key0.clone(),
            IssuedAuthorization::Pending(Box::new(craft_action(-1))),
        );
        assert!(ledger_can_admit(&mut full, MAX_ISSUED_ACTIONS));
        assert!(!full.contains_key(&key0), "过期 Pending 被清理");
        assert_eq!(
            full.len(),
            MAX_ISSUED_ACTIONS - 1,
            "清理仅腾位不扩容（insert 由调用方随后完成）"
        );
        // 拒绝路径：已满且全部为 Consumed（清理不触及）→ 拒绝
        let mut consumed_full: HashMap<String, IssuedAuthorization> = HashMap::new();
        for i in 0..MAX_ISSUED_ACTIONS {
            consumed_full.insert(
                format!("c{i}"),
                IssuedAuthorization::Consumed {
                    session_id: "s".into(),
                },
            );
        }
        assert!(!ledger_can_admit(&mut consumed_full, MAX_ISSUED_ACTIONS));
    }

    // —— RS-287/300/301 回归（2026-10-02 审计） ——

    #[test]
    fn lazy_cleanup_treats_boundary_expiry_as_expired() {
        // RS-287：== now 即过期（RS-156 口径）——此前 `>= now` 保留 == 边界
        // 条目（已过期却驻留）。构造 expires_at == now 的 Pending 注入满
        // 账本，惰性清理必须移除（时间只前进，无翻转方向竞态）
        let mut full: HashMap<String, IssuedAuthorization> = HashMap::new();
        let now = crate::broker::now_unix_secs().unwrap_or(0);
        for i in 0..8 {
            full.insert(
                format!("k{i}"),
                IssuedAuthorization::Pending(Box::new(craft_action(3600))),
            );
        }
        full.insert(
            "boundary".into(),
            IssuedAuthorization::Pending(Box::new(AuthorizedAction {
                expires_at: now,
                ..craft_action(3600)
            })),
        );
        assert_eq!(full.len(), 9);
        // 容量 9：满 → 惰性清理 → boundary（== now）被移除 → 腾位放行
        assert!(ledger_can_admit(&mut full, 9));
        assert!(
            !full.contains_key("boundary"),
            "== now 的 Pending 必须按过期清理（RS-156 口径）"
        );
        // 判定单源直测：== now 过期、now+1 未过期
        assert!(pending_expired_at(now, now));
        assert!(pending_expired_at(now - 1, now));
        assert!(!pending_expired_at(now + 1, now));
    }

    #[test]
    fn authorization_ledger_full_via_public_path() {
        // RS-300：账本容量 fail-closed 公共路径覆盖——生产容量 50K 全量
        // evaluate 在单测内是负担（每次 getrandom + URL 解析），测试构造器
        // 注入小容量（4）走同一公共路径（evaluate → validate →
        // ledger_can_admit → insert），第 5 次 evaluate 必须
        // authorization_ledger_full 拒绝
        let broker =
            FfiBroker::with_ledger_capacity(POLICY_VERSION.into(), ACTION_EXPIRY_SECONDS, 4);
        assert!(broker.create_session("s".into(), "t".into(), 1, 60));
        for i in 0..4 {
            let url = format!("https://example.com/ledger/{i}");
            assert!(
                matches!(
                    broker.evaluate_navigation("s".into(), "t".into(), 1, url, "navigation".into()),
                    FfiDecision::Allow { .. }
                ),
                "第 {i} 次（容量内）必须放行"
            );
        }
        // 第 5 次：满账本 + 全部未过期 → fail-closed 拒绝
        match broker.evaluate_navigation(
            "s".into(),
            "t".into(),
            1,
            "https://example.com/overflow".into(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => {
                assert_eq!(reason.code, "authorization_ledger_full")
            }
            other => panic!("满账本必须 fail-closed，实际 {other:?}"),
        }
    }

    #[test]
    fn consume_on_full_ledger_denies_then_replays() {
        // RS-301：consume 成功 + 满账本的收口语义——validate_and_consume
        // 已在核心层消费 nonce，但 Consumed 记录因满账本无法登记 → 本次
        // 导航 deny（authorization_ledger_full）；二次 consume 同 nonce →
        // nonce_replay（核心层已消费，收口闭合）
        let broker =
            FfiBroker::with_ledger_capacity(POLICY_VERSION.into(), ACTION_EXPIRY_SECONDS, 4);
        assert!(broker.create_session("s".into(), "t".into(), 1, 60));
        let FfiDecision::Allow { action } = broker.evaluate_navigation(
            "s".into(),
            "t".into(),
            1,
            "https://example.com/once".into(),
            "navigation".into(),
        ) else {
            panic!("容量内必须放行")
        };
        // 填满账本（3 个其它 Pending + 目标 = 4）
        for i in 0..3 {
            let url = format!("https://example.com/filler/{i}");
            assert!(matches!(
                broker.evaluate_navigation("s".into(), "t".into(), 1, url, "navigation".into()),
                FfiDecision::Allow { .. }
            ));
        }
        // consume：核心层消费成功，Consumed 登记被满账本拒 → deny
        match broker.consume_navigation(
            action.clone(),
            "https://example.com/once".into(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => {
                assert_eq!(reason.code, "authorization_ledger_full")
            }
            other => panic!("满账本 consume 必须 deny，实际 {other:?}"),
        }
        // 二次 consume：核心层 nonce 已消费 → nonce_replay（收口闭合）
        match broker.consume_navigation(
            action,
            "https://example.com/once".into(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "nonce_replay"),
            other => panic!("二次 consume 必须重放拒绝，实际 {other:?}"),
        }
    }

    #[test]
    fn url_entries_reject_oversized_raw_url_before_parsing() {
        // RS-282：evaluate/approve/consume 的 raw_url 此前无前置上限（URL
        // 三入口有 MAX_FFI_URL_BYTES，这三处直通深解析）——超长先拒
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s".into(), "t".into(), 1, 60));
        let oversized = format!("https://example.com/{}", "a".repeat(70 * 1024));
        match broker.evaluate_navigation(
            "s".into(),
            "t".into(),
            1,
            oversized.clone(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "ffi_url_too_long"),
            other => panic!("evaluate 超长 raw_url 必须先拒，实际 {other:?}"),
        }
        // approve：超长先于 pending 移除（nonce 状态不被超长输入改变）
        let FfiDecision::RequireConfirmation { request } = broker.request_navigation_confirmation(
            "s".into(),
            "t".into(),
            1,
            "https://example.com/ok".into(),
            "navigation".into(),
        ) else {
            panic!("正常请求必须登记")
        };
        match broker.approve_navigation_confirmation(
            request.nonce.clone(),
            oversized.clone(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "ffi_url_too_long"),
            other => panic!("approve 超长 raw_url 必须先拒，实际 {other:?}"),
        }
        // pending 记录未被消费——正常 URL 仍可批准（先拒不改状态）
        assert!(matches!(
            broker.approve_navigation_confirmation(
                request.nonce,
                "https://example.com/ok".into(),
                "navigation".into()
            ),
            FfiDecision::Allow { .. }
        ));
        // consume：超长同样先拒
        let FfiDecision::Allow { action } = broker.evaluate_navigation(
            "s".into(),
            "t".into(),
            1,
            "https://example.com/once".into(),
            "navigation".into(),
        ) else {
            panic!("容量内必须放行")
        };
        match broker.consume_navigation(action, oversized, "navigation".into()) {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "ffi_url_too_long"),
            other => panic!("consume 超长 raw_url 必须先拒，实际 {other:?}"),
        }
    }

    #[test]
    fn redact_url_truncates_oversized_host_segment() {
        // RS-282：redact 的 host 段截断（256B）——deny 文案内嵌 host 由
        // URL 攻击者可控，脱敏输出必须有界
        let long_host = "a".repeat(300);
        let url = format!("https://{long_host}/p");
        let redacted = redact_url_for_log(&url);
        assert!(
            redacted.len() <= "https://".len() + MAX_REDACT_HOST_BYTES,
            "host 段截断到 256B：{}",
            redacted.len()
        );
        // 正常长度 host 不受影响（既有锚点回归）
        assert_eq!(
            redact_url_for_log("https://example.com/p?token=1#f"),
            "https://example.com"
        );
    }

    #[test]
    fn destroy_session_distinguishes_missing_id() {
        // RS-286：destroy 对不存在的 id 此前恒 true——core 层改返回 bool
        // 后宿主可区分「已销毁」与「本来就不存在」
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s".into(), "t".into(), 1, 60));
        assert!(broker.destroy_session("s".into()), "存在 id 销毁 true");
        assert!(
            !broker.destroy_session("s".into()),
            "二次销毁（已不存在）false"
        );
        assert!(!broker.destroy_session("never".into()), "不存在 id false");
    }

    // —— RS-308（2026-10-02 审计）：approvals-replay-and-expiry 向量消费 ——

    /// 向量 expires_at（ISO8601 Z 形态）→ UNIX epoch 秒。手工解析
    /// （civil 天数算法——Howard Hinnant days_from_civil），不引 chrono。
    fn iso8601_to_epoch(s: &str) -> Option<u64> {
        let b = s.as_bytes();
        if b.len() != 20 || b[4] != b'-' || b[7] != b'-' || b[10] != b'T' || b[19] != b'Z' {
            return None;
        }
        let num = |r: std::ops::Range<usize>| s.get(r)?.parse::<i64>().ok();
        let (y, m, d) = (num(0..4)?, num(5..7)?, num(8..10)?);
        let (hh, mm, ss) = (num(11..13)?, num(14..16)?, num(17..19)?);
        if !(1..=12).contains(&m) || !(1..=31).contains(&d) {
            return None;
        }
        let y = if m <= 2 { y - 1 } else { y };
        let era = if y >= 0 { y } else { y - 399 } / 400;
        let yoe = y - era * 400;
        let mp = (m + 9) % 12;
        let doy = (153 * mp + 2) / 5 + d - 1;
        let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
        let days = era * 146_097 + doe - 719_468;
        Some((days * 86_400 + hh * 3_600 + mm * 60 + ss) as u64)
    }

    #[test]
    fn approvals_replay_and_expiry_vectors_consumed() {
        // RS-308：approvals-replay-and-expiry.json 五条向量此前零 Rust 消费
        // ——逐条经 FFI 消费语义断言（nonce 重放 deny / 过期 deny / 换 scope
        // deny / 有效放行）。向量 expires_at 是 ISO8601（epoch 转换在
        // iso8601_to_epoch）；重放向量（n1/n3）的时间戳语义与过期正交，
        // 首次消费用新鲜窗口建立已消费状态后再重放（向量的 2026-08-16
        // 时间戳在重放分支之前就会触发 action_expired，触达不了重放本身）
        let root: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../contracts/vectors/approvals-replay-and-expiry.json"
        ))
        .expect("向量 JSON 必须合法");
        let vectors = root["vectors"]
            .as_array()
            .expect("approvals 向量缺 vectors 数组");
        assert!(vectors.len() >= 5, "向量覆盖面收缩（{}）", vectors.len());
        let url = "https://example.com/";
        let mut semantic = 0usize;
        for v in vectors {
            let expected = v["expected"].as_str().unwrap_or("valid");
            let note = v["note"].as_str().unwrap_or("unnamed");
            let nonce = v["nonce"].as_str().unwrap_or_default().to_string();
            let scope = v["scope"].as_str().unwrap_or("navigation").to_string();
            // 重放向量：首次消费需要未过期窗口（见函数注释）——非重放
            // 向量按向量原值
            let vector_expiry = iso8601_to_epoch(v["expires_at"].as_str().unwrap_or_default())
                .unwrap_or_else(|| panic!("向量 {note}: expires_at 不可解析"));
            let fresh = crate::broker::now_unix_secs().unwrap_or(0) + 3_600;
            let expires_at = if expected == "deny_replay" {
                fresh
            } else {
                vector_expiry
            };
            let broker = FfiBroker::new(POLICY_VERSION.into());
            assert!(broker.create_session("s1".into(), "t1".into(), 1, 120));
            let action = AuthorizedAction {
                session_id: "s1".into(),
                tab_id: "t1".into(),
                document_generation: 1,
                origin: "https://example.com".into(),
                method: "GET".into(),
                canonical_parameters: "/".into(),
                scope: scope.clone(),
                expires_at,
                nonce: nonce.clone(),
                policy_version: POLICY_VERSION.into(),
                explanation: String::new(),
            };
            // 模拟 evaluate 签发后的账本状态（公共 evaluate 无法注入向量
            // 的 expires_at，经账本登记后走公共 consume 入口）
            broker.issued_actions.lock().unwrap().insert(
                action.nonce.clone(),
                IssuedAuthorization::Pending(Box::new(action.clone())),
            );
            let consume = |broker: &FfiBroker, scope: &str| {
                broker.consume_navigation(
                    FfiAuthorizedAction::from(action.clone()),
                    url.into(),
                    scope.into(),
                )
            };
            match expected {
                "valid" => {
                    // 未重放 + 远期过期：单次消费放行
                    assert!(
                        matches!(consume(&broker, &scope), FfiDecision::Allow { .. }),
                        "向量 {note}: 有效授权必须放行"
                    );
                    semantic += 1;
                }
                "deny_replay" => {
                    // 先原 scope 单次消费成功（入账），再按向量形态重放
                    assert!(
                        matches!(consume(&broker, &scope), FfiDecision::Allow { .. }),
                        "向量 {note}: 重放前首次消费必须放行"
                    );
                    let replay_scope = v["replay_scope"].as_str().unwrap_or(&scope);
                    let expected_code = if replay_scope != scope {
                        // PY-089：换 scope 重放——scope 参与授权绑定
                        "action_binding_mismatch"
                    } else {
                        "nonce_replay"
                    };
                    match consume(&broker, replay_scope) {
                        FfiDecision::Deny { reason } => assert_eq!(
                            reason.code, expected_code,
                            "向量 {note}: 重放必须按 {expected_code} 拒绝"
                        ),
                        other => panic!("向量 {note}: 重放必须拒绝，实际 {other:?}"),
                    }
                    semantic += 1;
                }
                "deny_expired" => {
                    // PY-090：expires_at 到点即拒（<=now 口径）
                    match consume(&broker, &scope) {
                        FfiDecision::Deny { reason } => assert_eq!(
                            reason.code, "action_expired",
                            "向量 {note}: 过期必须 action_expired 拒绝"
                        ),
                        other => panic!("向量 {note}: 过期必须拒绝，实际 {other:?}"),
                    }
                    semantic += 1;
                }
                "deny_schema" => {
                    // 缺 nonce（空串）：schema 层 minLength 是 Python 职责；
                    // Rust 侧消费机制 = consume_nonce 对空 nonce 拒绝
                    //（RS-034 nonce_invalid——长度非法不认账本键）
                    match consume(&broker, &scope) {
                        FfiDecision::Deny { reason } => assert_eq!(
                            reason.code, "nonce_invalid",
                            "向量 {note}: 缺 nonce 的 Rust 侧消费语义（空 nonce 拒绝入账）"
                        ),
                        other => panic!("向量 {note}: 缺 nonce 必须拒绝，实际 {other:?}"),
                    }
                    semantic += 1;
                }
                other => panic!("向量 {note}: 未知 expected {other}"),
            }
        }
        assert!(semantic >= 5, "语义级向量覆盖面收缩（{semantic}）");
    }

    // —— RS-253/254/258/270 回归（审计 2026-10-01） ——

    #[test]
    fn empty_policy_version_defaults_on_uniffi_path() {
        // RS-253：C ABI 拒空 policy_version（aegis_policy_core_broker_new 返回
        // null）；UniFFI constructor 不可失败——空版本按「默认版本」收口：
        // 签发的 action 携带哨兵版本，与 broker 自身校验自洽
        let broker = FfiBroker::new(String::new());
        assert!(broker.create_session("s".into(), "t".into(), 1, 60));
        let decision = broker.evaluate_navigation(
            "s".into(),
            "t".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        );
        match decision {
            FfiDecision::Allow { action } => {
                assert_eq!(action.policy_version, DEFAULT_POLICY_VERSION);
            }
            other => panic!("空版本默认化后导航应正常评估，实际 {other:?}"),
        }
        // C ABI 侧仍拒绝空版本（行为差异以测试锚点双端登记）
        // —— 见 c_abi::tests::c_abi_rejects_empty_policy_version
    }

    #[test]
    fn evaluate_navigation_rejects_oversized_scope() {
        // RS-254：scope 长度上限 256（与 RS-223 会话键同口径）——
        // 此前 FFI 边界对 scope 无长度防线
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s".into(), "t".into(), 1, 60));
        let oversized = "x".repeat(MAX_SCOPE_BYTES + 1);
        match broker.evaluate_navigation(
            "s".into(),
            "t".into(),
            1,
            "https://example.com/".into(),
            oversized,
        ) {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "ffi_scope_too_long"),
            other => panic!("超长 scope 必须拒绝，实际 {other:?}"),
        }
        // 恰 256 字节放行（边界内侧）
        let at_cap = "y".repeat(MAX_SCOPE_BYTES);
        assert!(matches!(
            broker.evaluate_navigation(
                "s".into(),
                "t".into(),
                1,
                "https://example.com/".into(),
                at_cap,
            ),
            FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
        ));
    }

    #[test]
    fn deny_reasons_redact_url_query_and_userinfo() {
        // RS-258：url_policy deny 的 detail/explanation 不得内嵌完整明文
        // URL——query（token 载体）与 userinfo 剥除（AD-211 的 Rust 同步）
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s".into(), "t".into(), 1, 60));
        // 对照锚点：可解析 URL 正常评估（token 在 query 中但页面可解析，
        // 非 deny 路径——不进入文案面）
        let token_url = "https://example.com/path?session_token=SECRET&x=1#frag";
        assert!(matches!(
            broker.evaluate_navigation(
                "s".into(),
                "t".into(),
                1,
                token_url.into(),
                "navigation".into(),
            ),
            FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
        ));
        // 解析失败路径：userinfo 形态被 canonicalize 拒绝
        // （canonicalize_external 拒 userinfo），deny 文案应只含 host
        let userinfo_url = "https://user:secretpw@example.com/path?token=LEAK";
        let denied = match broker.evaluate_navigation(
            "s".into(),
            "t".into(),
            1,
            userinfo_url.into(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => reason,
            other => panic!("userinfo URL 应被拒，实际 {other:?}"),
        };
        let combined = format!("{}{}", denied.detail, denied.explanation);
        assert!(
            !combined.contains("secretpw") && !combined.contains("LEAK"),
            "凭据/query token 不得泄入 deny 文案：{combined}"
        );
        assert!(
            combined.contains("example.com"),
            "host 可保留（定位信息）：{combined}"
        );
        // 脱敏单源函数直测：query/fragment/userinfo 全剥、scheme+host 保留
        assert_eq!(
            redact_url_for_log("https://example.com/p?token=1#f"),
            "https://example.com"
        );
        assert_eq!(
            redact_url_for_log("https://u:p@example.com:8443/p"),
            "https://example.com:8443"
        );
        assert_eq!(redact_url_for_log("not a url"), "<opaque-url>");
    }

    #[test]
    fn zero_expiry_window_issues_immediately_expired_actions() {
        // RS-270：ACTION_EXPIRY_SECONDS 可测参数化——注入 0 秒窗口后签发的
        // 授权 expires_at == 签发时刻，evaluate 自身的会话验证即判过期
        // （RS-156 口径 == now 即过期），参数真实生效
        let broker =
            FfiBroker::with_action_expiry(POLICY_VERSION.into(), TEST_ACTION_EXPIRY_SECONDS);
        assert!(broker.create_session("s".into(), "t".into(), 1, 120));
        match broker.evaluate_navigation(
            "s".into(),
            "t".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "action_expired"),
            other => panic!("零窗口签发必须即刻过期，实际 {other:?}"),
        }
    }

    #[test]
    fn expired_pending_approval_and_issued_action_rejected() {
        // RS-270：过期 approve/consume 分支直测——向两本账本注入已过期授权
        // （expires_at < now，确定性构造，无时钟竞态），绑定全部匹配的
        // 前提下必须以 action_expired 拒绝（此前恒 120s 窗口零覆盖）
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s".into(), "t".into(), 1, 120));
        let now = crate::broker::now_unix_secs().unwrap_or(0);
        let expired = AuthorizedAction {
            session_id: "s".into(),
            tab_id: "t".into(),
            document_generation: 1,
            origin: "https://example.com".into(),
            method: "GET".into(),
            canonical_parameters: "/late".into(),
            scope: "navigation".into(),
            expires_at: now.saturating_sub(1),
            nonce: "expired-nonce".into(),
            policy_version: POLICY_VERSION.into(),
            explanation: String::new(),
        };
        // approve 侧：pending 账本中的过期授权 → action_expired
        broker
            .pending_navigation_approvals
            .lock()
            .unwrap()
            .insert("expired-nonce".into(), expired.clone());
        match broker.approve_navigation_confirmation(
            "expired-nonce".into(),
            "https://example.com/late".into(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "action_expired"),
            other => panic!("过期授权 approve 必须拒绝，实际 {other:?}"),
        }
        // consume 侧：issued 账本中的过期 Pending 授权 → action_expired
        broker.issued_actions.lock().unwrap().insert(
            "expired-nonce".into(),
            IssuedAuthorization::Pending(Box::new(expired)),
        );
        match broker.consume_navigation(
            FfiAuthorizedAction {
                session_id: "s".into(),
                tab_id: "t".into(),
                document_generation: 1,
                origin: "https://example.com".into(),
                method: "GET".into(),
                canonical_parameters: "/late".into(),
                scope: "navigation".into(),
                expires_at: now.saturating_sub(1),
                nonce: "expired-nonce".into(),
                policy_version: POLICY_VERSION.into(),
                explanation: String::new(),
            },
            "https://example.com/late".into(),
            "navigation".into(),
        ) {
            FfiDecision::Deny { reason } => assert_eq!(reason.code, "action_expired"),
            other => panic!("过期授权 consume 必须拒绝，实际 {other:?}"),
        }
    }
}

// —— RS-137（审计 2026-09-25）：nonce 查表实现回归 ——

#[cfg(test)]
mod nonce_tests {
    use super::*;

    #[test]
    fn generate_nonce_is_64_lowercase_hex_chars() {
        for _ in 0..8 {
            let nonce = generate_nonce().expect("OS entropy available in tests");
            assert_eq!(nonce.len(), 64, "32 字节 hex 编码必须 64 字符");
            assert!(
                nonce
                    .bytes()
                    .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()),
                "nonce 必须全小写 hex（与 MAX_NONCE_LENGTH 校验、账本键序一致）"
            );
        }
        // 两次生成不重复（随机性抽查）
        let a = generate_nonce().unwrap();
        let b = generate_nonce().unwrap();
        assert_ne!(a, b);
    }

    // —— RS-185/199（审计 2026-09-25）——

    #[test]
    fn entropy_error_maps_to_typed_deny() {
        // RS-199：熵不足路径参数化后可测——映射构造的拒绝码/文案单源锁定
        //（真实 getrandom 失败在测试进程不可注入，映射函数即为注入面）
        let reason = entropy_error(getrandom::Error::UNSUPPORTED);
        assert_eq!(reason.code, "entropy_unavailable");
        assert!(reason.explanation.contains("entropy unavailable"));
        // 编码契约：确定性输入 → 确定性输出（64 字符小写 hex）
        let nonce = nonce_from_entropy(&[0u8; 32]);
        assert_eq!(nonce, "0".repeat(64));
        let nonce = nonce_from_entropy(&[0xff; 32]);
        assert_eq!(nonce, "f".repeat(64));
        assert_eq!(nonce_from_entropy(&[0xab; 32]).len(), 64);
    }

    #[test]
    fn approve_navigation_rejects_unparseable_url() {
        // RS-185：approve 的 URL 解析失败分支此前零测试——pending 审批
        // 对畸形 URL 必须拒绝（url_policy），且不消费 pending 记录？
        // 口径核实：canonicalize 在 remove(&nonce) 之后执行——失败时
        // nonce 已被移除（一次性语义：畸形重试后 approval_not_pending）
        let broker = FfiBroker::new("1.0".into());
        assert!(broker.create_session("s".into(), "t".into(), 1, 120));
        let decision = broker.request_navigation_confirmation(
            "s".into(),
            "t".into(),
            1,
            "https://example.com/confirm".into(),
            "navigation".into(),
        );
        let FfiDecision::RequireConfirmation { request } = decision else {
            panic!("active session should produce confirmation request");
        };
        // 畸形 URL approve → deny（url_policy）
        let denied = broker.approve_navigation_confirmation(
            request.nonce.clone(),
            "https://[::1]/bad".into(),
            "navigation".into(),
        );
        match denied {
            FfiDecision::Deny { reason } => {
                assert_eq!(reason.code, "url_policy", "畸形 URL 必须走 url_policy 拒绝");
            }
            other => panic!("期望 Deny，实际 {other:?}"),
        }
        // pending 已被移除（一次性语义）：同 nonce 重试 → approval_not_pending
        let retry = broker.approve_navigation_confirmation(
            request.nonce,
            "https://example.com/confirm".into(),
            "navigation".into(),
        );
        match retry {
            FfiDecision::Deny { reason } => {
                assert_eq!(reason.code, "approval_not_pending");
            }
            other => panic!("期望 approval_not_pending，实际 {other:?}"),
        }
    }
}
