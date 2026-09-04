namespace Aegis.Windows.WebView;

using System;
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

        // ESM：SDK 1.0.2903.40 未暴露 EnhancedSecurityModeState（反射探测——
        // 升级 SDK 后自动生效；当前显式留痕跳过，绝不伪装生效）
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
        core.AddScriptToExecuteOnDocumentCreatedAsync(
            FingerprintShield.BuildScript(FingerprintShield.NewSessionSeed()));
        SecurityLog.Write($"[security] 标签 {tabId}: 指纹防护全量管道已注入（页面脚本前生效）");
        applied++;
        return applied;
    }

    /// <summary>按来源翻转 IsWebMessageEnabled（每次顶层/子框架导航时调用）。
    /// 远程 http/https 页面禁用——js_api 无桥架构（ADR-003）下此通道必须关死。
    /// 唯一例外：受信本地虚拟主机（ntp.aegis.local——M3 新标签页宿主桥；
    /// chrome.aegis.local 预留）——虚拟主机只映射发布资源目录，非远程内容。</summary>
    public static void SetPerOrigin(CoreWebView2 core, string? url)
    {
        try
        {
            var isRemote = Uri.TryCreate(url, UriKind.Absolute, out var uri)
                           && (uri.Scheme == Uri.UriSchemeHttp || uri.Scheme == Uri.UriSchemeHttps)
                           && !IsTrustedLocalHost(uri.Host);
            core.Settings.IsWebMessageEnabled = !isRemote;
        }
        catch
        {
            // 来源解析失败 → fail-closed 禁用
            core.Settings.IsWebMessageEnabled = false;
        }
    }

    /// <summary>受信本地虚拟主机白名单（NTP 宿主桥唯一激活面；请求通道另经
    /// NtpBridge.IsTrustedSource 双重校验——远程页即便伪装也不可达）。</summary>
    public static bool IsTrustedLocalHost(string host) =>
        host.Equals(Chrome.Ntp.NtpAssets.HostName, StringComparison.OrdinalIgnoreCase)
        || host.Equals("chrome.aegis.local", StringComparison.OrdinalIgnoreCase);
}