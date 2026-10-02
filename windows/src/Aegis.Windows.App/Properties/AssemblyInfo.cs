using System.Runtime.CompilerServices;

// CS-409（2026-10-02 审计）：注释如实描述开放面——本特性把程序集**全部**
// internal 成员开放给两个同仓库测试套件（契约解析器只是最早一批消费面，
// 此后各审计批次持续新增 internal 测试缝，如 FaviconService/Favicon 缓存、
// HostWebView.IsExemptFromHttpsUpgrade、TabRuntime.ZoomEpsilon 等）；
// 不构成产品运行时公共 API（测试程序集不随发布物分发）。
[assembly: InternalsVisibleTo("Aegis.Windows.Broker.Tests")]
// CS-040/041（审计 2026-09-25）：HistoryWindow.DateLabel / ParseLocalTime
// 静态分支直测（窗口构造冒烟之外的行为分支覆盖）。
[assembly: InternalsVisibleTo("Aegis.Windows.Core.Tests")]
