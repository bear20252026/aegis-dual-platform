package com.aegis.browser

import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.neverEqualPolicy
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp
import kotlin.math.abs
import kotlin.random.Random

/**
 * 地址栏贪吃蛇（用户需求：开始游戏时地址栏区域放大 5 倍作为游戏显示带，
 * 游戏结束/退出恢复原高度并回到浏览状态；游戏期间保留迷你地址栏常规功能）。
 *
 * 实现参考（均 MIT 许可，架构模式借鉴、代码针对地址栏横条布局重写）：
 * - TurzimmGit/Snake-Game-APK（detectDragGestures + Canvas + LaunchedEffect 循环）
 * - mukeshsolanki/snake-game-android（MIT (c) 2018 Mukesh Solanki）
 * MIT 版权声明按许可证要求保留于本文件头。
 */

enum class SnakePhase { IDLE, PLAYING, OVER }

/** 地址栏区域高度：普通 56dp ↔ 游戏带 280dp（5 倍，animateDpAsState 平滑过渡）。 */
private val BAR_IDLE = 56.dp
private val BAR_GAME = 280.dp

private enum class Dir { UP, DOWN, LEFT, RIGHT }

private data class Cell(val x: Int, val y: Int)

private class SnakeGame(private val cols: Int, private val rows: Int) {
    var snake = mutableListOf(Cell(cols / 2, rows / 2))
    var dir = Dir.RIGHT
    var food = Cell(0, 0)
    var score = 0
        private set
    var alive = true
        private set

    init { respawnFood() }

    fun respawnFood() {
        do {
            food = Cell(Random.nextInt(cols), Random.nextInt(rows))
        } while (food in snake)
    }

    /** 前进一格；返回 false = 游戏结束（撞墙/撞身）。 */
    fun tick(): Boolean {
        if (!alive) return false
        val head = snake.first()
        val next = when (dir) {
            Dir.UP -> Cell(head.x, head.y - 1)
            Dir.DOWN -> Cell(head.x, head.y + 1)
            Dir.LEFT -> Cell(head.x - 1, head.y)
            Dir.RIGHT -> Cell(head.x + 1, head.y)
        }
        if (next.x !in 0 until cols || next.y !in 0 until rows || next in snake) {
            alive = false
            return false
        }
        snake.add(0, next)
        if (next == food) {
            score += 1
            respawnFood()
        } else {
            snake.removeAt(snake.lastIndex)
        }
        return true
    }

    fun turn(new: Dir) {
        // 禁止 180° 掉头（与当前方向相反）
        val head = snake.firstOrNull() ?: return
        val neck = snake.getOrNull(1) ?: run { dir = new; return }
        val blocked = when (new) {
            Dir.UP -> neck.y < head.y
            Dir.DOWN -> neck.y > head.y
            Dir.LEFT -> neck.x < head.x
            Dir.RIGHT -> neck.x > head.x
        }
        if (!blocked) dir = new
    }
}

/**
 * 地址栏容器：idle 显示常规地址栏（尾部带 🎮 入口）；PLAYING/OVER 放大为
 * 游戏带——顶行保留迷你地址栏（输入网址/回车导航 → 自动退出游戏），
 * 下方为游戏画布（滑动手势控制方向）；OVER 显示分数与再来一局/退出。
 */
@Composable
fun AddressBarWithSnake(
    address: String,
    onAddressChange: (String) -> Unit,
    onOpen: () -> Unit,
    onBack: () -> Unit,
    onForward: () -> Unit,
    onReload: () -> Unit,
    onReader: () -> Unit,
    onTranslate: () -> Unit,
) {
    var phase by remember { mutableStateOf(SnakePhase.IDLE) }
    var restartKey by remember { mutableIntStateOf(0) }

    val barHeight by animateDpAsState(
        targetValue = if (phase == SnakePhase.IDLE) BAR_IDLE else BAR_GAME,
        label = "barHeight",
    )

    Column(modifier = Modifier.fillMaxWidth().height(barHeight)) {
        // 常规地址栏行（游戏期间保留完整功能——输入网址回车导航并退出游戏）
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = address,
                onValueChange = { new ->
                    onAddressChange(new)
                    if (phase != SnakePhase.IDLE) phase = SnakePhase.IDLE // 用户开始浏览 → 退出游戏
                },
                modifier = Modifier.weight(1f),
                singleLine = true,
                label = { Text(if (phase == SnakePhase.IDLE) "地址" else "地址（输入回车将退出游戏）") },
            )
            Button(onClick = {
                if (phase != SnakePhase.IDLE) phase = SnakePhase.IDLE
                onOpen()
            }) { Text("打开") }
            // 游戏入口/退出切换（地址栏尾部）
            if (phase == SnakePhase.IDLE) {
                Button(
                    onClick = { phase = SnakePhase.PLAYING; restartKey++ },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2E7D32)),
                ) { Text("🎮") }
            } else {
                Button(
                    onClick = { phase = SnakePhase.IDLE },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF8B2E2E)),
                ) { Text("✕") }
            }
        }
        // 导航按钮行（仅 idle）
        if (phase == SnakePhase.IDLE) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Button(onClick = onBack) { Text("后退") }
                Button(onClick = onForward) { Text("前进") }
                Button(onClick = onReload) { Text("刷新") }
                Button(onClick = onReader) { Text("阅读") }
                Button(onClick = onTranslate) { Text("翻译") }
            }
        } else {
            SnakeGameArea(
                restartKey = restartKey,
                modifier = Modifier.weight(1f),
                onGameOver = { phase = SnakePhase.OVER },
                onRestart = { restartKey++ },
                onExit = { phase = SnakePhase.IDLE },
            )
        }
    }
}

