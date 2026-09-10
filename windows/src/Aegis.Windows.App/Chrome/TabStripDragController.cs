namespace Aegis.Windows.Chrome;

using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using Aegis.Windows.Core.Tabs;

/// <summary>标签条拖拽排序控制器（MainWindow 上帝对象拆分·第三批）：真实移动
/// 超过系统阈值才进入拖拽（防 ✕ 点按抖动误拖）、关闭按钮区域不拖、Drop
/// 落点半侧判定后经 TabManager.MoveTab 重排。</summary>
public sealed class TabStripDragController
{
    private readonly ListBox _tabStrip;
    private readonly TabManager _tabs;
    private Point _dragStart;

    public TabStripDragController(ListBox tabStrip, TabManager tabs)
    {
        _tabStrip = tabStrip ?? throw new ArgumentNullException(nameof(tabStrip));
        _tabs = tabs ?? throw new ArgumentNullException(nameof(tabs));
    }

    /// <summary>记录按下起点——拖拽需超过阈值移动才判定为拖拽（防误触发吞点击）。</summary>
    public void RecordDragStart(Point position) => _dragStart = position;

    /// <summary>PreviewMouseMove：按住左键且超过系统最小拖拽阈值 → 发起
    /// 容器级拖放（数据=来源索引）。</summary>
    public void HandlePreviewMouseMove(MouseEventArgs e)
    {
        if (e.LeftButton != MouseButtonState.Pressed)
            return;
        var pos = e.GetPosition(_tabStrip);
        // 真实移动超过系统最小拖拽阈值才进入拖拽——否则点按 ✕ 时的微小抖动
        // 会误触发拖拽、吞掉关闭点击（「标签只能新增不能删除」的根因）
        if (Math.Abs(pos.X - _dragStart.X) < SystemParameters.MinimumHorizontalDragDistance
            && Math.Abs(pos.Y - _dragStart.Y) < SystemParameters.MinimumVerticalDragDistance)
            return;
        if (IsOverCloseButton(pos))
            return;  // 关闭按钮区域不拖拽——交由其 Click 处理
        if (TabItemIndexUnderMouse(pos) is not int fromIndex)
            return;
        _dragStart = pos;  // 抑制重复 DoDragDrop
        // 容器级拖放（数据=来源索引）；DragOver/Drop 完成重排
        DragDrop.DoDragDrop(_tabStrip, fromIndex, DragDropEffects.Move);
    }

    /// <summary>DragOver：落点在标签上且数据匹配才允许 Move。</summary>
    public void HandleDragOver(DragEventArgs e)
    {
        e.Effects = TabItemIndexUnderMouse(e.GetPosition(_tabStrip)) is int
                    && e.Data.GetDataPresent(typeof(int))
            ? DragDropEffects.Move
            : DragDropEffects.None;
        e.Handled = true;
    }

    /// <summary>Drop：落点为标签中心右侧时插入其后（末位拖动体验）。</summary>
    public void HandleDrop(DragEventArgs e)
    {
        if (!e.Data.GetDataPresent(typeof(int))
            || TabItemIndexUnderMouse(e.GetPosition(_tabStrip)) is not int toIndex)
            return;
        var fromIndex = (int)e.Data.GetData(typeof(int));
        if (toIndex > fromIndex && TabItemCenterIsBefore(e.GetPosition(_tabStrip), toIndex))
            toIndex--;
        _tabs.MoveTab(Math.Min(fromIndex, _tabs.Tabs.Count - 1), Math.Max(0, toIndex));
        e.Handled = true;
    }

    /// <summary>命中点是否落在某标签的关闭（✕）按钮上。</summary>
    private bool IsOverCloseButton(Point position)
    {
        if (_tabStrip.InputHitTest(position) is not DependencyObject hit)
            return false;
        var probe = hit;
        while (probe is not null)
        {
            if (probe is Button button && button.Tag is string)
                return true;
            probe = System.Windows.Media.VisualTreeHelper.GetParent(probe);
        }
        return false;
    }

    /// <summary>标签条坐标下的标签索引（ListBox 容器命中——非标签区域返回 null）。</summary>
    private int? TabItemIndexUnderMouse(Point position)
    {
        var element = _tabStrip.InputHitTest(position) as DependencyObject;
        while (element is not null && element is not ListBoxItem)
            element = System.Windows.Media.VisualTreeHelper.GetParent(element);
        return element is ListBoxItem item
            && _tabStrip.ItemContainerGenerator.IndexFromContainer(item) is var idx && idx >= 0
            ? idx
            : null;
    }

    private bool TabItemCenterIsBefore(Point tabStripPosition, int index)
    {
        if (_tabStrip.ItemContainerGenerator.ContainerFromIndex(index) is not ListBoxItem item)
            return false;
        var point = tabStripPosition - item.TranslatePoint(default, _tabStrip);
        return point.X > item.ActualWidth / 2;
    }
}
