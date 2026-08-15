namespace Aegis.Windows.Diagnostics;

using System;
using System.Collections.Generic;

/// <summary>阶段 C（蓝图 windows/src/Aegis.Windows.Diagnostics）：
/// crash/health 非敏感日志骨架——脱敏、速率限制、不可把 token/网页内容
/// 写入日志（蓝图迁移表——event_log/crash_reporter 迁入）。阶段 C 最小。</summary>
public sealed class Diagnostics
{
    private readonly List<string> _nonSensitiveLog = new();

    public void LogNonSensitive(string message)
    {
        // 只记录非敏感信息（不包含 token/网页内容/query secret——脱敏）
        _nonSensitiveLog.Add($"[{DateTime.UtcNow:o}] {message}");
    }

    public IReadOnlyList<string> Log => _nonSensitiveLog;
}
