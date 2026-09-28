namespace Aegis.Windows.Core.Import;

using System.Collections.Generic;
using System.IO;

/// <summary>CS-231：Chrome/Edge 导入探测共享单源——此前 History/Bookmark 两个
/// Importer 各自维护同形 DetectSources 路径拼装（近似复制漂移面）。
/// 仅存在性探测，不读取内容；返回 (浏览器名, 文件路径) 对。</summary>
internal static class ImportProbe
{
    public static IReadOnlyList<(string Browser, string Path)> Probe(string fileName)
    {
        var local = System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData);
        var found = new List<(string, string)>();
        Add(found, "chrome", Path.Combine(local, "Google", "Chrome", "User Data", "Default", fileName));
        Add(found, "edge", Path.Combine(local, "Microsoft", "Edge", "User Data", "Default", fileName));
        for (var i = 1; i <= 9; i++)
        {
            Add(found, $"chrome(profile {i})", Path.Combine(local, "Google", "Chrome", "User Data", $"Profile {i}", fileName));
            Add(found, $"edge(profile {i})", Path.Combine(local, "Microsoft", "Edge", "User Data", $"Profile {i}", fileName));
        }
        return found;
    }

    private static void Add(List<(string, string)> into, string browser, string path)
    {
        if (File.Exists(path))
            into.Add((browser, path));
    }
}
