namespace Aegis.Windows.Broker;

using System;
using System.Collections.Generic;
using Aegis.Windows.Core.Security;

/// <summary>Capability Broker——唯一允许产生本地副作用的边界（ADR-002/蓝图阶段 C）。
/// 验证来源/会话/标签代际/scope/参数/预算/批准/nonce——没有 AuthorizedAction
/// 不能导航/下载/导出/改策略。默认拒绝（fail-closed）。</summary>
public sealed class BrowserPolicyBroker : IBroker
{
    public string PolicyVersion { get; } = "1.0";
    // 与 Rust 侧 broker.rs 的 MAX_CONSUMED_NONCES 保持对等：达到上限即 fail-closed 拒绝，
    // 绝不淘汰旧 nonce（以免削弱一次性/重放保护）。
    private const int MaxConsumedNonces = 50_000;
    private const int MaxAuditEntries = 5000;  // 审计有界（此前无上限——高频 deny 即无界内存）
    // CS-209/210/211：此前内联的魔法数单源
    private const int MaxSessions = 1024;             // 与 Rust MAX_SESSIONS 对等
    private const int NativeSessionTtlSeconds = 120;  // 原生会话 TTL（秒）
    private static readonly TimeSpan ActionLifetime = TimeSpan.FromMinutes(2);  // 授权时效
    private readonly object _auditLock = new();
    private readonly Queue<Audit.AuditEvent> _auditLog = new();
    private readonly HashSet<string> _consumedNonces = new(StringComparer.Ordinal);
    private readonly Dictionary<string, SessionContext> _sessions = new(StringComparer.Ordinal);
    private readonly object _nonceLock = new();
    private readonly object _sessionLock = new();
    private readonly Func<NativePolicyCoreGateResult> _nativePolicyCoreGate;
    private readonly NativePolicyCoreBridge? _nativePolicyCoreBridge;
    // 审计第七轮（2026-10-03）：桥来自进程级共享持有者——Dispose 时归还引用而非
    // 释放（原生侧单活 broker，误释放即全进程永久失去原生核心，见 Hub 注释）
    private readonly bool _nativePolicyCoreBridgeShared;
    private readonly bool _nativePolicyCoreRequired;
    // M1-T2（ADR-009）：威胁黑名单（可变引用——订阅刷新后整体替换快照）。
    // 策略数据归 broker（ADR-002：broker 唯一策略裁决点），HostWebView 只消费。
    // volatile：后台线程（订阅源刷新）整体替换与 UI 导航读取间保证可见性
    private volatile IBlockedHosts _blockedHosts;
    private bool _disposed;
    // M4-a（ADR-009 审计遗留清零）：KillSwitch 此前全仓零调用点（审计实证）。
    // broker 持有单例，导航/下载/确认全链强制检查；Chrome 经属性暴露触发。
    // CS-291（2026-09-26 审计）：killSwitch 参数注入进程级共享实例
    //（KillSwitch.Shared）——主窗与各无痕窗口的 broker 复用同一开关；缺省
    // 独立实例保持单测隔离（无跨 broker 联动诉求）。
    public KillSwitch KillSwitch { get; }

    // CS-323（2026-09-26 审计）：原生探测结果缓存——此前每次导航决策都
    // ProbeFromEnvironment（原生模式下一轮 NativeLibrary.TryLoad+GetExport+Free）；
    // 成功结果进程内不变即恒缓存，失败按短 TTL 重试（库文件可能随后就位）
    private readonly object _gateLock = new();
    private NativePolicyCoreGateResult? _cachedGateResult;
    private long _cachedGateStampTicks;
    // CS-361（2026-10-01 审计）：失败重试 TTL 可注入——测试缩短到毫秒级断言
    //「TTL 过期后失败结果不再缓存」；生产恒 30s
    internal static TimeSpan GateFailureRetryTtl = TimeSpan.FromSeconds(30);

