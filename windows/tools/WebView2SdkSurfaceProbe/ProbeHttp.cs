using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;

// 探针自带的最小 HTTP 面（从 RedirectProbe.cs 拆出，为了两份都在 300 行红线内——
// 拆点按职责：测量逻辑 vs 只够回答一个 GET 的服务端）。
// 不用 HttpListener 是有意的：它要 urlacl/管理员，而探针要在任何开发机与 CI runner 上都能跑。

/// <summary>只够回答一个 GET 的 loopback 服务器。不用 <see cref="HttpListener"/> 是有意的：
/// 它要 urlacl/管理员，而探针要在任何开发机上都能跑。</summary>
internal sealed class LoopbackServer : IDisposable
{
    private readonly TcpListener _listener;
    private readonly CancellationTokenSource _cancel = new();

    internal LoopbackServer()
    {
        _listener = new TcpListener(IPAddress.Loopback, 0);
        _listener.Start();
        Port = ((IPEndPoint)_listener.LocalEndpoint).Port;
        Base = $"http://127.0.0.1:{Port}";
        _ = Task.Run(AcceptLoopAsync);
    }

    internal int Port { get; }
    internal string Base { get; }
    internal Func<string, HttpReply>? OnGet { get; set; }

    private async Task AcceptLoopAsync()
    {
        while (!_cancel.IsCancellationRequested)
        {
            TcpClient client;
            try
            {
                client = await _listener.AcceptTcpClientAsync(_cancel.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException) { break; }
            catch (ObjectDisposedException) { break; }
            _ = Task.Run(() => ServeAsync(client));
        }
    }

    private async Task ServeAsync(TcpClient client)
    {
        using (client)
        await using (var stream = client.GetStream())
        {
            var reader = new StreamReader(stream, Encoding.ASCII);
            var requestLine = await reader.ReadLineAsync().ConfigureAwait(false) ?? string.Empty;
            var parts = requestLine.Split(' ');
            var path = parts.Length > 1 ? parts[1] : "/";
            while (true)
            {
                var line = await reader.ReadLineAsync().ConfigureAwait(false);
                if (string.IsNullOrEmpty(line)) break;
            }
            var bytes = (OnGet?.Invoke(path) ?? HttpReply.NotFound()).Render();
            await stream.WriteAsync(bytes).ConfigureAwait(false);
            await stream.FlushAsync().ConfigureAwait(false);
        }
    }

    public void Dispose()
    {
        _cancel.Cancel();
        _listener.Stop();
    }
}

internal readonly record struct HttpReply(int Status, string Reason, string[] Headers, byte[] Body)
{
    internal static HttpReply Redirect(string location) =>
        new(302, "Found", ["Location: " + location, "Content-Length: 0"], []);

    internal static HttpReply Html(string bodyHtml)
    {
        var bytes = Encoding.UTF8.GetBytes(bodyHtml);
        return new(200, "OK",
            ["Content-Type: text/html; charset=utf-8", "Content-Length: " + bytes.Length],
            bytes);
    }

    internal static HttpReply Attachment(byte[] body) =>
        new(200, "OK",
            [
                "Content-Type: application/octet-stream",
                "Content-Disposition: attachment; filename=\"aegis-probe.bin\"",
                "Content-Length: " + body.Length,
            ],
            body);

    internal static HttpReply NotFound() => new(404, "Not Found", ["Content-Length: 0"], []);

    internal byte[] Render()
    {
        var sb = new StringBuilder($"HTTP/1.1 {Status} {Reason}\r\n");
        foreach (var h in Headers) _ = sb.Append(h).Append("\r\n");
        _ = sb.Append("Connection: close\r\n\r\n");
        var head = Encoding.ASCII.GetBytes(sb.ToString());
        var all = new byte[head.Length + Body.Length];
        Buffer.BlockCopy(head, 0, all, 0, head.Length);
        Buffer.BlockCopy(Body, 0, all, head.Length, Body.Length);
        return all;
    }
}
