# -*- coding: utf-8 -*-
"""MainWindow.xaml P0+P1 UI 补丁：标签模板(favicon/睡眠/固定/悬停✕)、标签事件、
InPrivate 按钮、查找条、地址栏补全弹窗。"""
import pathlib

P = pathlib.Path("windows/src/Aegis.Windows.App/Chrome/MainWindow.xaml")
t = P.read_text(encoding="utf-8")

# 1) TabStrip 事件接线
old_ts = '<ListBox x:Name="TabStrip" SelectionMode="Single" Background="Transparent"\n                   BorderThickness="0" SelectionChanged="TabStrip_SelectionChanged"'
new_ts = '<ListBox x:Name="TabStrip" SelectionMode="Single" Background="Transparent"\n                   BorderThickness="0" SelectionChanged="TabStrip_SelectionChanged"\n                   ContextMenuOpening="TabStrip_ContextMenuOpening" PreviewMouseDown="TabStrip_PreviewMouseDown"'
assert old_ts in t
t = t.replace(old_ts, new_ts, 1)

# 2) 标签模板重写（favicon 图片+占位点 / 睡眠标记 / 固定隐藏✕ / 悬停显示✕）
old_tpl = t[t.index("            <ListBox.ItemContainerStyle>"):t.index("            </ListBox.ItemContainerStyle>") + len("            </ListBox.ItemContainerStyle>")]
new_tpl = """            <ListBox.ItemContainerStyle>
              <Style TargetType="ListBoxItem">
                <Setter Property="Focusable" Value="False"/>
                <Setter Property="Template">
                  <Setter.Value>
                    <ControlTemplate TargetType="ListBoxItem">
                      <Border x:Name="Chip" CornerRadius="8,8,0,0" Margin="0,0,0,0"
                              Padding="12,6" BorderThickness="1,1,1,0"
                              BorderBrush="Transparent"
                              Background="{DynamicResource ChromeBackgroundBrush}">
                        <DockPanel>
                          <Button x:Name="TabClose" DockPanel.Dock="Right" Content="✕" Click="TabClose_Click"
                                  Tag="{Binding TabId}" Focusable="False" Cursor="Hand"
                                  FontSize="10" Margin="10,0,0,0" Padding="2,0"
                                  Background="Transparent" BorderThickness="0"
                                  ToolTip="关闭标签（Ctrl+W）" Visibility="Collapsed">
                            <Button.Style>
                              <Style TargetType="Button">
                                <Setter Property="Foreground" Value="{DynamicResource TextSecondaryBrush}"/>
                                <Setter Property="Background" Value="Transparent"/>
                                <Setter Property="BorderThickness" Value="0"/>
                                <Setter Property="FontSize" Value="10"/>
                                <Setter Property="Cursor" Value="Hand"/>
                                <Setter Property="Template">
                                  <Setter.Value>
                                    <ControlTemplate TargetType="Button">
                                      <Border Background="Transparent" CornerRadius="9">
                                        <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                                      </Border>
                                    </ControlTemplate>
                                  </Setter.Value>
                                </Setter>
                                <Style.Triggers>
                                  <Trigger Property="IsMouseOver" Value="True">
                                    <Setter Property="Foreground" Value="#FFFFFFFF"/>
                                  </Trigger>
                                </Style.Triggers>
                              </Style>
                            </Button.Style>
                          </Button>
                          <Grid DockPanel.Dock="Left" Width="16" Height="16" Margin="0,0,7,0" VerticalAlignment="Center">
                            <Ellipse Fill="#FF3B82F6"/>
                            <Image Source="{Binding Icon}" Width="16" Height="16"
                                   RenderOptions.BitmapScalingMode="HighQuality">
                              <Image.Style>
                                <Style TargetType="Image">
                                  <Setter Property="Visibility" Value="Visible"/>
                                  <Style.Triggers>
                                    <DataTrigger Binding="{Binding Icon}" Value="{x:Null}">
                                      <Setter Property="Visibility" Value="Collapsed"/>
                                    </DataTrigger>
                                  </Style.Triggers>
                                </Style>
                              </Image.Style>
                            </Image>
                          </Grid>
                          <TextBlock x:Name="SleepMark" DockPanel.Dock="Left" Text="💤" FontSize="10"
                                     Margin="0,0,5,0" Visibility="Collapsed" VerticalAlignment="Center"/>
                          <TextBlock x:Name="TabTitle" Text="{Binding Title}" FontSize="12" MaxWidth="150"
                                     TextTrimming="CharacterEllipsis"
                                     Foreground="{DynamicResource TextSecondaryBrush}"/>
                        </DockPanel>
                      </Border>
                      <ControlTemplate.Triggers>
                        <Trigger Property="IsSelected" Value="True">
                          <Setter TargetName="Chip" Property="Background" Value="{DynamicResource ChromeBackgroundBrush}"/>
                          <Setter TargetName="Chip" Property="BorderBrush" Value="#22FFFFFF"/>
                          <Setter TargetName="TabTitle" Property="Foreground" Value="#FFFFFFFF"/>
                          <Setter TargetName="TabClose" Property="Visibility" Value="Visible"/>
                        </Trigger>
                        <Trigger Property="IsMouseOver" Value="True">
                          <Setter TargetName="Chip" Property="Background" Value="{DynamicResource ButtonOverlayHoverBrush}"/>
                          <Setter TargetName="TabTitle" Property="Foreground" Value="#FFFFFFFF"/>
                          <Setter TargetName="TabClose" Property="Visibility" Value="Visible"/>
                        </Trigger>
                        <DataTrigger Binding="{Binding IsPinned}" Value="True">
                          <Setter TargetName="TabClose" Property="Visibility" Value="Collapsed"/>
                        </DataTrigger>
                        <DataTrigger Binding="{Binding IsSleeping}" Value="True">
                          <Setter TargetName="SleepMark" Property="Visibility" Value="Visible"/>
                        </DataTrigger>
                      </ControlTemplate.Triggers>
                    </ControlTemplate>
                  </Setter.Value>
                </Setter>
              </Style>
            </ListBox.ItemContainerStyle>"""