    public BrowserPolicyBroker(
        Func<NativePolicyCoreGateResult>? nativePolicyCoreGate = null,
        NativePolicyCoreBridge? nativePolicyCoreBridge = null,
        IBlockedHosts? blockedHosts = null,
        KillSwitch? killSwitch = null,
        bool? nativePolicyCoreRequiredForTests = null)
    {
        _nativePolicyCoreGate = nativePolicyCoreGate ?? NativePolicyCoreGate.ProbeFromEnvironment;
        // CS-372（2026-10-01 审计）：native 必需态 internal 测试缝——生产路径
        //（null）仍由环境变量决定并尝试创建真实桥；测试传 true 可注入假
        // gate/黑名单锁定必需模式分支，不需要真实原生库
        _nativePolicyCoreRequired = nativePolicyCoreRequiredForTests ?? NativePolicyCoreGate.IsRequired;
        if (_nativePolicyCoreRequired && nativePolicyCoreRequiredForTests is null)
        {
            // 审计第七轮（2026-10-03·latent：仅在原生门禁开启时生效）：改取进程级
            // 共享桥。Rust 侧 aegis_policy_core_broker_new 强制「进程内单活 broker」
            //（RS-140），第二个 broker_new 返回 null——主窗已在组合根占掉唯一名额，
            // 无痕窗自建桥必得 null → 原生模式下无痕窗每一帧/每一次下载全部
            // native_policy_core_bridge_unavailable（实测缺陷，非理论风险）。
            _nativePolicyCoreBridge = NativePolicyCoreBridgeHub.Acquire(PolicyVersion);
            _nativePolicyCoreBridgeShared = _nativePolicyCoreBridge is not null;
        }
        else
        {
            _nativePolicyCoreBridge = nativePolicyCoreBridge;
        }
        _blockedHosts = blockedHosts ?? NoBlockedHosts.Instance;
        KillSwitch = killSwitch ?? new KillSwitch();
    }

    /// <summary>替换黑名单快照（订阅源后台刷新完成时调用——原子换引用）。
    /// CS-375（2026-10-01 审计）：参数如实声明可空（调用方以 null 表达
    /// "回退空名单"，此前非空签名使 CS-017 回归用例报 CS8625）。
    /// 审计第七轮（2026-10-03）：注入的是进程级共享持有者（SharedBlockedHosts
    /// .Shared）时改向其发布——否则无痕窗口 broker（组合根注入同一持有者、
    /// 自身从不被刷新调用）永远看不到新快照，等价于 denylist 对隐私路径失效；
    /// 实例级注入（单测/独立名单）保持旧的实例内替换语义。</summary>
    public void UpdateBlockedHosts(IBlockedHosts? blockedHosts)
    {
        var snapshot = blockedHosts ?? NoBlockedHosts.Instance;
        if (_blockedHosts is SharedBlockedHosts shared)
        {
            shared.Publish(snapshot);
            return;
        }
        _blockedHosts = snapshot;
    }

    /// <summary>子资源层黑名单查询（HostWebView WebResourceRequested 真拦截——
    /// 命中返回 403 stub。导航层的同名单独在 EvaluateNavigation 内强制）。</summary>
    public bool IsHostBlocked(string host) => _blockedHosts.IsBlocked(host);

    /// <summary>M3 下载授权（ADR-009：下载策略的原生兑现）：会话/标签/代际
    /// 校验通过后登记允许下载（危险扩展已由调用方完成用户确认）。
    /// Rust 契约当前无 download scope——授权在托管 broker 完成（审计留痕），
    /// 未来契约扩展 download 动作时迁移至原生核心托管。</summary>
    public bool AllowDownload(string sessionId, string tabId, string origin,
        string fileName, bool userConfirmed)
    {
        if (KillSwitch.IsEngaged)
        {
            RecordAudit("deny", "download", origin, "kill_switch_engaged");
            return false;
        }
        // 审计第七轮（2026-10-04·R7-CS1-02）：下载 URL 同样是策略输入——此前这道门
        // 只看 kill-switch/会话/标签，从不看 URL，远程页面一个链接即可把
        // http://169.254.169.254/latest/user-data 落盘（导航层已声明的隐私网络边界
        // 在下载层不成立）。取不到绝对地址 = 无法判定 = 一并拒绝（与调用方
        // 「读不到元数据即按危险处理」同口径）。
        if (PrivateNetworkBoundary.DeniesRaw(origin))
        {
            RecordAudit("deny", "download", origin, PrivateNetworkBoundary.DenyCode);
            SecurityLog.Write($"[network] 下载拒绝（本机/内网/链路本地地址或地址不可判定）: {UrlRedactor.Redact(origin)}");
            return false;
        }
        lock (_sessionLock)
        {
            if (_disposed || !_sessions.TryGetValue(sessionId, out var session)
                || session.TabId != tabId)
            {
                RecordAudit("deny", "download", origin, "download_session_context");
                return false;
            }
        }
        RecordAudit("allow", "download", origin,
            userConfirmed ? "user_confirmed" : null);
        SecurityLog.Write($"[download] 允许下载: {fileName}（来源 {UrlRedactor.Redact(origin)}，"
                          + (userConfirmed ? "用户已确认危险扩展" : "常规下载") + "）");
        return true;
    }

