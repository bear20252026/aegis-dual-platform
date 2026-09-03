namespace Aegis.Windows.Core;

using System;
using System.IO;

/// <summary>C# 栈数据目录解析（ADR-009：与 Python stable 渠道的数据目录
/// 隔离——beta 渠道独立存储，避免跨渠道读写干扰）。</summary>
public static class AppPaths
{
    public static string DataDir =>
        Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Aegis",
            "AegisCSharp");

    public static string SessionDbPath => Path.Combine(DataDir, "tabs.db");
}
