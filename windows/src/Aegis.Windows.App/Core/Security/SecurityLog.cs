namespace Aegis.Windows.Core.Security;

using System;
using System.IO;

/// <summary>安全事件落盘（简版——追加写 + 大小有界；M4 由 Diagnostics 层
/// 统一重构）。线程安全：lock 串行化追加（低频安全事件，无性能压力）。</summary>
public static class SecurityLog
{
    private static readonly object Lock = new();
    private const long MaxBytes = 1024 * 1024;  // 1MB 截断（保留尾部——近期事件优先）

    public static void Write(string message)
    {
        try
        {
            lock (Lock)
            {
                var dir = AppPaths.DataDir;
                Directory.CreateDirectory(dir);
                var path = Path.Combine(dir, "security.log");
                if (File.Exists(path) && new FileInfo(path).Length > MaxBytes)
                    File.Delete(path);  // 有界：满即删（近期事件在重启后自然重建）
                File.AppendAllText(
                    path,
                    $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}{Environment.NewLine}");
            }
        }
        catch
        {
            // 日志失败绝不影响主流程（安全事件尽力留痕）
        }
    }
}