    /// <summary>注册由受控 WebView 创建的会话；未知会话上的副作用一律拒绝。</summary>
    public bool RegisterSession(string sessionId, string tabId, ulong generation = 0)
    {
        if (string.IsNullOrWhiteSpace(sessionId) || string.IsNullOrWhiteSpace(tabId))
            return false;
        lock (_sessionLock)
        {
            // CS-332（2026-09-26 审计）：Dispose 后拒绝注册新会话——此前仅
            // AllowDownload 在锁内检查 _disposed，注册路径放行（清空后复活）
            if (_disposed)
                return false;
            if (_sessions.ContainsKey(sessionId))
                return false;
            // 与 Rust MAX_SESSIONS 对等（此前无上限——泄漏面）
            if (_sessions.Count >= MaxSessions)
                return false;
            if (_nativePolicyCoreRequired && (_nativePolicyCoreBridge is null
                || !_nativePolicyCoreBridge.CreateSession(sessionId, tabId, generation, NativeSessionTtlSeconds)))
                return false;
            _sessions.Add(sessionId, new SessionContext(tabId, generation));
            return true;
        }
    }

    /// <summary>文档代际推进时同步会话状态；仅同标签严格单步推进，阻止跳跃和回退。</summary>
    public bool UpdateDocumentGeneration(string sessionId, string tabId, ulong generation)
    {
        lock (_sessionLock)
        {
            if (!_sessions.TryGetValue(sessionId, out var session)
                || !string.Equals(session.TabId, tabId, StringComparison.Ordinal)
                || session.DocumentGeneration == ulong.MaxValue
                || generation != session.DocumentGeneration + 1)
                return false;
            if (_nativePolicyCoreRequired && (_nativePolicyCoreBridge is null
                || !_nativePolicyCoreBridge.AdvanceDocumentGeneration(sessionId, tabId, generation)))
                return false;
            session.DocumentGeneration = generation;
            return true;
        }
    }

    /// <summary>销毁标签会话并清理其 nonce，禁止遗留 WebView 消费旧授权。</summary>
    public void DestroySession(string sessionId)
    {
        if (_nativePolicyCoreRequired)
            _nativePolicyCoreBridge?.DestroySession(sessionId);
        lock (_sessionLock)
            _sessions.Remove(sessionId);
        lock (_nonceLock)
            // CS-285：O(全部 nonce) 的 RemoveWhere——清理为低频销毁操作、nonce 集
            // 有界（MAX_CONSUMED_NONCES=50k），整集扫描比引入 per-session 分桶
            // 索引的复杂度/内存代价划算（分桶在高速导航热路径上是每 nonce 一次
            // 额外字典操作的固定开销）；保持整集扫描为既定取舍
            _consumedNonces.RemoveWhere(nonce => nonce.StartsWith($"{sessionId}:", StringComparison.Ordinal));
    }

