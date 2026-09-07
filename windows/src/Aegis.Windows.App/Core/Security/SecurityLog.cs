namespace Aegis.Windows.Core.Security;

using System;
using System.IO;

/// <summary>安全事件落盘（追加写 + 大小有界轮转）。线程安全：lock 串行化追加
///（低频安全事件，无性能压力）。防伪造：消息内换行替换为转义形式——页面
/// 可控字符串（如 NTP jsError）不能再注入伪造日志行；单条消息长度有界。</summary>
public static class SecurityLog
{
    private static readonly object Lock = new();
    private const long MaxBytes = 1024 * 1024;      // 1MB 触发轮转
    private const int MaxMessageChars = 4000;       // 单条上限

    public static void Write(string message)
    {
        try
        {
            lock (Lock)
            {
                var dir = AppPaths.DataDir;
                Directory.CreateDirectory(dir);
                var path = AppPaths.SecurityLogPath;
                if (File.Exists(path) && new FileInfo(path).Length > MaxBytes)
                {
                    // 轮转而非整删：满 1MB 改名保留一份 .1——刷量攻击不能
                    // 再抹除全部取证痕迹（此前 File.Delete 直接清空）
                    var previous = path + ".1";
                    try
                    {
                        if (File.Exists(previous))
                            File.Delete(previous);
                        File.Move(path, previous);
                    }
                    catch (IOException)
                    {
                        // 轮转失败则截断重写（保底有界）
                        File.Delete(path);
                    }
                }
                var sanitized = (message ?? string.Empty)
                    .Replace("\r", "\\r", StringComparison.Ordinal)
                    .Replace("\n", "\\n", StringComparison.Ordinal);
                if (sanitized.Length > MaxMessageChars)
                    sanitized = sanitized[..MaxMessageChars] + "…(截断)";
                File.AppendAllText(
                    path,
                    $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss zzz}] {sanitized}{Environment.NewLine}");
            }
        }
        catch
        {
            // 日志失败绝不影响主流程（安全事件尽力留痕）
        }
    }
}
