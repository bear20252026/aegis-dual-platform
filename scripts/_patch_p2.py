# -*- coding: utf-8 -*-
"""P0/P1 补丁：下载持久化+复制路径 / 书签栏 / 右键菜单"""
import pathlib

# ═══ 1. MainWindow.xaml.cs 接线 ═══
p = pathlib.Path("windows/src/Aegis.Windows.App/Chrome/MainWindow.xaml.cs")
t = p.read_text(encoding="utf-8")

# 字段：下载记录存储
old = "    private readonly System.Collections.ObjectModel.ObservableCollection<Core.Downloads.DownloadItem> _downloads = new();"
new = old + "\n    private readonly Core.Downloads.DownloadRecordStore _downloadRecords =\n        new(System.IO.Path.Combine(AppPaths.DataDir, \"downloads.db\"));"
assert old in t, "downloads field not found"
t = t.replace(old, new, 1)

# CreateRuntime 初始化完成回调内：添加下载完成持久化 + favicon 回调
old_nav = """            var core = runtime.Control.CoreWebView2;
            BindVirtualHosts(core);
            runtime.OnCoreReady(core);"""
new_nav = old_nav + """
            // 下载完成 → 持久化记录
            runtime.DownloadOperationStarted += (op, dangerous) =>
            {
                Dispatcher.BeginInvoke(() =>
                {
                    try
                    {
                        var filePath = op?.ResultFilePath ?? "";
                        var size = new System.IO.FileInfo(filePath).Length;
                        _downloadRecords.Add(
                            System.IO.Path.GetFileName(filePath), filePath,
                            op?.Uri ?? "", size, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"));
                    }
                    catch (Exception) { }
                });
            };"""
assert old_nav in t
t = t.replace(old_nav, new_nav, 1)

# 书签栏加载（构造函数）
old_ctor = "        RestoreSessionOrStart();"
new_ctor = old_ctor + "\n        RefreshBookmarkBar();"
assert old_ctor in t
t = t.replace(old_ctor, new_ctor, 1)

# 方法：刷新书签栏
old_sleep = "    private void StartSleepTimer()"
bookmark_methods = """    /// <summary>刷新书签栏（书签变更时重载）。</summary>
    public void RefreshBookmarkBar()
    {
        BookmarkBarItems.Items.Clear();
        foreach (var b in _bookmarks.All())
        {
            var btn = new System.Windows.Controls.Button
            {
                Content = b.Title.Length > 14 ? b.Title[..14] + "…" : b.Title,
                Tag = b.Url,
                ToolTip = b.Url,
            };
            btn.Style = (Style)FindResource("BookmarkBarButton");
            btn.Click += (s, e) =>
            {
                if (s is System.Windows.Controls.Button { Tag: string url } && _activeTabId is not null
                    && _runtimes.TryGetValue(_activeTabId, out var rt))
                    rt.Control.Source = new Uri(url);
            };
            BookmarkBarItems.Items.Add(btn);
        }
        BookmarkBar.Visibility = BookmarkBarItems.Items.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
    }

    private void StartSleepTimer()"""
assert old_sleep in t
t = t.replace(old_sleep, bookmark_methods, 1)

p.write_text(t, encoding="utf-8", newline="")
print("MainWindow cs ok")

# ═══ 2. MainWindow.xaml：书签栏 + 右键菜单事件 ═══
px = pathlib.Path("windows/src/Aegis.Windows.App/Chrome/MainWindow.xaml")
x = px.read_text(encoding="utf-8")

# TabStrip 加 ContextMenuOpening（已有）——确认
# 加书签栏（在搜索行 Grid.Row=1 后面，日期筛选 Grid.Row=2 前面）
old_row = '    <!-- ═══ 日期筛选：分段控件 + 可展开日历 + 范围 ═══ -->'
bookmark_bar = '''    <!-- ═══ 书签栏（固定标签下方，显示常用书签按钮） ═══ -->
    <Border x:Name="BookmarkBar" Grid.Row="2" CornerRadius="10" Margin="0,4,0,0" Padding="6,4"
            Background="{DynamicResource SegmentedBrush}" Visibility="Collapsed">
      <ItemsControl x:Name="BookmarkBarItems">
        <ItemsControl.ItemsPanel>
          <ItemsPanelTemplate><WrapPanel Orientation="Horizontal"/></ItemsPanelTemplate>
        </ItemsControl.ItemsPanel>
      </ItemsControl>
    </Border>

    <!-- ═══ 日期筛选：分段控件 + 可展开日历 + 范围 ═══ '''
# Need to shift rows: bookmark bar becomes row 2, date filter becomes row 2 too (WrapPanel)
# Actually easier: change the bookmark bar to Grid.Row=2 and date filter stays at 2 too (they overlap)
# Let me add a new row definition and shift things.
old_rows = '''    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>'''
new_rows = '''    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>'''
assert old_rows in x
x = x.replace(old_rows, new_rows, 1)