    /// <summary>评估导航意图（ProposedAction → Decision——默认拒绝——fail-closed）。</summary>
    public Decision EvaluateNavigation(string sessionId, string tabId, ulong generation,
        string rawUrl, string scope)
    {
        if (KillSwitch.IsEngaged)
        {
            RecordAudit("deny", scope, UrlRedactor.Redact(rawUrl), "kill_switch_engaged");
            return new Decision.Deny(new DenyReason("kill_switch_engaged", "紧急终止开关已触发——全部导航冻结"));
        }
        if (!AllowsNavigationUnderNativePolicyRequirement(scope, rawUrl, out var nativeDenied))
            return nativeDenied;
        if (_nativePolicyCoreRequired)
        {
            // CS-372（2026-10-01 审计）：黑名单门禁前置到桥可用性检查之前——
            // 黑名单命中给出具体拒绝原因（threat_blocklist）优于泛化的
            // bridge_unavailable；此前顺序使「必需模式+无桥」下黑名单分支
            // 不可达，测试无法锁定"native 模式黑名单同样强制"语义
            if (Uri.TryCreate(rawUrl, UriKind.Absolute, out var nativeUri))
            {
                if (_blockedHosts.IsBlocked(nativeUri.Host))
                {
                    RecordAudit("deny", scope, UrlRedactor.Redact(rawUrl), "threat_blocklist");
                    SecurityLog.Write($"[threat] 导航拒绝（黑名单命中）: {UrlRedactor.Redact(rawUrl)}");
                    return new Decision.Deny(new DenyReason("threat_blocklist", "该地址在恶意站点黑名单中，已被拦截。"));
                }
                // 审计第七轮（2026-10-03）：私有/回环拒绝在原生模式同样前置（托管
                // 侧的强制面，与黑名单同源同理——Rust 核心不含本仓的隐私网络边界）
                if (PrivateNetworkBoundary.Denies(nativeUri))
                    return DenyNonPublicTarget(scope, rawUrl);
            }
            if (_nativePolicyCoreBridge is null)
                return NativeBridgeDenied(scope, "native_policy_core_bridge_unavailable");
            var nativeDecision = _nativePolicyCoreBridge.EvaluateNavigation(sessionId, tabId, generation, rawUrl, scope);
            RecordNativeDecision(scope, nativeDecision, rawUrl);
            return nativeDecision;
        }
        if (!HasCurrentSession(sessionId, tabId, generation))
        {
            RecordAudit("deny", scope, UrlRedactor.Redact(rawUrl), "session_context");
            return new Decision.Deny(new DenyReason("session_context", "会话、标签或文档代际无效"));
        }
        if (!OriginPolicy.TryParseExternal(rawUrl, out var uri))
        {
            RecordAudit("deny", scope, UrlRedactor.Redact(rawUrl), "url_policy");
            return new Decision.Deny(new DenyReason("url_policy", "拒绝 URL（非可导航地址）"));
        }
        // M1-T2：威胁黑名单门禁（host 精确+子域后缀匹配；命中 fail-closed 留痕）
        if (_blockedHosts.IsBlocked(uri.Host))
        {
            RecordAudit("deny", scope, UrlRedactor.Redact(rawUrl), "threat_blocklist");
            SecurityLog.Write($"[threat] 导航拒绝（黑名单命中）: {UrlRedactor.Redact(rawUrl)}");
            return new Decision.Deny(new DenyReason("threat_blocklist", "该地址在恶意站点黑名单中，已被拦截。"));
        }
        // 审计第七轮（2026-10-03）：本机/内网/链路本地/元数据地址默认拒绝——
        // 远程页的 SSRF/CSRF 原语（含 iframe 子文档，同一入口）
        if (PrivateNetworkBoundary.Denies(uri))
            return DenyNonPublicTarget(scope, rawUrl);
        var origin = uri.GetLeftPart(UriPartial.Authority);
        var action = new AuthorizedAction(sessionId, tabId, generation, origin, "GET",
            uri.GetComponents(UriComponents.PathAndQuery, UriFormat.UriEscaped), scope, DateTime.UtcNow.Add(ActionLifetime),
            $"{sessionId}:{Guid.NewGuid():N}", PolicyVersion);
        RecordAudit("allow", scope, origin, null);
        return new Decision.Allow(action);
    }

