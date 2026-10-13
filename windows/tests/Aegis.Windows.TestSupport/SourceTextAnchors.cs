using System;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;

namespace Aegis.Windows.TestSupport;

/// <summary>「按文本判源码」的唯一剔注释口径（R9-B45 / 台账 §五 Q59 R9-SH-17）。</summary>
/// <remarks>
/// 本仓的注记传统是把被禁的旧形态**逐字抄在注释里**（修复说明不抄原文就说不清改了什么），
/// 于是文本锚有两个相反方向的失效：只在注记里出现的形态会让「接线锚」假绿，而任何一句提到
/// 被禁形态的注记会让「不得回潮」的反向锚假红——为了变绿最容易被做的是删注记，丢掉的正是
/// 防止回归的那段上下文。所以判代码不判注释。
/// <para>
/// 收敛前这条纪律在 C# 测试面散了 9 份：4 份 `CodeOnly` + 1 份 `StripLineComments` +
/// 5 处无具名的内联 `Where(line => !line.TrimStart().StartsWith("//"))`。内联那批**只剔整行
/// `//`**，块注释与 ` * ` 续行根本不剔（太窄）；Python 侧另一支曾切「`//` 到行尾」（会连
/// 字符串里的 `https://` 一起吃掉＝过剔）。两种错法同时存在正是没有单一出处的症状。
/// </para>
/// <para>
/// 与 `scripts/text_anchors.py:strip_comments`（Python）、`withoutComments()`
/// （Kotlin 测试源集，`:broker`/`:app` 各一份）同口径，只少一种形态：**不剔整行 `#`**——
/// 那不是 C# 的注释而是预处理指令，剔掉会把 `#if` 之间的代码边界抹平。
/// 行注释只认整行形态，不认行尾形态（同 Python 那份的理由）。
/// </para>
/// </remarks>
public static class SourceTextAnchors
{
    private static readonly Regex BlockComments = new(@"/\*[\s\S]*?\*/", RegexOptions.CultureInvariant);

    /// <summary>剔掉整行 `//`、块注释与 ` * ` 续行，返回只剩代码的文本（行内容不裁剪）。</summary>
    /// <remarks>
    /// **顺序是判据的一部分**：整行 `//` 必须先剔，再做块注释匹配。
    /// `WebViewHardening.kt:41` 的说明里写着 `"https://*"`——其中第二个 `/` 紧跟 `*`
    /// 构成一个假块起点，先做块匹配会一路吃到下一个 `*/`，把中间的真语句删掉
    /// （R9-B45 收敛时实测撞出来，端侧那份同理）。反过来先剔 ` * ` 行会删掉块的**收尾**，
    /// 让剩下的块开头去匹配后面的收尾——所以块匹配必须赶在星号行剔除之前完成。
    /// </remarks>
    public static string CodeOnly(string text)
    {
        // 行尾必须按平台无关方式切分：仓库检出 LF 而工作副本可能 CRLF，
        // 用 Environment.NewLine 切会把整份文件当成一行，注释过滤静默失效（第八轮 B6 由 CI 暴露）。
        var noLineComments = DropLines(text.Replace("\r\n", "\n"), "//");
        var noBlocks = BlockComments.Replace(noLineComments, string.Empty);
        return DropLines(noBlocks, "*");
    }

    /// <summary>丢掉以 <paramref name="prefix"/>（忽略行首缩进）开头的整行。</summary>
    private static string DropLines(string text, string prefix)
    {
        var kept = new List<string>();
        foreach (var line in text.Split('\n'))
        {
            if (!line.TrimStart().StartsWith(prefix, StringComparison.Ordinal))
            {
                kept.Add(line);
            }
        }

        return string.Join('\n', kept);
    }

    /// <summary>读仓库内源码文件并立刻剔注释——绝大多数锚只要这一步。</summary>
    public static string ReadCodeOnly(string repoRoot, params string[] relativeParts)
    {
        var relative = string.Join(Path.DirectorySeparatorChar.ToString(), relativeParts);
        return CodeOnly(File.ReadAllText(Path.Combine(repoRoot, relative)));
    }
}
