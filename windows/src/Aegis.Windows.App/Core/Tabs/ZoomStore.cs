namespace Aegis.Windows.Core.Tabs;

using System;
using System.Collections.Generic;

/// <summary>每站点缩放因子存储（运行期镜像 AppSettings.ZoomByHost；主窗口负责
/// 持久化——Changed 事件触发写回）。host → 缩放，缺省 1.0。</summary>
public static class ZoomStore
{
    private static Dictionary<string, double> _map = new(StringComparer.OrdinalIgnoreCase);

    public static event Action? Changed;

    public static void Load(IEnumerable<KeyValuePair<string, double>> map)
    {
        _map = new Dictionary<string, double>(map, StringComparer.OrdinalIgnoreCase);
    }

    public static double Get(string host)
    {
        return host is not null && _map.TryGetValue(host, out var z) && z > 0.2 ? z : 1.0;
    }

    public static void Set(string host, double zoom)
    {
        if (string.IsNullOrEmpty(host) || Math.Abs(zoom - 1.0) < 0.001)
        {
            if (host is not null && _map.Remove(host))
                Changed?.Invoke();
            return;
        }
        _map[host] = Math.Clamp(zoom, 0.25, 5.0);
        Changed?.Invoke();
    }

    public static Dictionary<string, double> Snapshot() => new(_map, StringComparer.OrdinalIgnoreCase);
}
