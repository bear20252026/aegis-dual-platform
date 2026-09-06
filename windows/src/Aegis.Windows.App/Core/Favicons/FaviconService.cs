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
/// - 尝试 https://<host>/favicon.ico（8s 超时，200KB 上限）；
/// - 命中内存/磁盘缓存则即时返回（UI 线程可直接渲染，位图已 Freeze）；
/// - 失败/未命中回退 null（UI 显示首字母占位，不阻塞）。
/// 隐私优先：直连站点源，不依赖第三方图标服务。</summary>
public static class FaviconService
{
    private static readonly ConcurrentDictionary<string, ImageSource?> Mem = new(StringComparer.OrdinalIgnoreCase);
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

    /// <summary>取站点图标。onLoaded 在异步抓取完成后回调（UI 线程外→调用方
    /// 自行转 Dispatcher）；同步命中缓存则直接返回并跳过回调。</summary>
    public static ImageSource? Get(string host, Action<ImageSource?>? onLoaded = null)
    {
        if (string.IsNullOrWhiteSpace(host))
            return null;
        if (Mem.TryGetValue(host, out var cached))
            return cached;
        var fromDisk = LoadFromDisk(host);
        if (fromDisk is not null)
        {
            Mem[host] = fromDisk;
            return fromDisk;
        }
        _ = Task.Run(async () =>
        {
            var icon = await FetchAsync(host);
            if (icon is not null)
                Mem[host] = icon;
            if (onLoaded is not null)
            {
                System.Windows.Application.Current?.Dispatcher.BeginInvoke(
                    new Action(() => onLoaded(icon)));
            }
            if (icon is not null)
                SaveToDisk(host, icon);
        });
        return null;
    }

    private static ImageSource? LoadFromDisk(string host)
    {
        var path = CachePath(host);
        if (!File.Exists(path))
            return null;
        try
        {
            var bytes = File.ReadAllBytes(path);
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
            using var fs = File.Create(CachePath(host));
            encoder.Save(fs);
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
            using var response = await Http.GetAsync("https://" + host + "/favicon.ico");
            if (!response.IsSuccessStatusCode)
                return null;
            var bytes = await response.Content.ReadAsByteArrayAsync();
            if (bytes.Length == 0 || bytes.Length > 200 * 1024)
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
