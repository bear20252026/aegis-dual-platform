namespace Aegis.Windows.Broker;

using System;

/// <summary>AuthorizedAction——唯一允许进入副作用服务的凭据（ADR-002）。
/// 绑定 session/tab/document_generation/origin/method/canonical_parameters/
/// scope/expires_at/nonce/policy_version——任一字段变化使批准失效。</summary>
public sealed record AuthorizedAction(
    string SessionId,
    string TabId,
    ulong DocumentGeneration,
    string Origin,
    string Method,
    string CanonicalParameters,
    string Scope,
    DateTime ExpiresAt,
    string Nonce,
    string PolicyVersion);
