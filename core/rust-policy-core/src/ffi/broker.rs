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
    /// 审计第六轮（2026-10-03/04）：威胁 host 黑名单快照（deny-by-content）。
    /// 此前 FFI 通路完全没有策略层——H-7 注记明载「policy.evaluate /
    /// capability.validate 未接入 FFI 通路」，故 evaluate_navigation 的拒绝
    /// 条件只有"URL 是否良构"，任意良构 https URL 一律 Allow（恶意 host 不例外）。
    /// 空集 = 不拦（默认不 deny-all，避免未接线端整体不可用）；由宿主经
    /// update_host_denylist 注入订阅源快照。
    deny_hosts: std::sync::Mutex<std::collections::HashSet<String>>,
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

/// 黑名单条目 host 形态校验——与 `canonicalize_external` 的 host 口径一致。
/// 尾点/前导点/空段/越界字符的条目永远不会被命中，收下即制造"已登记但永不生效"
/// 的死条目（比不登记更坏：订阅源看起来是工作的）。
/// 审计第六轮（2026-10-03/04）：置于模块级而非 impl 内——`#[uniffi::export]`
/// 的 impl 块不接受无 self 关联函数（编译期报 associated functions not supported）。
fn denylist_host_shape_ok(host: &str) -> bool {
    !host.is_empty()
        && !host.starts_with('.')
        && !host.ends_with('.')
        && !host.contains("..")
        && host
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'-')
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
        // 内容判定的 host 口径：**剥去端口**的纯主机名。
        // CanonicalExternalUrl.host 依 RS-227 口径保留非默认端口（:8080 形态
        // 实证在 host 内），直接拿它比对会同时制造两个绕过：
        //   ① 黑名单条目 `bad.example` 匹配不上 `bad.example:8443`；
        //   ② 高危判定把 `127.0.0.1:8080` 当成非本机（split('.') 末段
        //      "8080" 之外的 "1:8080" 解析失败）而放行。
        // IPv6 字面量（方括号形态）已在归一层被拒（PY-069/070），此处
        // split(':') 取首段无歧义。host 永不为空（归一层已拒空）。
        let policy_host = canonical_url
            .host
            .split(':')
            .next()
            .unwrap_or(canonical_url.host.as_str());
        // 审计第六轮（2026-10-03/04）：deny-by-content 首次在 FFI 通路生效——
        // 命中威胁黑名单即拒（此前黑名单只活在两端宿主代码里，Android 端整体缺失）。
        // 用 policy host 比对，不用 raw_url：raw 可含 userinfo/query 混淆形态。
        if self.is_host_denied(policy_host) {
            return FfiDecision::Deny {
                reason: FfiDenyReason {
                    code: "threat_blocklist".into(),
                    detail: format!("目标 host 在威胁黑名单: {policy_host}"),
                    explanation: "denied — host is on the threat blocklist".into(),
                },
            };
        }
        // 高危目标判定（本机/私网）——纯函数，见 security_policy 文档
        let high_risk =
            crate::security_policy::SecurityPolicy::is_local_or_private_host(policy_host);
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
            // 审计第六轮（2026-10-03/04）：高危目标（本机/私网）不直发放行授权，
            // 改登记为待审批。确认流自此**只对高危目标触发**，普通公网导航直接
            // Allow——此前 request_navigation_confirmation 把每一个 Allow 无条件转成
            // RequireConfirmation，等价于"每次导航都弹确认"，因而该开关在
            // 2026-08-30 被实测定案关闭、整套确认域（pendingConfirmation/防孤儿
            // nonce/受信兑换）沦为死代码。收窄到高危及开关可重新启用。
            // 副带收益：子框架轻量路径只调 evaluate_navigation，收到
            // RequireConfirmation 即按既有语义 fail-closed 阻断——远程页嵌
            // iframe 打 127.0.0.1/私网的 SSRF 面自此在核心层被拦，不依赖端侧实现。
            Ok(()) if high_risk => self.register_pending_approval(action),
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
}

// 审计第六轮（2026-10-03/04）：内部判定/登记辅助——置于非导出 impl 块，
// #[uniffi::export] 的 impl 会把其中所有方法计入 FFI 面
//（内部类型 AuthorizedAction 未导出，被引用即编译失败）。
impl FfiBroker {
    /// 威胁黑名单判定（审计第六轮 2026-10-03/04）。锁中毒按**被拒**处理——
    /// 黑名单是拦截面，判定失败绝不 fail-open。
    fn is_host_denied(&self, host: &str) -> bool {
        match self.deny_hosts.lock() {
            Ok(denied) => denied.contains(host),
            Err(_) => true,
        }
    }
}

