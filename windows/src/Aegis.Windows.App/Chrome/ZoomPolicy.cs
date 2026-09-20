namespace Aegis.Windows.Chrome;

using System;

/// <summary>每站点缩放步进策略（上帝对象拆分·第七批——MainWindow.ZoomActive 的
/// clamp 纯化）：步进增量后钳制到统一边界 [MinZoom, MaxZoom]（与会话内 Ctrl+±、
/// 设置归一同口径——此前会话内允许 0.25、持久化钳 1.0，跨口径静默重置）。
/// 纯函数可单测。</summary>
public static class ZoomPolicy
{
    /// <summary>对当前缩放施加步进增量并钳制到边界。</summary>
    public static double ApplyStep(double current, double delta) =>
        Math.Clamp(current + delta, TabRuntime.MinZoom, TabRuntime.MaxZoom);
}