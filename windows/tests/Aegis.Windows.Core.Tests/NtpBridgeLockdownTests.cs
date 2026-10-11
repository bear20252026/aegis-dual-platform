namespace Aegis.Windows.Core.Tests;

using System.Text.Json;
using Aegis.Windows.Chrome.Ntp;
using Xunit;

/// <summary>AX-04（外部第三轮审计 2026-10-11）：紧急停止期间，NTP 宿主桥的副作用操作
/// 必须在**分发层**被拒——此前只有 broker 的导航/下载/批准入口查 KillSwitch，
/// 而 `restoreSession`/`importBookmarks`/`importHistory`/`goBack`/`openGeo` 经桥直达数据层。
///
/// 判定点放在 <see cref="NtpBridge.Dispatch"/> 而不是排队的 <c>TryHandle</c>：
/// 导入三操作走 Task.Run，排队之后才进 Dispatch ⇒「先排队、后排紧急停止」会被重新验证。</summary>
public sealed class NtpBridgeLockdownTests
{
    private static JsonElement NoArgs() => JsonSerializer.SerializeToElement(Array.Empty<object>());

    private static JsonElement ArgsOf(params object[] values) =>
        JsonSerializer.SerializeToElement(values);

    private sealed class Recorder
    {
        public List<string> Effects { get; } = [];
        public List<string> Engines { get; } = [];
        public List<string> Wallpapers { get; } = [];

        public void Did(string op) => Effects.Add(op);
    }

    private static NtpBridge Bridge(Func<bool> lockdown, Recorder rec) =>
        new(new NtpBridge.Services(
            SearchEngine: () => "baidu",
            SetSearchEngine: rec.Engines.Add,
            Wallpaper: () => "aurora-lime.jpg",
            SetWallpaper: rec.Wallpapers.Add,
            Bookmarks: () => Array.Empty<Aegis.Windows.Core.Bookmarks.Bookmark>(),
            SavedSessionCount: () => 0,
            RestoreSession: () => rec.Did("restoreSession"),
            Navigate: _ => rec.Did("navigate"),
            GoBack: () => { rec.Did("goBack"); return true; },
            OpenGeo: () => { rec.Did("openGeo"); return true; },
            ImportSources: () => Array.Empty<NtpBridge.ImportSourceSnapshot>(),
            ImportBookmarks: _ => { rec.Did("importBookmarks"); return (0, 0, Array.Empty<NtpBridge.ImportResult>()); },
            ImportHistory: (_, _) => { rec.Did("importHistory"); return (0, 0, Array.Empty<NtpBridge.ImportResult>()); },
            IsLockdownEngaged: lockdown));

    private static string? ErrorOf(object? result)
    {
        // TryGetProperty 在非 Object 元素上是**抛出**而不是返回 false（实测），
        // 而 goBack/openGeo 返回 bool、hasSaved 返回 int——不先判 ValueKind 就是测试自己炸。
        if (result is null)
            return null;
        var element = JsonSerializer.SerializeToElement(result);
        return element.ValueKind == JsonValueKind.Object
               && element.TryGetProperty("error", out var error)
            ? error.GetString()
            : null;
    }

    [Theory]
    [InlineData("navigate")]
    [InlineData("goBack")]
    [InlineData("openGeo")]
    [InlineData("restoreSession")]
    [InlineData("importBookmarks")]
    [InlineData("importHistory")]
    public void SideEffectingOps_AreRefusedDuringLockdown(string op)
    {
        var rec = new Recorder();
        var result = Bridge(() => true, rec).Dispatch(op, op == "navigate" ? ArgsOf("https://example.com") : NoArgs());
        Assert.Equal(NtpBridge.LockdownErrorCode, ErrorOf(result));
        Assert.Empty(rec.Effects);
    }

    [Theory]
    [InlineData("navigate")]
    [InlineData("goBack")]
    [InlineData("openGeo")]
    [InlineData("restoreSession")]
    [InlineData("importBookmarks")]
    [InlineData("importHistory")]
    public void TheSameOps_RunWhenNotEngaged(string op)
    {
        // 反向锚：拒绝必须来自开关本身，而不是「这些操作在桥里根本没接上」。
        var rec = new Recorder();
        var result = Bridge(() => false, rec).Dispatch(op, op == "navigate" ? ArgsOf("https://example.com") : NoArgs());
        Assert.NotEqual(NtpBridge.LockdownErrorCode, ErrorOf(result));
        Assert.Single(rec.Effects);
    }