/** 游戏画布：网格 + 蛇 + 食物；拖动手势控制方向；循环异常自动回退浏览状态。 */
@Composable
private fun SnakeGameArea(
    restartKey: Int,
    modifier: Modifier = Modifier,
    onGameOver: () -> Unit,
    onRestart: () -> Unit,
    onExit: () -> Unit,
) {
    var cols by remember { mutableIntStateOf(0) }
    var rows by remember { mutableIntStateOf(0) }
    // neverEqualPolicy：SnakeGame 是可变对象（tick 原地改列表）——引用不变但
    // 内容每 tick 变化，用 never-equal 强制重绘（BUG-011：此前 tick 自增
    // 从未在组合中读取 → Canvas 永不重绘 → 蛇视觉冻结、滑动「无效」假象）
    var game by remember(restartKey) {
        mutableStateOf<SnakeGame?>(null, neverEqualPolicy())
    }

    Box(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp)
            .onSizeChanged { size ->
                // 网格初始化（尺寸阶段一次完成——不在 draw 阶段写 state）
                if (cols == 0 && size.width > 0 && size.height > 0) {
                    cols = (size.width / 24f).toInt().coerceIn(12, 64)
                    rows = (size.height / 24f).toInt().coerceIn(6, 12)
                    game = SnakeGame(cols, rows)
                }
            }
            .background(Color(0xFF10241C), RectangleShape)
            .pointerInput(Unit) {
                detectDragGestures { change, drag ->
                    change.consume()
                    val g = game ?: return@detectDragGestures
                    val new = if (abs(drag.x) > abs(drag.y)) {
                        if (drag.x > 0) Dir.RIGHT else Dir.LEFT
                    } else {
                        if (drag.y > 0) Dir.DOWN else Dir.UP
                    }
                    g.turn(new)
                }
            },
    ) {
        Canvas(modifier = Modifier.fillMaxWidth().height(BAR_GAME)) {
            val g = game ?: return@Canvas
            val cw = size.width / cols
            val ch = size.height / rows
            // 网格
            for (x in 0..cols) drawLine(Color(0xFF1D3A2E), Offset(x * cw, 0f), Offset(x * cw, size.height))
            for (y in 0..rows) drawLine(Color(0xFF1D3A2E), Offset(0f, y * ch), Offset(size.width, y * ch))
            // 食物
            drawCircle(Color(0xFFFF5252), radius = cw * 0.38f,
                center = Offset(g.food.x * cw + cw / 2, g.food.y * ch + ch / 2))
            // 蛇
            g.snake.forEachIndexed { i, c ->
                drawRect(
                    if (i == 0) Color(0xFF8BC34A) else Color(0xFF4CAF50),
                    topLeft = Offset(c.x * cw + 1, c.y * ch + 1),
                    size = androidx.compose.ui.geometry.Size(cw - 2, ch - 2),
                )
            }
            if (g.alive.not()) {
                drawRect(Color(0x88000000), topLeft = Offset.Zero, size = size)
            }
        }
        // 状态层（分数 / 游戏结束操作）
        val g = game
        when {
            g == null -> {}
            g.alive -> Text(
                "分数 ${g.score} · 滑动控制方向",
                color = Color(0xFFB9E4C7),
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.align(Alignment.TopStart).padding(6.dp),
            )
            else -> Row(
                modifier = Modifier.align(Alignment.Center),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text("游戏结束 · 得分 ${g.score}", color = Color.White)
                Button(onClick = onRestart) { Text("再来一局") }
                Button(onClick = { onExit() }) { Text("退出") }
            }
        }
    }

    // 游戏循环（协程 tick）；异常自动回退浏览状态——游戏永不拖垮浏览器
    LaunchedEffect(restartKey, cols, rows) {
        if (cols == 0 || rows == 0) return@LaunchedEffect
        val speed = 200L  // 初速放缓——横向跑道长，给玩家反应时间
        while (true) {
            kotlinx.coroutines.delay(speed)
            try {
                val g = game ?: continue
                if (g.alive) {
                    if (!g.tick()) {
                        onGameOver()
                    }
                    game = g  // neverEqualPolicy：每 tick 强制重绘（BUG-011）
                }
            } catch (e: Exception) {
                android.util.Log.e("AegisSnake", "game loop error: ${e.message}")
                onExit() // 异常回退：游戏失败绝不影响浏览
                return@LaunchedEffect
            }
        }
    }
}