#[uniffi::export]
impl FfiBroker {
    /// 注入/替换威胁 host 黑名单快照（审计第六轮 2026-10-03/04）。
    ///
    /// 返回**被接受**的条目数：调用方可用 `输入数 - 返回值` 发现有一批条目
    /// 被形态校验拒收，而不是静默变成死条目。空输入 = 清空（**不** deny-all）——
    /// 未接入订阅源的端行为与既往完全一致，这是本改动能安全落地的前提。
    pub fn update_host_denylist(&self, hosts: Vec<String>) -> u32 {
        let accepted: std::collections::HashSet<String> = hosts
            .into_iter()
            .map(|host| host.trim().to_ascii_lowercase())
            .filter(|host| denylist_host_shape_ok(host))
            .collect();
        let count = accepted.len() as u32;
        match self.deny_hosts.lock() {
            Ok(mut denied) => *denied = accepted,
            // 锁中毒：不覆盖（保留旧快照比清空安全），并如实报 0 接受
            Err(_) => return 0,
        }
        count
    }
}

impl FfiBroker {
    /// 把已通过会话/代际校验的授权登记为待审批请求（用户确认面）。
    ///
    /// 审计第六轮（2026-10-03/04）：自 request_navigation_confirmation 抽出，
    /// 现由 evaluate_navigation 的高危分支直接调用——授权不再"先进 issued 账本
    /// 再搬出来"，消除已发放未消费的中间态；owner 转移单段完成。
    fn register_pending_approval(&self, authorized: AuthorizedAction) -> FfiDecision {
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
}

#[uniffi::export]
impl FfiBroker {
    /// 将当前导航登记为待审批请求（仅当其确属高危目标）。
    ///
    /// 审计第六轮（2026-10-03/04）：**语义收窄**。本函数不再把每一个可放行导航
    /// 一律转成 RequireConfirmation——高危判定（本机/私网）与黑名单拦截都已在
    /// evaluate_navigation 内完成，这里只作委托：Allow 原样返回（宿主可直接消费），
    /// RequireConfirmation / Deny 原样返回。
    /// 旧口径「每次导航都要确认」是使用方于 2026-08-30 关闭确认开关、进而使整套
    /// 确认域（pendingConfirmation / 防孤儿 nonce / 受信兑换入口）退化为死代码的
    /// 直接根因；收窄后确认只对少数目标触发，开关可重新启用而不牺牲可用性。
    pub fn request_navigation_confirmation(
        &self,
        session_id: String,
        tab_id: String,
        generation: u64,
        raw_url: String,
        scope: String,
    ) -> FfiDecision {
        self.evaluate_navigation(session_id, tab_id, generation, raw_url, scope)
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
        // 审计第六轮延续（2026-10-04）：消费点**复判黑名单**（TOCTOU 收口）。
        // evaluate 与 consume 之间隔着一次用户批准/一次网络往返，订阅源快照
        // 可能在这段窗口里新增该 host；只在 evaluate 判一次，等于"已签发授权
        // 一旦到手就永久有效"，60s 有效期内黑名单更新对已授权导航不生效。
        // 注意：这里**只复判黑名单，不复判高危**——高危目标在签发阶段就走
        // 待审批分支、从不进入 issued 账本；若在此处再拦高危，用户刚批准的
        // 本机/私网导航会被自己否决，把确认流变成死路径。
        let policy_host = canonical_url
            .host
            .split(':')
            .next()
            .unwrap_or(canonical_url.host.as_str());
        if self.is_host_denied(policy_host) {
            return FfiDecision::Deny {
                reason: FfiDenyReason {
                    code: "threat_blocklist".into(),
                    detail: format!("消费点复判：host 已进入威胁黑名单 {policy_host}"),
                    explanation: "denied — host entered the threat blocklist after issuance".into(),
                },
            };
        }
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
            deny_hosts: std::sync::Mutex::new(std::collections::HashSet::new()),
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
mod ffi_navigation_tests;

// —— RS-137（审计 2026-09-25）：nonce 查表实现回归 ——

#[cfg(test)]
mod nonce_tests;

#[cfg(test)]
mod consume_recheck_tests;
