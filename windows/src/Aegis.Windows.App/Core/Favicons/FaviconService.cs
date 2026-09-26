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

    // CS-121：内存缓存按持久化语义分面——无痕抓取不再写入普通窗口共享缓存
    // （图标元数据不跨信任语境混合；磁盘面此前已隔离，此处补内存面）。
    private static readonly ConcurrentDictionary<string, ImageSource?> Mem = new(StringComparer.OrdinalIgnoreCase);
    private static readonly ConcurrentDictionary<string, ImageSource?> PrivateMem = new(StringComparer.OrdinalIgnoreCase);
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
        var memory = persistToDisk ? Mem : PrivateMem;
        if (memory.TryGetValue(host, out var cached))
            return cached;
        // 同 host 并发导航只发起一次抓取（in-flight 去重）。键含持久化语义——
        // 此前仅按 host 去重：无痕与普通标签并发首取同 host 时先发起方的
        // persistToDisk 生效，无痕站点的图标可被写盘（无痕不落盘承诺失效）。
        var flightKey = persistToDisk ? host : "\0private:" + host;
        // CS-309（2026-09-26 审计）：负缓存 Miss 同样按持久化语义分面——
        // 此前无痕标签抓取失败把 host 写入进程级共享 Miss，普通窗口随后
        // 首访直接命中负缓存不抓取（隐私语境泄漏到持久化语境）
        if (Miss.ContainsKey(flightKey))
        {
            // 负缓存：此前已确认该 host 无可用图标——不再重复抓取
            onLoaded?.Invoke(null);
            return null;
        }
        var task = InFlight.GetOrAdd(flightKey, _ => Task.Run(async () =>
        {
            var icon = persistToDisk ? await LoadFromDiskAsync(host).ConfigureAwait(false) : null;
            icon ??= await (FetchHookForTests is { } hook ? hook(host) : FetchAsync(host)).ConfigureAwait(false);
            if (icon is null)
            {
                Miss[flightKey] = 1;
                TrimCaches();
            }
            else
            {
                memory[host] = icon;
                // CS-119：命中写入后同样修剪——全命中长会话内存不无界增长
                // （此前仅 miss 路径 Trim，正常命中路径只进不出）
                TrimCaches();
                if (persistToDisk)
                    await Task.Run(() => SaveToDisk(host, icon)).ConfigureAwait(false);
            }
            return icon;
        }));
        _ = DeliverAsync(flightKey, task, onLoaded);
        return null;
    }

    private static async Task DeliverAsync(string flightKey, Task<ImageSource?> task, Action<ImageSource?>? onLoaded)
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
            InFlight.TryRemove(flightKey, out _);
        }
        if (onLoaded is not null)
        {
            System.Windows.Application.Current?.Dispatcher.BeginInvoke(
                new Action(() => onLoaded(icon)));
        }
    }

    /// <summary>内存/负缓存上限——长会话不无界增长（CS-121：双内存面一并修剪）。</summary>
    private static void TrimCaches()
    {
        if (Miss.Count > MaxMemoryEntries)
            Miss.Clear();
        if (Mem.Count > MaxMemoryEntries)
            Mem.Clear();
        if (PrivateMem.Count > MaxMemoryEntries)
            PrivateMem.Clear();
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

    /// <summary>CS-120：提 internal 直测——host 归一化（小写）与哈希文件名形态。</summary>
    internal static string CachePath(string host)
    {
        var hash = Convert.ToHexString(SHA1.HashData(Encoding.UTF8.GetBytes(host.ToLowerInvariant())));
        return Path.Combine(CacheDir, hash + ".png");
    }

    // ═══ CS-328（2026-09-26 审计）：可测缝——进程级静态缓存面（负缓存命中
    // 短路/InFlight 去重/TrimCaches 上限）此前零覆盖，注入抓取桩与状态访问器
    // 供单测（生产 FetchHookForTests 恒 null 走真实 FetchAsync） ═══

    /// <summary>测试注入的抓取桩（TaskCompletionSource 可控完成——确定性
    /// 驱动 in-flight/负缓存路径；生产恒 null）。</summary>
    internal static Func<string, Task<ImageSource?>>? FetchHookForTests;

    /// <summary>host 是否已在该持久化语境的负缓存中。</summary>
    internal static bool IsMissCached(string host, bool persistToDisk) =>
        Miss.ContainsKey(persistToDisk ? host : "\0private:" + host);

    /// <summary>该 host 在该持久化语境是否有进行中的抓取。</summary>
    internal static bool IsInFlight(string host, bool persistToDisk) =>
        InFlight.ContainsKey(persistToDisk ? host : "\0private:" + host);

    /// <summary>负缓存条目数（TrimCaches 上限断言用）。</summary>
    internal static int MissCount => Miss.Count;

    /// <summary>测试预置负缓存条目（等价"该语境已确认无图标"状态——
    /// TrimCaches 上限用例需要大批量预置，经真实抓取路径成本不可行）。</summary>
    internal static void SeedMissForTests(string host, bool persistToDisk) =>
        Miss[persistToDisk ? host : "\0private:" + host] = 1;

    /// <summary>清空进程级缓存（测试隔离）。</summary>
    internal static void ClearCachesForTests()
    {
        Miss.Clear();
        InFlight.Clear();
        Mem.Clear();
        PrivateMem.Clear();
    }
}