    /// <summary>
    /// 登记需要显式用户确认的导航。确认状态与可兑换授权仅存在于 Rust 核心；
    /// 默认托管路径不得自行重建或签发确认授权。
    /// </summary>
    public Decision RequestNavigationConfirmation(string sessionId, string tabId, ulong generation,
        string rawUrl, string scope)
    {
        // CS-007（审计 2026-09-25）：KillSwitch 前置检查——确认请求同样属于
        // 导航链入口，此前唯一未接 KillSwitch 的入口（AllowDownload/Evaluate/
        // Approve/TryConsume 均已检查），紧急终止期间不得再登记新确认请求
        if (KillSwitch.IsEngaged)
        {
            RecordAudit("deny", scope, UrlRedactor.Redact(rawUrl), "kill_switch_engaged");
            return new Decision.Deny(new DenyReason("kill_switch_engaged", "紧急终止开关已触发——全部导航冻结"));
        }
        if (!AllowsNavigationUnderNativePolicyRequirement(scope, rawUrl, out var nativeDenied))
            return nativeDenied;
        if (!_nativePolicyCoreRequired || _nativePolicyCoreBridge is null)
            return NativeBridgeDenied(scope, "native_confirmation_core_required");
        var decision = _nativePolicyCoreBridge.RequestNavigationConfirmation(sessionId, tabId, generation, rawUrl, scope);
        RecordNativeDecision(scope, decision, rawUrl);
        return decision;
    }

    /// <summary>仅将原生核心已登记的确认请求兑换为其原始绑定授权；异常和不匹配均拒绝。</summary>
    public Decision ApproveNavigationConfirmation(ApprovalRequest request, string rawUrl, string scope)
    {
        if (KillSwitch.IsEngaged)
        {
            RecordAudit("deny", request.Scope, request.Origin, "kill_switch_engaged");
            return new Decision.Deny(new DenyReason("kill_switch_engaged", "紧急终止开关已触发——批准链冻结"));
        }
        if (!AllowsNavigationUnderNativePolicyRequirement(scope, rawUrl, out var nativeDenied))
            return nativeDenied;
        if (!_nativePolicyCoreRequired || _nativePolicyCoreBridge is null)
            return NativeBridgeDenied(scope, "native_confirmation_core_required");
        var decision = _nativePolicyCoreBridge.ApproveNavigationConfirmation(request, rawUrl, scope);
        RecordNativeDecision(scope, decision, rawUrl);
        return decision;
    }

    /// <summary>显式拒绝确认请求；未知 nonce、桥接故障或非原生模式均失败闭合。</summary>
    public bool RejectNavigationConfirmation(ApprovalRequest request)
    {
        if (!ProbeGate().AllowsPlatformBroker
            || !_nativePolicyCoreRequired
            || _nativePolicyCoreBridge is null
            || !_nativePolicyCoreBridge.RejectNavigationConfirmation(request))
            return false;
        RecordAudit("deny", request.Scope, request.Origin, "confirmation_rejected");
        return true;
    }

    /// <summary>
    /// 下载请求默认拒绝（审计 C1——全面审计 2026-09-04）：当前契约没有
    /// 下载授权动作，DownloadStarting 不得绕过 broker 直接放行；调用方
    /// （HostWebView）据此 Handled 抑制原生下载流程，本方法仅留痕。
    /// 与「没有 AuthorizedAction 不能导航/下载/导出」的类声明对齐。
    /// </summary>
    public void DenyDownload(string sessionId, string tabId, string origin)
    {
        RecordAudit("deny", "download", origin, "download_not_authorized");
    }

    /// <summary>校验 AuthorizedAction 是否仍有效（会话/标签/代际/过期/策略版本——fail-closed）。</summary>
    public bool IsValid(AuthorizedAction? action, ulong currentGeneration)
    {
        lock (_sessionLock)
            return IsValidInCurrentSession(action, currentGeneration);
    }

