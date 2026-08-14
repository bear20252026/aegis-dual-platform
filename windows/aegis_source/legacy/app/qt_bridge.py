"""qt_bridge.py —— 跨线程回主线程投递桥（v2.1.1 修复 P0-3）。

缺陷背景：在 daemon threading.Thread 的工作线程里调用
QTimer.singleShot(0, cb)，cb 会因该线程没有 Qt 事件循环而**静默丢失**
——AI 代理决策、视觉问答、同步反馈、情报状态四处功能因此全部失效。

本模块提供统一桥：
- run_in_thread(worker, on_main)：worker 后台执行，on_main 恒定在
  Qt 主线程被调用；
- MainBridge 可独立使用（回调线程属于第三方函数——例如
  ThreatFeedUpdater 内部自起线程——的场景：先在主线程建桥，
  把 bridge.payload.emit 作为回调传入）。

原理：桥对象在主线程创建（线程亲和性=主线程），任何线程 emit 信号
都会经 Qt auto connection 自动切换为 QueuedConnection，槽必然落在
主线程事件循环上执行。
"""

import threading

from PySide6.QtCore import QObject, Signal

_LIVE = set()   # 保活：防止单次使用的桥在信号投递前被 GC


class MainBridge(QObject):
    """主线程亲和的中继对象。payload 约定为 (kind, value) 元组。"""

    payload = Signal(object)


def run_in_thread(worker, on_main):
    """worker() 在后台线程执行；on_main(payload) 恒在主线程执行。

    worker 的返回值作为 payload[1]；worker 抛出的异常会被包装为
    ("__error__", exc) 送达主线程，on_main 可自行分支处理。
    返回桥对象（调用方无需持有，模块内已保活至投递完成）。
    """
    bridge = MainBridge()
    bridge.payload.connect(on_main)
    _LIVE.add(bridge)
    bridge.payload.connect(lambda *_a: _LIVE.discard(bridge))

    def _run():
        try:
            result = worker()
            bridge.payload.emit(("__ok__", result))
        except Exception as e:
            bridge.payload.emit(("__error__", e))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    bridge._thread = t          # 防线程句柄被提前回收
    return bridge