    [Theory]
    [InlineData("getEngine")]
    [InlineData("getWallpaper")]
    [InlineData("bookmarks")]
    [InlineData("hasSaved")]
    [InlineData("importScan")]
    [InlineData("jsError")]
    public void ReadOps_StayAvailableDuringLockdown(string op)
    {
        // 紧急停止期间用户仍要看得见状态、报得出异常——一刀切会把设置窗/诊断一起废掉。
        var rec = new Recorder();
        Assert.Null(ErrorOf(Bridge(() => true, rec).Dispatch(op, NoArgs())));
    }

    [Fact]
    public void PrefChanges_StillApplyDuringLockdown()
    {
        // setEngine/setWallpaper 改的是本机偏好，不产生网络或数据副作用；冻结期间
        // 连「关掉某项防护」都做不到反而更糟。判定边界在此显式登记，不是漏网。
        var rec = new Recorder();
        var bridge = Bridge(() => true, rec);
        Assert.Null(ErrorOf(bridge.Dispatch("setEngine", ArgsOf("bing"))));
        Assert.Null(ErrorOf(bridge.Dispatch("setWallpaper", ArgsOf("aurora-lime.jpg"))));
        Assert.Equal(["bing"], rec.Engines);
        Assert.Equal(["aurora-lime.jpg"], rec.Wallpapers);
    }

    [Fact]
    public void SameBridge_ReChecksAtExecutionTime_NotAtConstruction()
    {
        // 「排队后才触发紧急停止」的形状：同一实例、同一闭包，翻转判定源必须立刻生效。
        var engaged = false;
        var rec = new Recorder();
        var bridge = Bridge(() => engaged, rec);
        Assert.Null(ErrorOf(bridge.Dispatch("goBack", NoArgs())));
        Assert.Single(rec.Effects);
        engaged = true;
        Assert.Equal(NtpBridge.LockdownErrorCode, ErrorOf(bridge.Dispatch("goBack", NoArgs())));
        Assert.Single(rec.Effects);
    }

    [Fact]
    public void AsyncImportPath_DeliversTheDenialToThePage()
    {
        // CS-031 支路：走 Task.Run 的导入三操作也必须把拒绝**回给页面**——
        // 若这条路径只留 null，前端导入态会被复位成「成功但 0 条」而不是「被拒绝」。
        var rec = new Recorder();
        var bridge = Bridge(() => true, rec);
        var done = new System.Threading.ManualResetEventSlim(false);
        object? response = null;
        bridge.TryHandle(TrustedNtp, ImportBookmarksMessage,
            r => { lock (rec) { response = r; } done.Set(); },
            body => body());
        Assert.True(done.Wait(TimeSpan.FromSeconds(5)), "异步导入路径未响应页面（Promise 永挂）");
        var payload = JsonSerializer.SerializeToElement(response);
        Assert.Equal(7, payload.GetProperty("id").GetInt32());
        Assert.Equal(NtpBridge.LockdownErrorCode,
            payload.GetProperty("result").GetProperty("error").GetString());
        Assert.Empty(rec.Effects);
    }

    [Fact]
    public void UnknownOps_RemainIgnoredNotDeniedByLockdown()
    {
        // 未知操作仍走原有 fail-closed 忽略（返回 null）——新增门禁不能把
        // 「不认识的操作」变成「被紧急停止拒绝」，否则拒绝码失去归因价值。
        var rec = new Recorder();
        Assert.Null(ErrorOf(Bridge(() => true, rec).Dispatch("evilOp", NoArgs())));
        Assert.Empty(rec.Effects);
    }

    private static string TrustedNtp => "https://ntp.aegis.local/start.html";

    private static string ImportBookmarksMessage =>
        """{"__aegis":1,"id":7,"op":"importBookmarks","args":[]}""";
}