    /// <summary>在真实导航发生前校验并消费授权动作，防止跨会话、错标签和 nonce 重放。</summary>
    public bool TryConsumeNavigation(AuthorizedAction? action, string sessionId, string tabId,
        ulong currentGeneration, string rawUrl, string scope)
    {
        if (!ProbeGate().AllowsPlatformBroker)
            return false;
        if (action is null)
            return false;
        // 消费点强制 KillSwitch（evaluate 与 consume 之间触发时撤销已签发授权——
        // 与 KillSwitch "撤销已发出但未执行的授权" 语义对齐）
        if (KillSwitch.IsEngaged)
        {
            RecordAudit("deny", scope, UrlRedactor.Redact(rawUrl), "kill_switch_engaged");
            return false;
        }
        // 审计第七轮（2026-10-03）：消费点复判隐私网络边界——托管授权只能在
        // EvaluateNavigation 签发（那里已拒），此处兜住"原生核心签发的内网授权"
        // 与调用方伪造动作（与 KillSwitch 在消费点复判同理）
        if (OriginPolicy.TryParseExternal(rawUrl, out var targetUri)
            && PrivateNetworkBoundary.Denies(targetUri))
        {
            RecordAudit("deny", scope, UrlRedactor.Redact(rawUrl), PrivateNetworkBoundary.DenyCode);
            return false;
        }
        if (_nativePolicyCoreRequired)
        {
            if (_nativePolicyCoreBridge is null)
                return false;            lock (_sessionLock)
            {
                if (!IsValidInCurrentSession(action, currentGeneration)
                    || action.SessionId != sessionId || action.TabId != tabId)
                    return false;
                if (!_nativePolicyCoreBridge.TryConsumeNavigation(action, rawUrl, scope))
                    return false;
                // 原生 nonce 是裸的（无前缀），须加 sessionId 前缀与托管路径一致，
                // 否则 DestroySession 的 RemoveWhere("sessionId:") 清不掉 →
                // _consumedNonces 永不清理，满 MAX 后 TryRecordConsumedNonce 恒
                // false → 该 broker 全站导航永久锁死（自 DoS，审计发现 F）。
                return TryRecordConsumedNonce($"{sessionId}:{action.Nonce}");
            }
        }
        if (!OriginPolicy.TryParseExternal(rawUrl, out var uri))
            return false;
        // 与 DestroySession 使用相同锁序列，避免会话销毁后仍可消费旧授权。
        lock (_sessionLock)
        {
            if (!IsValidInCurrentSession(action, currentGeneration)
                || action.SessionId != sessionId || action.TabId != tabId || action.Scope != scope
                || action.Method != "GET" || action.Origin != uri.GetLeftPart(UriPartial.Authority)
                || action.CanonicalParameters != uri.GetComponents(UriComponents.PathAndQuery, UriFormat.UriEscaped))
                return false;
            return TryRecordConsumedNonce(action.Nonce);
        }
    }

    /// <summary>阶段 C：脱敏审计（记录决策——不含 token/网页内容/query secret——
    /// 与 contracts/schemas/audit-event.schema.json 对齐）。</summary>
    public IReadOnlyList<Audit.AuditEvent> AuditLog
    {
        get { lock (_auditLock) return _auditLog.ToArray(); }
    }

    public void Dispose()
    {
        if (_disposed)
            return;
        _disposed = true;
        lock (_sessionLock)
            _sessions.Clear();
        lock (_nonceLock)
            _consumedNonces.Clear();
        if (_nativePolicyCoreBridgeShared)
            // 审计第七轮（2026-10-03）：共享桥只归还引用（归零才真正释放）——
            // 直接 Dispose 会让存活窗口的原生链全断
            NativePolicyCoreBridgeHub.Release(_nativePolicyCoreBridge);
        else
            _nativePolicyCoreBridge?.Dispose();
        GC.SuppressFinalize(this);
    }

    private void RecordAudit(string decision, string scope, string origin, string? reason)
    {
        lock (_auditLock)
        {
            if (_auditLog.Count >= MaxAuditEntries)
                _auditLog.Dequeue();  // 有界环形——最旧条目淘汰（内存审计，非取证存储）
            _auditLog.Enqueue(new Audit.AuditEvent(
                Guid.NewGuid().ToString("N"), DateTime.UtcNow, decision, scope, UrlRedactor.Redact(origin), reason));
        }
    }

    // CS-296（2026-09-26 审计）：审计/日志 URL 脱敏私有副本删除——代理对安全
    // 截断回退分支已吸收进共享 UrlRedactor.Redact 单源，本类全部调用点改走单源。

    /// <summary>记录已消费 nonce；达上限即 fail-closed 拒绝（与 Rust 侧 broker.rs 对等）。
    /// 不淘汰旧 nonce，避免削弱一次性/重放保护。</summary>
    private bool TryRecordConsumedNonce(string nonce)
    {
        lock (_nonceLock)
        {
            if (_consumedNonces.Count >= MaxConsumedNonces)
                return false;
            return _consumedNonces.Add(nonce);
        }
    }

