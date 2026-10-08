namespace Aegis.Windows.WebView;

using System;
using System.Threading.Tasks;
using Aegis.Windows.Core.Security;
using Microsoft.Web.WebView2.Core;

/// <summary>WebView2 原生加固束（ADR-009 M1-T2：批次 1 在 pywebview 上费尽周折
/// 的全部加固，在原生宿主直达——无需任何 workaround）：
/// - AreHostObjectsAllowed/AreDefaultScriptDialogs 关闭（页面无宿主对象/原生弹窗）
/// - IsWebMessageEnabled 按来源翻转（远程页面禁用——pywebview 时代靠请求回调
///   逐请求翻转，原生在 NavigationStarting 一次到位）
/// - ESM 探测启用（Profile API 原生可达）
/// - ProcessFailed 崩溃留痕
/// - AddScriptToExecuteOnDocumentCreated 指纹防护前置注入（pywebview 上不可达
///   的 API——B 路线红利的第一批兑现）
/// 全部显式留痕（SecurityLog）——安全状态可观测，绝不静默。</summary>
public static class WebView2Hardening
{
    /// <summary>核心就绪后一次性应用全部加固。返回应用的项数（留痕用）。</summary>
    public static int Apply(CoreWebView2 core, string tabId)
    {
        var applied = 0;
        var settings = core.Settings;
        settings.AreHostObjectsAllowed = false;
        applied++;
        settings.AreDefaultScriptDialogsEnabled = false;
        applied++;
        // IsWebMessageEnabled 由 SetPerOrigin 在每次导航时按来源翻转
        SetPerOrigin(core, core.Source);
        applied++;
        SecurityLog.Write($"[security] 标签 {tabId}: 功能收紧已应用（宿主对象/原生弹窗关闭，WebMessage per-origin）");

        // ESM：SDK 1.0.2903.40 未暴露 EnhancedSecurityModeState ⇒ 反射探测不到就留痕
        // 跳过，绝不伪装生效。**但「升级 SDK 后自动生效」这句是错的**（R8-DEPS-1 复读，
        // 2026-10-08 实测）：取两个 stable 包的
        // lib_manual/netcoreapp3.0/Microsoft.Web.WebView2.Core.dll 直接搜字符串，
        // 1.0.2903.40 与当时最新的 1.0.4258.31 **都是 0 次命中**
        // （对照项 `IsInPrivateModeEnabled` 两版各 2 次命中，证明搜法本身有效）——
        // ESM 至今只存在于 `-prerelease` moniker。所以这条不是「等升级就到位」，
        // 而是要等微软把 ESM 放进 stable SDK；重启判据写在台账第八节 C 类，
        // 别把本行当成待办清单里的一条自动兑现项。
        try
        {
            var profile = core.Profile;
            var esmProperty = profile?.GetType().GetProperty("EnhancedSecurityModeState");
            if (profile is not null && esmProperty is not null)
            {
                esmProperty.SetValue(profile, 1);  // Enabled
                SecurityLog.Write($"[security] 标签 {tabId}: ESM 已启用");
            }
            else
            {
                SecurityLog.Write($"[security] 标签 {tabId}: ESM 未启用（SDK 未暴露 API）");
            }
        }
        catch (Exception ex)
        {
            SecurityLog.Write($"[security] 标签 {tabId}: ESM 启用失败（不影响浏览）: {ex.Message}");
        }
        applied++;

        // 进程崩溃留痕（渲染/GPU 子进程崩溃时宿主仍存活——写安全日志）
        core.ProcessFailed += (_, args) =>
        {
            var kind = args.ProcessFailedKind.ToString();
            SecurityLog.Write($"[native] 标签 {tabId}: WebView2 进程退出 kind={kind}");
        };
        applied++;

        // 指纹防护前置注入（文档创建前执行——页面脚本无法绕过；M3 全量
        // 红蓝对抗管道——每标签会话独立 32 字节加密随机种子）
        // CS-182：注入不再 fire-and-forget——失败留痕（注入静默失败=指纹
        // 防护整段失效且不可观测）
        // CS-405（2026-10-02 审计）：成功日志移入 ContinueWith 的非故障分支
        // ——此前写在 ContinueWith 外，注入实际失败时仍记"已注入"（日志说谎）
        _ = core.AddScriptToExecuteOnDocumentCreatedAsync(
                FingerprintShield.BuildScript(FingerprintShield.NewSessionSeed()))
            .ContinueWith(t =>
            {
                if (t.IsFaulted)
                    SecurityLog.Write($"[security] 标签 {tabId}: 指纹防护注入失败: {t.Exception?.GetBaseException().Message}");
                else
                    SecurityLog.Write($"[security] 标签 {tabId}: 指纹防护全量管道已注入（页面脚本前生效）");
            }, TaskScheduler.Default);
        applied++;
        return applied;
    }

    /// <summary>按来源翻转 IsWebMessageEnabled（每次顶层导航时调用）。
    /// 审计第六轮（2026-10-03）：改**默认拒绝**——仅显式白名单的本地资产虚拟
    /// 主机（https + 受信 host）才开该通道。此前判据是 `isRemote`（仅对
    /// http/https 为真），于是 file:/data:/about: 及一切非 http(s) 形态都落到
    /// <code>!isRemote</code>＝启用分支：远程页执行 <code>location='file:///x'</code>
    /// 虽被 broker 取消导航，仍在显示的远程文档却已被打开 WebMessage 通道
    /// ——ADR-003 声称关死的通道实际处于 fail-open，今日只靠 NtpBridge
    /// .IsTrustedSource + NtpAssets.IsTopLevelNtpDocument 二层兜底。
    /// 白名单口径不扩大（仅 NTP host，与既有 IsTrustedLocalHost 一致）。</summary>
    public static void SetPerOrigin(CoreWebView2 core, string? url)
    {
        try
        {
            var isTrustedShell =
                Uri.TryCreate(url, UriKind.Absolute, out var uri)
                && uri.Scheme == Uri.UriSchemeHttps
                && IsTrustedLocalHost(uri.Host);
            core.Settings.IsWebMessageEnabled = isTrustedShell;
        }
        catch
        {
            // 来源解析失败 → fail-closed 禁用
            core.Settings.IsWebMessageEnabled = false;
        }
    }

    /// <summary>受信本地虚拟主机白名单（NTP 宿主桥唯一激活面；请求通道另经
    /// NtpBridge.IsTrustedSource 双重校验——远程页即便伪装也不可达）。
    /// CS-389（2026-10-02 审计）：删除 chrome.aegis.local 条目——该虚拟主机
    /// 从未被映射（NtpAssets 只映射 ntp/geo），白名单条目指向不存在的宿主；
    /// 真实映射加入时再随映射一并登记。</summary>
    public static bool IsTrustedLocalHost(string host) =>
        host.Equals(Chrome.Ntp.NtpAssets.HostName, StringComparison.OrdinalIgnoreCase);
}