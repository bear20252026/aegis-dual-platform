using System.Runtime.CompilerServices;

// 仅开放 C ABI JSON 契约解析器给同仓库回归测试；不构成产品运行时公共 API。
[assembly: InternalsVisibleTo("Aegis.Windows.Broker.Tests")]
// CS-040/041（审计 2026-09-25）：HistoryWindow.DateLabel / ParseLocalTime
// 静态分支直测（窗口构造冒烟之外的行为分支覆盖）。
[assembly: InternalsVisibleTo("Aegis.Windows.Core.Tests")]
