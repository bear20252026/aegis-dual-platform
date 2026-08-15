namespace Aegis.Windows.Broker;

using System;

/// <summary>Origin/URL 策略（阶段 C——Broker 导航决策核心——与 contracts/vectors 对齐）。
/// 外部导航仅 http/https；拒绝 data:/blob:/javascript:/userinfo/控制字符/空白/
/// 无 host/非法端口/超长（url-origin-invalid 向量——契约一致）。</summary>
public static class OriginPolicy
{
    public const int MaxUrlLength = 8192;

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
        if (!string.IsNullOrEmpty(u.UserInfo))
            return false;
        if (string.IsNullOrEmpty(u.Host))
            return false;
        uri = u;
        return true;
    }
}