    private bool AllowsNavigationUnderNativePolicyRequirement(
        string scope,
        string rawUrl,
        out Decision.Deny nativeDenied)
    {
        var result = ProbeGate();
        if (result.AllowsPlatformBroker)
        {
            nativeDenied = null!;
            return true;
        }
        var code = result.DenialCode ?? "native_policy_core_unavailable";
        RecordAudit("deny", scope, "native-policy-core", code);
        nativeDenied = new Decision.Deny(new DenyReason(code, "已启用的原生策略核心不可用或不兼容"));
        return false;
    }

    /// <summary>CS-323（2026-09-26 审计）：门禁探测带缓存——成功结果进程内
    /// 不变（环境变量/库文件不热换）恒缓存；失败结果 30s 内不重试，避免每次
    /// 导航决策都跑一轮 NativeLibrary.TryLoad+GetExport+Free（原生模式下的
    /// 每导航固定开销）。锁内短临界区，相对原生探测开销可忽略。</summary>
    private NativePolicyCoreGateResult ProbeGate()
    {
        lock (_gateLock)
        {
            var now = Environment.TickCount64;
            if (_cachedGateResult is { } cached
                && (cached.AllowsPlatformBroker
                    || now - _cachedGateStampTicks < (long)GateFailureRetryTtl.TotalMilliseconds))
                return cached;
            var result = _nativePolicyCoreGate();
            _cachedGateResult = result;
            _cachedGateStampTicks = now;
            return result;
        }
    }

    private Decision.Deny NativeBridgeDenied(string scope, string code)
    {
        RecordAudit("deny", scope, "native-policy-core", code);
        return new Decision.Deny(new DenyReason(code, "已启用的原生策略核心桥接不可用"));
    }

    /// <summary>记录原生核心决策的审计行。CS-404（2026-10-02 审计）：deny 行
    /// 的 origin 此前恒记字面量 "native-policy-core"（被拒地址不可追溯）——
    /// 改记脱敏后的原始 URL（RecordAudit 内部再过一次 UrlRedactor.Redact，
    /// 此处显式脱敏以与其它 deny 行同口径）。</summary>
    private void RecordNativeDecision(string scope, Decision decision, string rawUrl)
    {
        switch (decision)
        {
            case Decision.Allow allow:
                RecordAudit("allow", scope, allow.Action.Origin, null);
                break;
            case Decision.Deny deny:
                RecordAudit("deny", scope, UrlRedactor.Redact(rawUrl), deny.Reason.Code);
                break;
            case Decision.RequireConfirmation confirmation:
                RecordAudit("require_confirmation", confirmation.Request.Scope, confirmation.Request.Origin, null);
                break;
        }
    }

    /// <summary>隐私网络边界命中的拒绝留痕（谓词与文案在 PrivateNetworkBoundary 单源，
    /// 四层出口共用——见该文件注释）。</summary>
    private Decision.Deny DenyNonPublicTarget(string scope, string rawUrl)
    {
        RecordAudit("deny", scope, UrlRedactor.Redact(rawUrl), PrivateNetworkBoundary.DenyCode);
        SecurityLog.Write($"[network] 导航拒绝（本机/内网/链路本地地址）: {UrlRedactor.Redact(rawUrl)}");
        return new Decision.Deny(PrivateNetworkBoundary.Reason);
    }

    private bool HasCurrentSession(string sessionId, string tabId, ulong generation)
    {
        lock (_sessionLock)
        {
            return _sessions.TryGetValue(sessionId, out var session)
                && string.Equals(session.TabId, tabId, StringComparison.Ordinal)
                && session.DocumentGeneration == generation;
        }
    }

    private bool IsValidInCurrentSession(AuthorizedAction? action, ulong currentGeneration)
    {
        return action is not null
            && action.PolicyVersion == PolicyVersion
            && action.DocumentGeneration == currentGeneration
            && _sessions.TryGetValue(action.SessionId, out var session)
            && string.Equals(session.TabId, action.TabId, StringComparison.Ordinal)
            && session.DocumentGeneration == currentGeneration
            && action.ExpiresAt > DateTime.UtcNow;
    }

    private sealed class SessionContext
    {
        public SessionContext(string tabId, ulong documentGeneration)
        {
            TabId = tabId;
            DocumentGeneration = documentGeneration;
        }

        public string TabId { get; }
        public ulong DocumentGeneration { get; set; }
    }
}
