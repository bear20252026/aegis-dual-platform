package com.aegis.browser

import android.app.Application
import com.aegis.broker.AndroidBroker

/**
 * A-6 修复（架构审计 2026-08-31）：进程级 Broker 由 Application 持有——
 * 原 SecureWebViewFactory object 静态单例不可测试、不可多实例隔离；
 * 现在 AndroidBrokerTest 直接构造、运行期经 applicationContext 获取，
 * 生命周期与进程一致且显式可寻。
 */
class AegisApplication : Application() {
    val broker: AndroidBroker = AndroidBroker()
}
