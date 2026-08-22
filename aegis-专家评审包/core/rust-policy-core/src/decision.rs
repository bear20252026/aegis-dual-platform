//! Decision 类型化模型（蓝图——与 contracts/Windows Broker/Android Broker 一致）。
//!
//! Decision = Allow(AuthorizedAction) | RequireConfirmation(ApprovalRequest) | Deny(DenyReason)
//! ——不再用 bool/空字符串作为安全模型——默认拒绝（fail-closed）。

/// 类型化安全决策（纯数据——无 I/O）。
#[derive(Debug, Clone, PartialEq)]
pub enum Decision {
    Allow(AuthorizedAction),
    RequireConfirmation(ApprovalRequest),
    Deny(DenyReason),
}

/// AuthorizedAction——唯一允许进入副作用服务的凭据（ADR-002）。
/// 绑定字段任一变化使批准失效。
/// explanation：人类可读的审计说明（照搬 warden Verdict.explanation 模式）。
#[derive(Debug, Clone, PartialEq)]
pub struct AuthorizedAction {
    pub session_id: String,
    pub tab_id: String,
    pub document_generation: u64,
    pub origin: String,
    pub method: String,
    pub canonical_parameters: String,
    pub scope: String,
    pub expires_at: u64,
    pub nonce: String,
    pub policy_version: String,
    pub explanation: String,
}

/// 审批请求（高风险副作用——原生确认——nonce 一次性/过期——重放拒绝）。
#[derive(Debug, Clone, PartialEq)]
pub struct ApprovalRequest {
    pub origin: String,
    pub method: String,
    pub path: String,
    pub scope: String,
    pub expires_at: u64,
    pub nonce: String,
}

/// 拒绝原因（类型化——fail-closed——审计可追溯）。
#[derive(Debug, Clone, PartialEq)]
pub struct DenyReason {
    pub code: String,
    pub detail: String,
    /// 人类可读的审计说明（照搬 warden Verdict.explanation 模式）。
    pub explanation: String,
}
