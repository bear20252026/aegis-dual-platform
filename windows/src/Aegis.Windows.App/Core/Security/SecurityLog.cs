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

    // CS-135：体量计数器——此前每次写都 File.Exists + FileInfo.Length 两次系统
    // 调用。进程首写校准一次现值，其后增量累计（消息为 ASCII 为主的安全事件行，
    // 按 char 数近似字节量——1MB 轮转阈值不需要字节级精确）。
    private static long _approxBytes = -1;  // -1 = 未校准

    /// <summary>CS-246：目录注入面（默认绑定 AppPaths.DataDir）——转义/截断/
    /// 轮转行为此前写死真实用户目录不可直测；测试注入临时目录，生产恒为 null。</summary>
    internal static string? SecurityLogDirOverride;

    public static void Write(string message)
    {
        try
        {
            lock (Lock)
            {
                var dir = SecurityLogDirOverride ?? AppPaths.DataDir;
                Directory.CreateDirectory(dir);
                var path = Path.Combine(dir, Path.GetFileName(AppPaths.SecurityLogPath));
                if (_approxBytes < 0)
                    _approxBytes = File.Exists(path) ? new FileInfo(path).Length : 0;
                if (_approxBytes > MaxBytes)
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
                    _approxBytes = 0;
                }
                var sanitized = (message ?? string.Empty)
                    .Replace("\r", "\\r", StringComparison.Ordinal)
                    .Replace("\n", "\\n", StringComparison.Ordinal);
                if (sanitized.Length > MaxMessageChars)
                    sanitized = sanitized[..MaxMessageChars] + "…(截断)";
                File.AppendAllText(
                    path,
                    $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss zzz}] {sanitized}{Environment.NewLine}");
                _approxBytes += sanitized.Length + 32;
            }
        }
        catch
        {
            // 日志失败绝不影响主流程（安全事件尽力留痕）
        }
    }
}
