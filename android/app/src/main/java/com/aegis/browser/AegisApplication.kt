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
    // AD-139（审计 2026-09-23 清单·A6 批）：broker 主线程即时初始化改 lazy——
    // 原字段初始化在 Application 构造期同步执行（requireNativePolicyCore=true
    // 时含 JNA Native.load 跨 JNI 探测），拖慢冷启动首帧且把原生加载失败的
    // 影响提前到进程启动。lazy 后首次消费点 = BrowserViewModel.factory 取
    // broker（首个 Activity 组合期），惰性且线程安全（synchronized 默认模式）。
    val broker: AndroidBroker by lazy { AndroidBroker() }

    override fun onCreate() {
        super.onCreate()
        // AD-065（2026-09-24 审计）：注册全局未捕获异常处理器——崩溃前留痕
        // （logcat -s AegisCrash），随后委托系统默认处理器（崩溃语义不变：
        // 该弹的弹、该杀的杀，只是多一条带堆栈的记录）。
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            android.util.Log.e(
                "AegisCrash",
                "未捕获异常 thread=${thread.name}: ${throwable.javaClass.name}",
                throwable,
            )
            previous?.uncaughtException(thread, throwable)
        }
    }
}
