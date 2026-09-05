namespace Aegis.Windows.Chrome;

using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

/// <summary>自绘日历日期字段（Apple 风格）：点击字段展开月历浮层——月份导航、
/// 周一起始网格、今日描边、选中填充、回到今天。42 个日格构造一次复用
/// （月切换仅更新文本/样式，零分配），保证流畅与低内存。
/// 通过 <see cref="SelectedDate"/>（DateTime?）读写，用户选择后触发
/// <see cref="SelectedDateChanged"/>。</summary>
public partial class DateField : UserControl
{
    private DateTime? _selectedDate;
    private int _year;
    private int _month;
    private bool _initialized;
    private readonly TextBlock[] _dayTexts = new TextBlock[42];
    private readonly Button[] _dayButtons = new Button[42];

    /// <summary>选择变化（用户点选/回到今天）。</summary>
    public event EventHandler? SelectedDateChanged;

    public DateField()
    {
        InitializeComponent();
        BuildDayCells();
        var today = DateTime.Today;
        _year = today.Year;
        _month = today.Month;
        _initialized = true;
        UpdateFieldText();
    }

    /// <summary>占位文本（未选择时显示）。</summary>
    public string PlaceholderText { get; set; } = "选择日期";

    /// <summary>字段文本（已选择时显示 yyyy-MM-dd）。</summary>
    public string FieldText
    {
        get => FieldLabel.Text;
        set => FieldLabel.Text = value;
    }

    /// <summary>选中的日期（未选择为 null）。</summary>
    public DateTime? SelectedDate
    {
        get => _selectedDate;
        set
        {
            _selectedDate = value;
            if (value is { } d)
            {
                _year = d.Year;
                _month = d.Month;
            }
            UpdateFieldText();
            RenderMonth();
        }
    }

    private void BuildDayCells()
    {
        for (var i = 0; i < 42; i++)
        {
            var index = i;
            var text = new TextBlock();
            var button = new Button
            {
                Style = (Style)Resources["DayCell"],
                Content = text,
            };
            button.Click += (_, _) => OnDayClick(index);
            _dayTexts[i] = text;
            _dayButtons[i] = button;
            DayGrid.Children.Add(button);
        }
    }

    private void OnDayClick(int index)
    {
        if (_dayTexts[index].Tag is not DateTime date)
            return;
        _selectedDate = date;
        _year = date.Year;
        _month = date.Month;
        UpdateFieldText();
        RenderMonth();
        Flyout.IsOpen = false;
        SelectedDateChanged?.Invoke(this, EventArgs.Empty);
    }

    private void UpdateFieldText()
    {
        if (!_initialized)
            return;
        FieldLabel.Text = _selectedDate is { } d ? d.ToString("yyyy-MM-dd") : PlaceholderText;
        // TryFindResource（不抛）——控件在宿主窗口资源树就绪前构造时也能安全初始化
        FieldLabel.Foreground = Res(_selectedDate is null ? "TextSecondaryBrush" : "TextPrimaryBrush");
    }

    /// <summary>资源查找（不抛异常；未命中返回 null → 回退继承/默认色）。</summary>
    private Brush? Res(string key) => TryFindResource(key) as Brush;

    /// <summary>渲染当前月历（复用 42 个日格——仅更新文本与状态样式，零分配）。</summary>
    private void RenderMonth()
    {
        MonthTitle.Text = $"{_year}年{_month}月";
        var first = new DateTime(_year, _month, 1);
        var offset = ((int)first.DayOfWeek + 6) % 7;  // 周一为首列
        var start = first.AddDays(-offset);
        var today = DateTime.Today;
        var accent = Res("AccentBrush") ?? Brushes.DodgerBlue;
        var primary = Res("TextPrimaryBrush") ?? Brushes.Black;
        for (var i = 0; i < 42; i++)
        {
            var date = start.AddDays(i);
            var text = _dayTexts[i];
            text.Text = date.Day.ToString();
            text.Tag = date;  // 日格点击的目标日期
            var button = _dayButtons[i];
            button.Opacity = date.Month == _month ? 1 : 0.32;
            var selected = _selectedDate == date;
            var isToday = date == today;
            if (selected)
            {
                button.Background = accent;
                button.Foreground = Brushes.White;
                button.BorderThickness = new Thickness(0);
            }
            else if (isToday)
            {
                button.Background = Brushes.Transparent;
                button.Foreground = accent;
                button.BorderBrush = accent;
                button.BorderThickness = new Thickness(1);
            }
            else
            {
                button.Background = Brushes.Transparent;
                button.Foreground = primary;
                button.BorderThickness = new Thickness(0);
            }
        }
    }

    private void FieldButton_Click(object sender, RoutedEventArgs e)
    {
        Flyout.IsOpen = !Flyout.IsOpen;
        if (Flyout.IsOpen)
        {
            if (_selectedDate is { } d)
            {
                _year = d.Year;
                _month = d.Month;
            }
            RenderMonth();
        }
    }

    private void PrevMonth_Click(object sender, RoutedEventArgs e)
    {
        (_year, _month) = _month == 1 ? (_year - 1, 12) : (_year, _month - 1);
        RenderMonth();
    }

    private void NextMonth_Click(object sender, RoutedEventArgs e)
    {
        (_year, _month) = _month == 12 ? (_year + 1, 1) : (_year, _month + 1);
        RenderMonth();
    }

    private void Today_Click(object sender, RoutedEventArgs e)
    {
        var today = DateTime.Today;
        _selectedDate = today;
        _year = today.Year;
        _month = today.Month;
        UpdateFieldText();
        RenderMonth();
        Flyout.IsOpen = false;
        SelectedDateChanged?.Invoke(this, EventArgs.Empty);
    }
}
