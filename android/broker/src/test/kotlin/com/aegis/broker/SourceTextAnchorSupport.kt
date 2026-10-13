package com.aegis.broker

/**
 * 源码文本锚的**前置处理**：按文本判定的常驻用例必须先剔注释再匹配。
 *
 * 为什么这是判据的一部分而不是洁癖（R9-SH-15 / R9-B39 同源，本仓第五次撞）：
 * 1. **假绿**——注释里写出被锚定的形态（`// 现改为 trackConsumedNonce(nonceLedgerKey(...))`）
 *    就能让「代码长这样」的断言通过，而代码其实没长那样；
 * 2. **假红**——本仓的修复注记有把**被禁的历史写法原文抄一遍**的传统（正是 R9-B39 那批
 *    在门禁里踩到的形态），于是「不得再出现旧形态」的反向锚会因为一句解释性注释判红，
 *    下一次为了变绿而删掉的就成了注记而不是缺陷。
 *
 * 口径与 `scripts/text_anchors.py:strip_comments`、C# 的 `SourceTextAnchors.CodeOnly` 一致：
 * 行注释、`#` 注释、C 系块注释、块注释续行的对齐星号。**顺序也是口径**：整行注释必须先剔，
 * 再做块注释匹配——`WebViewHardening.kt:41` 的说明里写着 `"https://*"`，其中第二个 `/` 紧跟 `*`
 * 构成一个假块起点，先做块匹配会一路吃到下一个 `*/`，把中间第 46 行的真语句一起删掉
 * （R9-B45 收敛时实测撞出来：正面控制当场判红）。
 * 两处各自实现是**有意的**——`:broker` 与 `:app` 的测试
 * 源集不共享（要共享得改 Gradle 的 testFixtures 配置，属构建面变更，不在按文本判定的
 * 批次里顺手做）；两边都用同一组语料自证（见 `SourceTextAnchorSupportTest`），
 * 所以「两副本各自漂移」这个老病在这里是可被发现的，不是又一个假绿源。
 */
internal fun String.withoutComments(): String =
    this
        .replace(Regex("(?m)^\\s*//.*$"), "")
        .replace(Regex("(?m)^\\s*#.*$"), "")
        .replace(Regex("/\\*[\\s\\S]*?\\*/"), "")
        .replace(Regex("(?m)^\\s*\\*.*$"), "")
