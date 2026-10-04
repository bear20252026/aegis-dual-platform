namespace Aegis.Windows.WebView;

using System;
using System.Linq;

/// <summary>指纹种子的「站点框定」素材（第七轮 R7-CS1-05/R7-CS2-01·自
/// FingerprintShield.cs 拆出以守行数红线——模板主体仍在主文件，本分片只提供
/// 注入用的 JS 片段与清单）。</summary>
public static partial class FingerprintShield
{
    /// <summary>公共后缀清单——**单源**在 `contracts/policy/public-suffix-list.txt`，
    /// 由 `contracts/codegen/verify_seed_framing_parity.py` 与本数组逐项对账（三端各持一份
    /// 内嵌副本，运行期零 I/O：Windows 制品不额外发布数据文件）。
    /// R6-25/AD-107 的口径：命中表内条目的 host 取后三段为 eTLD+1（a.co.uk 与
    /// b.co.uk 是两个站点）；未命中取后两段。</summary>
    internal static readonly string[] PublicSuffixes =
    [
        "ac.cn", "ac.jp", "ac.th", "ac.uk", "appspot.com", "azurewebsites.net",
        "blogspot.com", "cloudfront.net", "co.id", "co.il", "co.in", "co.jp",
        "co.kr", "co.nz", "co.th", "co.uk", "co.za", "com.ar", "com.au", "com.br",
        "com.cn", "com.co", "com.ec", "com.gr", "com.hk", "com.mx", "com.my",
        "com.pe", "com.ph", "com.pk", "com.pl", "com.pt", "com.py", "com.ro",
        "com.ru", "com.sa", "com.sg", "com.tr", "com.tw", "com.ua", "com.uy",
        "com.ve", "com.vn", "edu.au", "edu.cn", "edu.hk", "github.io", "gitlab.io",
        "go.id", "go.jp", "gob.mx", "gov.au", "gov.cn", "gov.uk", "herokuapp.com",
        "ne.jp", "ne.kr", "net.au", "net.cn", "net.in", "net.nz", "net.sg",
        "net.uk", "netlify.app", "or.jp", "or.kr", "or.th", "org.au", "org.cn",
        "org.hk", "org.il", "org.in", "org.nz", "org.ru", "org.sg", "org.tw",
        "org.uk", "pages.dev", "vercel.app",
    ];

    /// <summary>把清单渲染成 JS 对象字面量（键存在性判定——比 indexOf 数组快，
    // 且与 Kotlin 孪生的数组口径等价）。</summary>
    internal static string PublicSuffixTableJs =>
        "{ " + string.Join(",", PublicSuffixes.Select(s => $"'{s}':1")) + " }";

    /// <summary>顶层站框定（R7-CS1-05≡R7-CS2-01）：种子必须取**顶层 eTLD+1**，
    /// 不是本帧 hostname。参照实现 per_site_seed.rs:17-19 引 Brave 原文
    /// "Third party frames and script share the seed value of the top level
    /// eTLD+1 domain"——按本帧派生时，同一第三方跟踪帧在该用户的所有宿主站点
    /// 上产出**同一个**种子，加噪后的画布哈希本身就成了跨站持久标识符（该机制
    /// 要消除的东西被反手发放）。
    /// Chromium/WebView 提供 `location.ancestorOrigins`（祖先 origin 链，跨源亦
    /// 可见，[0] 为最顶层祖先）——无需宿主下发；取不到（非 Chromium 内核、顶层
    /// 文档、链被隔离）时保守退回本帧 hostname，绝不因顶层链失败而放弃噪声。
    /// 与 Android 孪生 WebViewHardening.kt 的 aegisTopLevelHostname 逐字同口径。</summary>
    internal const string TopLevelHostJs = """
          function aegisHostFromOrigin(o) {
            var s = String(o || '');
            var i = s.indexOf('://');
            if (i >= 0) s = s.slice(i + 3);
            s = s.split('/')[0].split('?')[0];
            if (s.charAt(0) === '[') {           // IPv6 字面量：端口在 ] 之后
              var j = s.indexOf(']');
              return j >= 0 ? s.slice(0, j + 1) : s;
            }
            var k = s.lastIndexOf(':');
            return k >= 0 ? s.slice(0, k) : s;
          }
          function aegisTopLevelHostname() {
            try {
              var anc = location.ancestorOrigins;
              if (anc && anc.length > 0) {
                var h = aegisHostFromOrigin(anc[0]).toLowerCase();
                if (h) return h;
              }
            } catch (e) { /* 退回本帧口径——不得因顶层链失败而放弃噪声 */ }
            return location.hostname;
          }
        """;
}
