using System;
using System.Collections;
using System.Collections.Generic;

namespace Aegis.Windows.TestSupport;

/// <summary>后台线程写、测试线程读的记录面（R9-B54 / 台账 §五 Q62 = R9-CS-19）。</summary>
/// <remarks>
/// 为什么不是 `List<T>`：被测对象的回调（`ThreatFeedCoordinator` 的 `applyHosts`/`message`、
/// `CoreDenylistPublisher.CorePushForTests`）跑在**被测试那一侧的线程**上，而测试线程在轮询
/// 等待里每 10ms 枚举同一份表。`List<T>` 在这种读法下会抛
/// `InvalidOperationException: Collection was modified; enumeration operation may not execute`
/// ——实测形态：`ThreatFeedCoordinatorTests.cs:65` 在 CI 上偶发红一条（run 38461642255，
/// 同一 commit 的另两个触发面全绿）。这类红灯的实际处置是「重跑一次」，
/// 而每重跑一次，门禁就少一分可信（R9-CI 那批反复记的同一个失效方向）。
/// <para>
/// 口径：<see cref="Record"/> 与 <see cref="Snapshot"/> 共用一把锁，快照是数组拷贝，
/// 所以任何一条 LINQ 链读到的是**同一份稳定视图**，不会与写入互相打断。
/// 没有选无锁并发集合是刻意的：`ConcurrentQueue<T>` 的枚举自己就声明「不是快照、可能瞬时」，
/// 而这里的断言靠的正是顺序与整体一致（`_pushed[0]`、`Assert.Single(...)`、`OfType&lt;&gt;().Any()`）。
/// </para>
/// <para>
/// 读面**只有** <see cref="Snapshot"/>/枚举/索引器/计数这几个：底层 `List` 不外露，
/// 所以「新加一个读取点顺手直接碰表」这条回潮路径在类型上就不存在。
/// </para>
/// </remarks>
public sealed class ThreadSafeRecorder<T> : IEnumerable<T>
{
    private readonly object _gate = new();
    private readonly List<T> _items = new();

    /// <summary>写入一条记录（被测试那一侧的线程调用）。</summary>
    public void Record(T item)
    {
        lock (_gate)
        {
            _items.Add(item);
        }
    }

    /// <summary>一次性稳定视图：整条链只拷贝一次。</summary>
    public T[] Snapshot()
    {
        lock (_gate)
        {
            return _items.ToArray();
        }
    }

    /// <summary>写入已落定的条数。与随后的枚举**不是同一次快照**——轮询等「够数」时用它，
    /// 拿到数之后再看内容（那才是同一份视图）。</summary>
    public int Count
    {
        get
        {
            lock (_gate)
            {
                return _items.Count;
            }
        }
    }

    public T this[int index] => Snapshot()[index];

    public IEnumerator<T> GetEnumerator() => ((IEnumerable<T>)Snapshot()).GetEnumerator();

    IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
}
