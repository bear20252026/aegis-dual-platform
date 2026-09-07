namespace Aegis.Windows.Core.Favicons;

using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Media;
using System.Windows.Media.Imaging;

/// <summary>站点 favicon 服务：懒取 + 磁盘缓存 + 内存缓存。
/// - 尝试 https://<host>/favicon.ico（8s 超时，200KB 上限，Content-Length 预检）；
/// - 命中内存缓存即时返回；磁盘读取与网络抓取全部在后台线程（UI 线程零 IO）；
/// - 失败/未命中回退 null（UI 显示首字母占位，不阻塞）；失败负缓存避免
///   无 favicon 站点每次导航都重复打点；
/// - persistToDisk=false（InPrivate）：仅内存缓存——无痕浏览不在磁盘留下
///   已访站点痕迹。
/// 隐私优先：直连站点源，不依赖第三方图标服务。</summary>
public static class FaviconService
{
    private const int MaxFaviconBytes = 200 * 1024;
    private const int MaxMemoryEntries = 500;

    private static readonly ConcurrentDictionary<string, ImageSource?> Mem = new(StringComparer.OrdinalIgnoreCase);
    private static readonly ConcurrentDictionary<string, byte> Miss = new(StringComparer.OrdinalIgnoreCase);
    private static readonly ConcurrentDictionary<string, Task<ImageSource?>> InFlight = new(StringComparer.OrdinalIgnoreCase);
    private static readonly HttpClient Http = CreateHttp();

    private static string CacheDir { get; } =
        Path.Combine(AppPaths.DataDir, "favicons");

    private static HttpClient CreateHttp()
    {
        var client = new HttpClient(new HttpClientHandler
        {
            AllowAutoRedirect = false,
        })
        {
            Timeout = TimeSpan.FromSeconds(8),
        };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("Mozilla/5.0 (AegisBrowser-Favicon)");
        return client;
    }

    /// <summary>取站点图标。onLoaded 在异步抓取/磁盘加载完成后回调（已转回
    /// UI 线程）；同步命中内存缓存则直接返回并跳过回调。persistToDisk=false
    /// 时跳过磁盘读写（无痕——内存缓存即可）。</summary>
    public static ImageSource? Get(string host, Action<ImageSource?>? onLoaded = null, bool persistToDisk = true)
    {
        if (string.IsNullOrWhiteSpace(host))
            return null;
        if (Mem.TryGetValue(host, out var cached))
            return cached;
        if (Miss.ContainsKey(host))
        {
            // 负缓存：此前已确认该 host 无可用图标——不再重复抓取
            onLoaded?.Invoke(null);
            return null;
        }
        // 同 host 并发导航只发起一次抓取（in-flight 去重）
        var task = InFlight.GetOrAdd(host, _ => Task.Run(async () =>
        {
            var icon = persistToDisk ? await LoadFromDiskAsync(host).ConfigureAwait(false) : null;
            icon ??= await FetchAsync(host).ConfigureAwait(false);
            if (icon is null)
            {
                Miss[host] = 1;
                TrimCaches();
            }
            else
            {
                Mem[host] = icon;
                if (persistToDisk)
                    await Task.Run(() => SaveToDisk(host, icon)).ConfigureAwait(false);
            }
            return icon;
        }));
        _ = DeliverAsync(host, task, onLoaded);
        return null;
    }

    private static async Task DeliverAsync(string host, Task<ImageSource?> task, Action<ImageSource?>? onLoaded)
    {
        ImageSource? icon = null;
        try
        {
            icon = await task.ConfigureAwait(false);
        }
        catch (Exception)
        {
            icon = null;  // 未观察异常防线
        }
        finally
        {
            InFlight.TryRemove(host, out _);
        }
        if (onLoaded is not null)
        {
            System.Windows.Application.Current?.Dispatcher.BeginInvoke(
                new Action(() => onLoaded(icon)));
        }
    }

    /// <summary>内存/负缓存上限——长会话不无界增长。</summary>
    private static void TrimCaches()
    {
        if (Miss.Count > MaxMemoryEntries)
            Miss.Clear();
        if (Mem.Count > MaxMemoryEntries)
            Mem.Clear();
    }

    private static async Task<ImageSource?> LoadFromDiskAsync(string host)
    {
        try
        {
            var path = CachePath(host);
            if (!File.Exists(path))
                return null;
            var bytes = await File.ReadAllBytesAsync(path).ConfigureAwait(false);
            return Decode(bytes);
        }
        catch (Exception)
        {
            return null;
        }
    }

    private static void SaveToDisk(string host, ImageSource icon)
    {
        if (icon is not BitmapSource bmp)
            return;
        try
        {
            Directory.CreateDirectory(CacheDir);
            var encoder = new PngBitmapEncoder();
            encoder.Frames.Add(BitmapFrame.Create(bmp));
            // 原子写：先写临时文件再替换——崩溃不留半写 PNG
            var finalPath = CachePath(host);
            var tempPath = finalPath + ".tmp";
            using (var fs = File.Create(tempPath))
                encoder.Save(fs);
            if (File.Exists(finalPath))
                File.Replace(tempPath, finalPath, null);
            else
                File.Move(tempPath, finalPath);
        }
        catch (Exception)
        {
            // 缓存写入失败不影响功能
        }
    }

    private static async Task<ImageSource?> FetchAsync(string host)
    {
        try
        {
            using var response = await Http.GetAsync("https://" + host + "/favicon.ico").ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
                return null;
            // 先看声明长度再缓冲——超大响应不进内存
            if (response.Content.Headers.ContentLength is long declared
                && (declared <= 0 || declared > MaxFaviconBytes))
                return null;
            var bytes = await response.Content.ReadAsByteArrayAsync().ConfigureAwait(false);
            if (bytes.Length == 0 || bytes.Length > MaxFaviconBytes)
                return null;
            return Decode(bytes);
        }
        catch (Exception)
        {
            return null;
        }
    }

    private static ImageSource? Decode(byte[] bytes)
    {
        try
        {
            var bitmap = new BitmapImage();
            bitmap.BeginInit();
            bitmap.CacheOption = BitmapCacheOption.OnLoad;
            bitmap.StreamSource = new MemoryStream(bytes);
            bitmap.EndInit();
            bitmap.Freeze();  // 可跨线程/直接绑定
            return bitmap;
        }
        catch (Exception)
        {
            return null;
        }
    }

    private static string CachePath(string host)
    {
        var hash = Convert.ToHexString(SHA1.HashData(Encoding.UTF8.GetBytes(host.ToLowerInvariant())));
        return Path.Combine(CacheDir, hash + ".png");
    }
}
