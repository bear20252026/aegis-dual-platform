namespace Aegis.Windows.Broker;

using System;
using System.Globalization;
using System.Linq;

/// <summary>Origin/URL 策略（阶段 C——Broker 导航决策核心——与 contracts/vectors 对齐）。
/// 外部导航仅 http/https；拒绝 data:/blob:/javascript:/userinfo/控制字符/空白/
/// 无 host/非法端口（0 与越界——CS-418）/超长/尾点 host/IDN bidi 混排/
/// IPv4 八位组越界（CS-418——AD-299 同款口径）（url-origin-invalid 向量——契约一致）。</summary>
public static class OriginPolicy
{
    public const int MaxUrlLength = 8192;
    public const int MaxHostLength = 253;

    /// <summary>CS-418（2026-10-02 审计）：TCP 端口上限（RFC 6335——与 Kotlin
    /// AD-299/Rust origin.rs PY-075 向量同口径）。.NET Uri 解析虽已拒绝 >65535
    /// 的显式端口（既有测试锁定），端口 0 仍被原样放行——此处显式收口，判定
    /// 不依赖平台解析细节；未写端口的 URL Port 为 scheme 默认值（80/443，恒在
    /// 区间内），不受影响。</summary>
    private const int MaxPort = 65535;

    public static bool TryParseExternal(string raw, out Uri uri)
    {
        uri = null!;
        if (string.IsNullOrEmpty(raw) || raw.Length > MaxUrlLength)
            return false;
        foreach (var ch in raw)
        {
            if (ch < 0x20 || ch == 0x7f || char.IsWhiteSpace(ch))
                return false;
        }
        if (!Uri.TryCreate(raw, UriKind.Absolute, out var u))
            return false;
        if (u.Scheme != Uri.UriSchemeHttp && u.Scheme != Uri.UriSchemeHttps)
            return false;
        // PY-076：authority 含 '@'（含空密码形态 "https://@host/"——.NET
        // 解析后 UserInfo 为空串，u.UserInfo 检查不可见）一律拒绝——与 Rust
        // origin.rs / Kotlin rawUserInfo 口径一致
        var schemeEnd = raw.IndexOf("://", StringComparison.Ordinal);
        // R8-CS-SEC-10：无 "://" 的形态（"http:example.com"——Uri.TryCreate
        // 判绝对且 scheme 为 http）此前落到 raw[2..]，authority 成了含 scheme
        // 残片的垃圾串，下方 raw 层防线全部空转。孪生谓词
        // ReservedAddressBoundary.HasNumericAuthority 对同一形态显式拒绝，此处补齐。
        if (schemeEnd < 0)
            return false;
        var authority = raw[(schemeEnd + 3)..];
        var authorityEnd = authority.IndexOfAny(new[] { '/', '?', '#' });
        if (authorityEnd >= 0)
            authority = authority[..authorityEnd];
        if (authority.Contains('@', StringComparison.Ordinal))
            return false;
        // CS-307（2026-09-26 审计）：前导零八进制 IPv4（"0177.0.0.1"）。
        // CS-348（2026-10-01 审计·确定性实验统一口径）：.NET 10 实测
        // Uri.TryCreate 已按 OS inet_aton 语义归一化 host（"0177.0.0.1"→
        // "127.0.0.1"、"192.168.001.001"→"192.168.1.1"，与 UrlSafety.cs 侧
        // IPAddress 实验一致——两文件此前对 .NET 行为留相反注释，必有一处
        // 失实，实验后统一为本口径）。对 raw authority 前置判定仍保留：
        // 下方 IsValidHost 只见归一化结果，而归一化是平台实现细节——显式
        // 拒绝原始前导零形态与 Rust origin.rs「4 段全数字逐段前导零拒绝」
        // 口径一致（双重解释混淆面），不依赖归一化行为
        if (IsLeadingZeroIpv4(authority))
            return false;
        // CS-418（2026-10-02 审计·云端实证补口）：raw 层备用 IPv4 编码拒绝。
        // .NET Uri.TryCreate 把 "127.1"/"2130706433"/"0x7f.1"/"0x7f000001"
        // 归一化为 "127.0.0.1"（CS-348 实验口径）——IsValidHost 的段数/十六
        // 进制判定只见归一化结果，四条共享向量（deny）全部放行（PR #60
        // UrlOriginVectorTests 红灯实证）。口径对齐 Kotlin
        // isAlternateIpv4Encoding（PY-071/072/AD-213）/Rust origin.rs：任一段
        // 0x 前缀十六进制、全数字段数 ≠ 4 一律拒绝（双重解释混淆面）
        if (IsAlternateIpv4Encoding(authority))
            return false;
        if (!string.IsNullOrEmpty(u.UserInfo))
            return false;
        if (string.IsNullOrEmpty(u.Host))
            return false;
        // CS-418（2026-10-02 审计）：端口 0/越界拒绝（PY-075 向量——见 MaxPort 注）
        if (u.Port is < 1 or > MaxPort)
            return false;
        if (!IsValidHost(u.Host))
            return false;
        uri = u;
        return true;
    }

