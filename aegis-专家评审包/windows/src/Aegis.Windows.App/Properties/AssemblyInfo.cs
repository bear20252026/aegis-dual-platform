using System.Runtime.CompilerServices;

// 仅开放 C ABI JSON 契约解析器给同仓库回归测试；不构成产品运行时公共 API。
[assembly: InternalsVisibleTo("Aegis.Windows.Broker.Tests")]