# Date filter row: change Grid.Row="2" to Grid.Row="3"
old_date_row = '<WrapPanel Grid.Row="2" Margin="0,14,0,0" VerticalAlignment="Center">'
new_date_row = '<WrapPanel Grid.Row="3" Margin="0,14,0,0" VerticalAlignment="Center">'
assert old_date_row in x
x = x.replace(old_date_row, new_date_row, 1)

# History list row: Grid.Row="3" → Grid.Row="4"
old_list_row = '<ListBox x:Name="HistoryList" Grid.Row="3"'
new_list_row = '<ListBox x:Name="HistoryList" Grid.Row="4"'
assert old_list_row in x
x = x.replace(old_list_row, new_list_row, 1)

# Empty hint row: Grid.Row="3" → Grid.Row="4"
old_empty = '<TextBlock x:Name="EmptyHint" Grid.Row="3"'
new_empty = '<TextBlock x:Name="EmptyHint" Grid.Row="4"'
assert old_empty in x
x = x.replace(old_empty, new_empty, 1)

# Insert bookmark bar (before date filter row)
old_date = '    <!-- ═══ 日期筛选：分段控件 + 可展开日历 + 范围 ═══ -->'
bookmark_bar = '''    <!-- ═══ 书签栏（固定标签下方，显示常用书签按钮） ═══ -->
    <Border x:Name="BookmarkBar" Grid.Row="2" CornerRadius="10" Margin="0,4,0,0" Padding="6,4"
            Background="{DynamicResource SegmentedBrush}" Visibility="Collapsed">
      <ItemsControl x:Name="BookmarkBarItems">
        <ItemsControl.ItemsPanel>
          <ItemsPanelTemplate><WrapPanel Orientation="Horizontal"/></ItemsPanelTemplate>
        </ItemsControl.ItemsPanel>
        <ItemsControl.ItemTemplate>
          <DataTemplate>
            <Button Content="{Binding}" Click="BookmarkBarItem_Click" Margin="2,0"
                    Background="Transparent" BorderThickness="0" Cursor="Hand"
                    Foreground="{DynamicResource TextPrimaryBrush}" FontSize="12" Padding="6,3"/>
          </DataTemplate>
        </ItemsControl.ItemTemplate>
      </ItemsControl>
    </Border>

    <!-- ═══ 日期筛选：分段控件 + 可展开日历 + 范围 ═══ '''
assert old_date in x
x = x.replace(old_date, bookmark_bar, 1)

# Grid rows for history window: add row for bookmark bar
old_hw_rows = '''    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>'''
new_hw_rows = '''    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>'''
assert old_hw_rows in x
x = x.replace(old_hw_rows, new_hw_rows, 1)

# Empty hint Grid.Row 3→4, HistoryList Grid.Row 3→4
x = x.replace('Grid.Row="3" Margin="0,24,0,0"', 'Grid.Row="4" Margin="0,24,0,0"')
x = x.replace('Grid.Row="3" Margin="0,16,0,0"', 'Grid.Row="4" Margin="0,16,0,0"')

# LoadMoreButton Grid.Row 4→5
x = x.replace('Grid.Row="4" Content="加载更多"', 'Grid.Row="5" Content="加载更多"')

px.write_text(x, encoding="utf-8", newline="")
print("MainWindow xaml ok")

# ═══ 3. DownloadsWindow.xaml：复制路径按钮 ═══
pd = pathlib.Path("windows/src/Aegis.Windows.App/Chrome/DownloadsWindow.xaml")
td = pd.read_text(encoding="utf-8")
old_dl = '<Button Style="{StaticResource LinkButton}" Content="打开文件夹" Click="ShowInFolder_Click" Margin="4,0,0,0"/>'
new_dl = old_dl + '\n                  <Button Style="{StaticResource LinkButton}" Content="复制路径" Click="CopyPath_Click" Margin="4,0,0,0"/>'
assert old_dl in td
td = td.replace(old_dl, new_dl, 1)
pd.write_text(td, encoding="utf-8", newline="")
print("DownloadsWindow xaml ok")

# ═══ 4. DownloadsWindow.xaml.cs：复制路径 handler ═══
pc = pathlib.Path("windows/src/Aegis.Windows.App/Chrome/DownloadsWindow.xaml.cs")
tc = pc.read_text(encoding="utf-8")
old_copy = "    private void ShowInFolder_Click"
add_copy = '''    private void CopyPath_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement { DataContext: DownloadItem item })
        {
            try
            {
                Clipboard.SetText(item.FilePath);
            }
            catch (Exception) { }
        }
    }

    private void ShowInFolder_Click'''
assert old_copy in tc
tc = tc.replace(old_copy, add_copy, 1)
if "using System.Windows.Input;" not in tc:
    tc = tc.replace("using System.Windows.Controls;", "using System.Windows.Controls;\nusing System.Windows.Input;")
pc.write_text(tc, encoding="utf-8", newline="")
print("DownloadsWindow cs ok")