    /// <summary>host 白名单式校验：剥 IPv6 方括号后按标签校验——字母/数字/
    /// 连字符/点（或 IPv6 字面量）；拒绝尾点、空白折叠、Unicode 控制符与
    /// bidi 混排字符（IDN 欺骗面——显示同形不同址）。</summary>
    private static bool IsValidHost(string host)
    {
        if (host.Length == 0 || host.Length > MaxHostLength)
            return false;
        // .NET Uri.Host 对 IPv6 字面量去方括号；DnsSafeHost 保留——按原串判断
        var isIpv6 = host.Contains(':', StringComparison.Ordinal);
        if (isIpv6)
        {
            // 仅允许十六进制/冒号/点（v4-mapped 尾段）
            foreach (var ch in host)
            {
                var isHex = char.IsAsciiDigit(ch)
                    || (ch >= 'a' && ch <= 'f') || (ch >= 'A' && ch <= 'F');
                if (!(isHex || ch == ':' || ch == '.'))
                    return false;
            }
            return true;
        }
        if (host.EndsWith(".", StringComparison.Ordinal))
            return false;  // 尾点 host（"example.com."）——规范化歧义面
        foreach (var ch in host)
        {
            // 非 ASCII（含 punycode 前的 IDN 与 bidi 字符）经 .NET Uri 已转
            // punycode（xn--）；仍显式拒绝非 DNS 安全字符集之外的残留
            if (!(char.IsAsciiLetterOrDigit(ch) || ch == '-' || ch == '.'))
                return false;
        }
        // CS-316（2026-09-26 审计）：一次 Split 复用——标签校验与段数判定
        // 此前对同一 host Split('.') 两次
        var segments = host.Split('.');
        foreach (var label in segments)
        {
            if (label.Length == 0 || label.Length > 63)
                return false;
            if (label.StartsWith('-') || label.EndsWith('-'))
                return false;
        }
        // PY-071/072（审计 2026-09-25）：非点分十进制 IPv4 编码拒绝——整数
        //（2130706433）/0x 十六进制/简写（127.1）OS 解析器均接受，双重解释
        // 混淆面。全数字段且段数 ≠ 4 拒（4 段 = 合法点分 IPv4，保留）；
        // 与 Rust origin.rs / Kotlin OriginPolicy 口径一致
        var lower = host.ToLowerInvariant();
        if (segments.Length != 4 && segments.All(s => s.Length > 0 && s.All(char.IsAsciiDigit)))
            return false;
        // CS-307（2026-09-26 审计）：前导零八进制 IPv4（"0177.0.0.1"）——
        // 4 段全数字即放行的既有分支漏掉此形态：OS 解析栈按八进制解释为
        // 127.0.0.1（双重解释混淆面）。按 IPv4 变体一并拒绝
        if (segments.Length == 4
            && segments.All(s => s.Length > 0 && s.All(char.IsAsciiDigit))
            && segments.Any(s => s.Length > 1 && s[0] == '0'))
            return false;
        // CS-418（2026-10-02 审计）：IPv4 八位组越界拒绝（RS-228 向量——
        // "999.1.1.1"/"256.0.0.1"/"300.300.300.300"；WHATWG IPv4 解析器逐段
        // ≤255 口径，与 Kotlin AD-299/Rust origin.rs 对齐）。此前只看段数，
        // 越界形态混过。超 3 位的数字段必然 >255——先按长度 fail-closed
        //（int.Parse 溢出面），再逐段数值判定
        if (segments.Length == 4
            && segments.All(s => s.Length > 0 && s.All(char.IsAsciiDigit))
            && segments.Any(s => s.Length > 3 || int.Parse(s, CultureInfo.InvariantCulture) > 255))
            return false;
        if (lower.StartsWith("0x") && lower[2..].All(c => char.IsAsciiDigit(c) || (c >= 'a' && c <= 'f')))
            return false;
        return true;
    }

