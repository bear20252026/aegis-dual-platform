package com.aegis.browser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files
import java.nio.file.Path

/**
 * AD-147（审计 2026-09-23 清单·A6 批）：壁纸白名单打包校验——
 * AegisHomeBridge.WALLPAPERS 与 shared/shell/wallpapers 目录内容此前靠人工
 * 同步（双端漂移：白名单留死名 → 选择不生效；目录新增图未登记 → 静默不可选）。
 * 本测试双向锁定：①白名单每一项都在打包目录中；②目录中的壁纸全部已登记。
 */
class WallpaperPackagingTest {
    /** 从测试工作目录向上定位仓库内 shared/shell/wallpapers（Gradle 测试
     *  工作目录随 AGP 版本在 module/root 间漂移——向上走查消除布局依赖）。 */
    private fun locateShellWallpapersDir(): Path? =
        generateSequence(Path.of(System.getProperty("user.dir")).toAbsolutePath()) { it.parent }
            .take(8)
            .map { it.resolve("shared").resolve("shell").resolve("wallpapers") }
            .firstOrNull { Files.isDirectory(it) }

    private fun requireShellWallpapersDir(): Path =
        checkNotNull(locateShellWallpapersDir()) {
            "未找到 shared/shell/wallpapers 目录（打包校验依赖仓库布局；请在仓库内运行测试）"
        }

    @Test
    fun whitelistedWallpapersAreAllPackaged() {
        val dir = requireShellWallpapersDir()
        AegisHomeBridge.WALLPAPERS.forEach { name ->
            assertTrue(
                "白名单壁纸缺失于打包目录（选择将静默失效）: $name",
                Files.isRegularFile(dir.resolve(name)),
            )
        }
    }

    @Test
    fun packagedImagesAreAllWhitelisted() {
        val dir = requireShellWallpapersDir()
        val packaged =
            Files.list(dir).use { stream ->
                stream
                    .map { it.fileName.toString() }
                    .filter { it.endsWith(".jpg") }
                    .sorted()
                    .toList()
            }
        assertEquals(
            "打包目录存在未登记壁纸（静默不可选——须同步 AegisHomeBridge.WALLPAPERS）",
            AegisHomeBridge.WALLPAPERS.sorted(),
            packaged,
        )
    }
}
