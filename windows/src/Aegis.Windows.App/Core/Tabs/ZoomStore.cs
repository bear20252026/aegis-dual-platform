namespace Aegis.Windows.Core.Tabs;

using System;
using System.Collections.Generic;

/// <summary>每站点缩放因子存储（运行期镜像 AppSettings.ZoomByHost；主窗口负责
/// 持久化——Changed 事件触发写回）。读写全程持锁——Load/Set 并发时不再丢写。</summary>
public static class ZoomStore
{
    private static readonly object Gate = new();
    private static Dictionary<string, double> _map = new(StringComparer.OrdinalIgnoreCase);

    public static event Action? Changed;

    /// <summary>缩放统一边界（与会话内 Ctrl+±、设置归一同口径——此前会话内
    /// 允许 0.25–5.0、持久化钳 1.0–3.0，跨口径静默重置用户设置）。</summary>
    public const double MinZoom = 0.25;
    public const double MaxZoom = 3.0;

    public static void Load(IEnumerable<KeyValuePair<string, double>> map)
    {
        lock (Gate)
        {
            _map = new Dictionary<string, double>(map, StringComparer.OrdinalIgnoreCase);
        }
    }

    public static double Get(string host)
    {
        lock (Gate)
        {
            // CS-036（审计 2026-09-25）：上下界同时钳制——此前只校验下界，
            // 持久层脏值（z=99）会原样返回驱动 WebView2 非法缩放
            return host is not null && _map.TryGetValue(host, out var z)
                && z >= MinZoom - 0.001 ? Math.Clamp(z, MinZoom, MaxZoom) : 1.0;
        }
    }

    public static void Set(string host, double zoom)
    {
        lock (Gate)
        {
            if (string.IsNullOrEmpty(host) || Math.Abs(zoom - 1.0) < 0.001)
            {
                if (host is not null && _map.Remove(host))
                    Changed?.Invoke();
                return;
            }
            _map[host] = Math.Clamp(zoom, MinZoom, MaxZoom);
        }
        Changed?.Invoke();
    }

    public static Dictionary<string, double> Snapshot()
    {
        lock (Gate)
        {
            return new Dictionary<string, double>(_map, StringComparer.OrdinalIgnoreCase);
        }
    }
}