    /// <summary>CS-307：raw authority 是否为「4 段全数字且任一段前导零」的
    /// IPv4 变体（host:port 先剥端口段再判定）。OS 解析栈（inet_aton 语义）
    /// 对前导零段按八进制解释（"0177.0.0.1" = 127.0.0.1），与归一化/显示值
    /// 构成双重解释混淆面。IPv6 字面量（'[' 开头）不属点分形态。</summary>
    private static bool IsLeadingZeroIpv4(string authority)
    {
        if (authority.Length == 0 || authority[0] == '[')
            return false;  // IPv6 字面量或空 authority——非点分 IPv4 形态
        var host = authority;
        var colon = host.LastIndexOf(':');
        if (colon >= 0)
        {
            // host:port——端口段为全数字时按 host:port 剥离；其余畸形形态
            // 不属本判定面（交由 Uri 解析/后续校验拒绝）
            var port = host[(colon + 1)..];
            if (port.Length == 0 || !port.All(char.IsAsciiDigit))
                return false;
            host = host[..colon];
        }
        var segments = host.Split('.');
        return segments.Length == 4
            && segments.All(s => s.Length > 0 && s.All(char.IsAsciiDigit))
            && segments.Any(s => s.Length > 1 && s[0] == '0');
    }

    /// <summary>CS-418：raw authority 备用 IPv4 编码检测（host:port 先剥端口
    /// 段——IsLeadingZeroIpv4 同口径；IPv6 '[' 开头不属点分形态）。覆盖整数
    ///（"2130706433"）、0x 十六进制（整串或逐段，如 "0x7f.1"）、非四段简写
    ///（"127.1"）——OS 解析栈均接受、与归一化显示值构成双重解释混淆面。
    /// 四段全数字（合法点分 IPv4）不属本判定面。</summary>
    private static bool IsAlternateIpv4Encoding(string authority)
    {
        if (authority.Length == 0 || authority[0] == '[')
            return false;  // IPv6 字面量或空 authority——非点分 IPv4 形态
        var host = authority;
        var colon = host.LastIndexOf(':');
        if (colon >= 0)
        {
            var port = host[(colon + 1)..];
            if (port.Length == 0 || !port.All(char.IsAsciiDigit))
                return false;
            host = host[..colon];
        }
        var segments = host.Split('.');
        foreach (var seg in segments)
        {
            if (seg.Length > 2
                && (seg.StartsWith("0x", StringComparison.Ordinal) || seg.StartsWith("0X", StringComparison.Ordinal))
                && seg[2..].All(c => char.IsAsciiDigit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')))
            {
                return true;
            }
        }
        return segments.Length != 4
            && segments.Length > 0
            && segments.All(s => s.Length > 0 && s.All(char.IsAsciiDigit));
    }
}
