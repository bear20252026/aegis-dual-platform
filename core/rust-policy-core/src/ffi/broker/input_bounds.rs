//! FFI 导航入口的前置规模上限（第九轮 R9-B63，自 `ffi/broker.rs` 抽出）。
//!
//! 家族：R8-RS-13 / R9-B61 立的是「先判长度再分配」这条通则，落点当时只有种子解码
//! 与黑名单两处。本批把同一个问题问完整个 `#[uniffi::export]` 面，量出两处缺口：
//!
//! 1. **`policy_version`**：构造期两面都没有「存」的口径——uniffi 构造器一字不判，
//!    C ABI 只有 `read_utf8` 那条为防「无 NUL 终止就无界越读」而设的 64 KiB 扫描界
//!    （那是**读**的口径，不是**存**的口径）。而这个串会被 `clone()` 进每一条签发的
//!    授权（见 `evaluate_navigation` 的 `policy_version: self.policy_version.clone()`），
//!    账本上限 50K ⇒ 一份宿主输入换成 50K 份驻留；它同样出现在「会话不存在」的
//!    deny 文案里（`broker.rs` 的 `validate_action_at`）。
//! 2. **`session_id` / `tab_id`**：`create_session` 判 256（RS-223），
//!    `evaluate_navigation` 不判。账本里的会话键之所以有界，靠的是「池键 ≤256 ⇒
//!    长键必然查不到」这条**间接**理由；而「查不到」恰恰是核心层把这个未判长的原串
//!    写进 detail 与 explanation 各一遍的那条路径。对照：核心层对 nonce 就写得规矩
//!    （`consume_nonce` 既判长、文案里只放长度数字），所以本批不动 nonce。
//!
//! 判定收在这里而不是留在入口各写一遍：`raw_url` 那条上限此前在 evaluate/approve/
//! consume 内联了三份逐字相同的代码，而 R9-B61 的第二条判据拦的就是「同一件事写两遍」。
//!
//! 口径不变：拒绝码与拒绝文案逐字沿用本批之前的形态，判定顺序为会话键 → scope →
//! URL；空 URL 仍归 `canonicalize_external` 判（这里不新增空串拒绝，改它等于换码）。

use super::{ffi_deny, FfiBroker, FfiDecision, MAX_SCOPE_BYTES, MAX_SESSION_KEY_BYTES};
use crate::ffi::MAX_FFI_URL_BYTES;

/// 构造期 `policy_version` 的字节上限——与本家族的短标识符口径同值（会话键、scope、
/// 管线 domain、脱敏 host、黑名单单条都是 256）。真实取值是
/// `contracts/policy/action-catalog.yaml` 里的 `policy_version: "1.0"`，256 已是 128
/// 倍余量；再长的东西就不是版本标签而是载荷了。
pub(crate) const MAX_POLICY_VERSION_BYTES: usize = 256;

impl FfiBroker {
    /// 构造期策略版本判定单源，**两面共用**：C ABI 据此返回 null（与既往「拒空」
    /// 走同一条拒绝路径），uniffi 构造器签名不可失败，据此退回
    /// `DEFAULT_POLICY_VERSION` 哨兵（RS-253 的既有做法）。退回是可观察的：
    /// Allow 载荷里回显的就是实际生效的那个版本串——宿主传进来的超长值既不会被
    /// 静默截断，也不会驻留在账本里。
    pub(crate) fn policy_version_ok(value: &str) -> bool {
        !value.is_empty() && value.len() <= MAX_POLICY_VERSION_BYTES
    }
}

/// 导航评估入口的三段前置上限（`evaluate_navigation` 与其委托方
/// `request_navigation_confirmation` 共用）。返回 `Some(deny)` 时调用方必须**立刻**
/// 返回：此时既没有做深解析，也没有拼任何含宿主原文的文案。
pub(crate) fn navigation_entry_refusal(
    session_id: &str,
    tab_id: &str,
    scope: &str,
    raw_url: &str,
) -> Option<FfiDecision> {
    // R9-B63：会话键排在第一段——它是唯一「查不到就把原串写进 deny 文案」的输入
    if session_id.len() > MAX_SESSION_KEY_BYTES || tab_id.len() > MAX_SESSION_KEY_BYTES {
        return Some(ffi_deny(
            "ffi_session_key_too_long",
            &format!(
                "会话键超长（session {} 字节 / tab {} 字节，上限 {MAX_SESSION_KEY_BYTES}）",
                session_id.len(),
                tab_id.len()
            ),
            "denied — session or tab key exceeds the 256-byte FFI boundary cap",
        ));
    }
    // RS-254：scope 长度上限（256——与 RS-223 会话键同口径）。超出后它会随
    // AuthorizedAction 进账本驻留，所以判在构造 action 之前
    if scope.len() > MAX_SCOPE_BYTES {
        return Some(ffi_deny(
            "ffi_scope_too_long",
            &format!("scope 超长（{} 字节，上限 {MAX_SCOPE_BYTES}）", scope.len()),
            "denied — scope exceeds the 256-byte FFI boundary cap",
        ));
    }
    url_entry_refusal(raw_url)
}

/// 只判 URL 的那两个入口（approve / consume）共用这一条。它们的 scope 是**比较**
/// 用的（既不进账本也不写进文案），所以不需要上限；`raw_url` 需要，是因为两条都
/// 走在深解析之前，且拒绝文案要脱敏（RS-282 的原理由头不动）。
pub(crate) fn url_entry_refusal(raw_url: &str) -> Option<FfiDecision> {
    if raw_url.len() > MAX_FFI_URL_BYTES {
        return Some(ffi_deny(
            "ffi_url_too_long",
            &format!(
                "URL 超长（{} 字节，上限 {MAX_FFI_URL_BYTES}）",
                raw_url.len()
            ),
            "denied — raw URL exceeds the 64KB FFI boundary cap",
        ));
    }
    None
}