assert old_tpl in t
t = t.replace(old_tpl, new_tpl, 1)

# 3) InPrivate 按钮（ProfileButton 后）
old_prof = '                  Click="Profile_Click" Margin="6,0,0,0" ToolTip="个人资料"/>'
new_prof = ('                  Click="Profile_Click" Margin="6,0,0,0" ToolTip="个人资料"/>\n'
            '          <Button x:Name="InPrivateButton" Style="{StaticResource NavButton}" Content="🕶"\n'
            '                  Click="InPrivate_Click" Margin="6,0,0,0" ToolTip="InPrivate 无痕窗口"/>')
assert old_prof in t
t = t.replace(old_prof, new_prof, 1)

# 4) 地址栏自动补全弹窗（接在 AddressPill Border 之后——锚定为 AddressPill 闭合后的 AddressHint 行前）
old_addr = '              <TextBlock x:Name="AddressHint" Text="搜索网页或输入网址" VerticalAlignment="Center"'
new_addr = """              <Popup x:Name="SuggestionPopup" PlacementTarget="{Binding ElementName=AddressPill}"
                     Placement="Bottom" StaysOpen="False" AllowsTransparency="True" PopupAnimation="Fade">
                <Border CornerRadius="12" Background="{DynamicResource SurfaceBrush}"
                        BorderBrush="{DynamicResource FieldBorderBrush}" BorderThickness="1"
                        Padding="6" Margin="0,6,0,0" MinWidth="420" MaxWidth="560" MaxHeight="320">
                  <Border.Effect>
                    <DropShadowEffect BlurRadius="20" ShadowDepth="2" Opacity="0.35"/>
                  </Border.Effect>
                  <ListBox x:Name="SuggestionList" Background="Transparent" BorderThickness="0"
                           PreviewKeyDown="SuggestionList_KeyDown">
                    <ListBox.ItemTemplate>
                      <DataTemplate>
                        <Grid Margin="4,3">
                          <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="Auto"/>
                          </Grid.ColumnDefinitions>
                          <TextBlock Text="{Binding Title}" TextTrimming="CharacterEllipsis"
                                     Foreground="{DynamicResource TextPrimaryBrush}" FontSize="12"/>
                          <TextBlock Grid.Column="1" Text="{Binding Kind}" Margin="10,0,0,0"
                                     Foreground="{DynamicResource TextMutedBrush}" FontSize="11"/>
                        </Grid>
                      </DataTemplate>
                    </ListBox.ItemTemplate>
                  </ListBox>
                </Border>
              </Popup>
              <TextBlock x:Name="AddressHint" Text="搜索网页或输入网址" VerticalAlignment="Center" """
assert old_addr in t
t = t.replace(old_addr, new_addr, 1)

# 5) 查找条（覆盖在 WebViewHost 上）+ 地址栏 Popup 容器需要 SurfaceBrush 资源
old_wv = '      <Grid x:Name="WebViewHost"/>'
new_wv = """      <Grid x:Name="WebViewHost"/>
      <!-- P0 页内查找条 -->
      <Border x:Name="FindBar" HorizontalAlignment="Right" VerticalAlignment="Top" Margin="0,10,12,0"
              CornerRadius="12" Background="{DynamicResource SurfaceBrush}"
              BorderBrush="{DynamicResource FieldBorderBrush}" BorderThickness="1"
              Padding="10,6" Visibility="Collapsed" Panel.ZIndex="8">
        <Border.Effect><DropShadowEffect BlurRadius="18" ShadowDepth="2" Opacity="0.35"/></Border.Effect>
        <StackPanel Orientation="Horizontal">
          <TextBox x:Name="FindBox" Width="200" Height="28" VerticalContentAlignment="Center"
                   FontSize="12" BorderThickness="0"
                   Background="{DynamicResource FieldBackgroundBrush}"
                   Foreground="{DynamicResource TextPrimaryBrush}" TextChanged="FindBox_TextChanged"/>
          <TextBlock x:Name="FindCount" VerticalAlignment="Center" Margin="8,0"
                     Foreground="{DynamicResource TextSecondaryBrush}" FontSize="11"/>
          <Button Content="▲" Tag="b" Click="Find_Executed" Width="28" Height="28" Cursor="Hand"
                  Background="Transparent" Foreground="{DynamicResource TextPrimaryBrush}" BorderThickness="0"
                  ToolTip="上一个"/>
          <Button Content="▼" Tag="f" Click="Find_Executed" Width="28" Height="28" Cursor="Hand"
                  Background="Transparent" Foreground="{DynamicResource TextPrimaryBrush}" BorderThickness="0"
                  ToolTip="下一个"/>
          <Button Content="✕" Click="CloseFind_Click" Width="28" Height="28" Cursor="Hand"
                  Background="Transparent" Foreground="{DynamicResource TextSecondaryBrush}" BorderThickness="0"
                  ToolTip="关闭（Esc）"/>
        </StackPanel>
      </Border>"""
assert old_wv in t
t = t.replace(old_wv, new_wv, 1)

# 6) 资源：SurfaceBrush 键（主窗口主题也更新）+ 查找 Enter 处理在 FindBox KeyDown 补
P.write_text(t, encoding="utf-8", newline="")
print("XAML patched OK")
