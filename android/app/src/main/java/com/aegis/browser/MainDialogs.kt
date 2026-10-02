@file:Suppress("MatchingDeclarationName") // AD-183：文件承载「状态机 + 三对话框 + 宿主」的对话框家族，非单声明文件

package com.aegis.browser

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

// AD-183（审计 2026-09-23 清单·A7 批）：主界面对话框组件文件——阅读模式、
// WebView 版本提示、导航审批三个对话框自 MainActivity.kt 抽出（onCreate
// 装配体回到改造红线内；本文件只承载对话框 UI 与其优先级状态机）。
//
// AD-151（审计 2026-09-23 清单·A7 批）：三对话框优先级状态机——原实现三个
// AlertDialog 各自独立渲染（状态同时非空时叠窗并存：多个遮罩层、返回键
// dismiss 目标不明、Compose 对话框层叠顺序依赖组合顺序而非安全语义）。
// 现收敛为 [ActiveDialog] 单槽状态机：同一时刻至多呈现一个对话框，
// 槽位由 [resolveActiveDialog] 按安全优先级裁决——
//   待审批导航（安全决策面，误 dismiss 即导航阻断）>
//   安全提示（版本/拒绝类提示，可稍后处理）>
//   阅读模式（纯内容增强）。
// 低优先级对话框只是被暂时遮蔽（状态仍在），高优先级清除后自然复现；
// 任何槽位都不吞并其它状态（dismiss 语义经各自回调原样上抛）。
//
// 纯函数 + 不可变入参——[resolveActiveDialog] 可 JVM 直测
// （DialogPriorityTest 锁定优先级与空态）。

/** 对话框槽位（优先级即枚举声明序——见 [resolveActiveDialog]）。 */
internal enum class ActiveDialog {
    /** 待审批导航确认（最高优先级——安全决策面）。 */
    PENDING_CONFIRMATION,

    /**
     * 待确认下载（AD-331，2026-10-02 审计）——仅查询参数命中危险扩展的
     * 二级防线（路径/文件名命中已硬拦截，不再进本槽）。
     */
    DOWNLOAD_CONFIRMATION,

    /** WebView 版本/安全提示。 */
    WEB_VIEW_ALERT,

    /** 阅读模式正文。 */
    READER_CONTENT,
}

/**
 * AD-151：对话框优先级裁决（单槽状态机的转移函数）。
 * 同刻多状态非空时仅返回最高优先级槽位；全空返回 null（无对话框）。
 * AD-331（2026-10-02 审计）：新增下载确认槽（优先级介于导航审批与安全提示
 * 之间——同为安全决策面，但不得遮蔽导航审批）。
 */
internal fun resolveActiveDialog(
    pendingConfirmation: PendingNavigationConfirmation?,
    pendingDownload: PendingDownloadConfirmation?,
    webViewAlert: WebViewAlertNotice?,
    readerContent: ReaderContent?,
): ActiveDialog? =
    when {
        pendingConfirmation != null -> ActiveDialog.PENDING_CONFIRMATION
        pendingDownload != null -> ActiveDialog.DOWNLOAD_CONFIRMATION
        webViewAlert != null -> ActiveDialog.WEB_VIEW_ALERT
        readerContent != null -> ActiveDialog.READER_CONTENT
        else -> null
    }

/**
 * A1：WebView 版本过旧安全提示对话框（CVE-2026-12438/11295 防御）。
 *
 * AD-204（审计 2026-09-23 清单·A7 批）：「去更新」失败降级——[onGoUpdate]
 * 由调用方消费 WebViewVersionCheck.openUpdate 的受理结果，跳转失败时
 * （无 Play Store/无浏览器）回填降级提示，不再静默无反馈。
 *
 * AD-260（2026-10-01 审计）：提示分型——版本检查（[Kind.VERSION_CHECK]）
 * 双按钮（去更新/稍后）；一般安全提示（[Kind.SECURITY_NOTICE]）单按钮
 * （知道了）——导航被拒/历史不可用等瞬时提示不再顶着「去更新」按钮误导。
 */
@Suppress("FunctionNaming")
@Composable
internal fun WebViewAlertDialog(
    notice: WebViewAlertNotice,
    onGoUpdate: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.alert_title)) },
        text = { Text(notice.message) },
        confirmButton = {
            if (notice.kind == WebViewAlertNotice.Kind.VERSION_CHECK) {
                TextButton(onClick = onGoUpdate) { Text(stringResource(R.string.alert_go_update)) }
            } else {
                TextButton(onClick = onDismiss) { Text(stringResource(R.string.alert_ack)) }
            }
        },
        dismissButton = {
            if (notice.kind == WebViewAlertNotice.Kind.VERSION_CHECK) {
                TextButton(onClick = onDismiss) { Text(stringResource(R.string.alert_later)) }
            }
        },
    )
}

/**
 * 受信 Compose chrome 审批层对话框：远程页面没有该回调或授权对象；
 * 默认关闭即拒绝（onDismissRequest 与拒绝按钮同走 [onReject]）。
 */
@Suppress("FunctionNaming")
@Composable
internal fun NavigationConfirmationDialog(
    pending: PendingNavigationConfirmation,
    onApprove: () -> Unit,
    onReject: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onReject,
        title = { Text(stringResource(R.string.confirm_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(UiDimens.SPACING_SMALL.dp)) {
                Text(stringResource(R.string.confirm_origin, pending.request.origin))
                Text(stringResource(R.string.confirm_path, pending.request.path))
                Text(stringResource(R.string.confirm_scope, pending.request.scope))
                // AD-110（审计 2026-09-23 清单·A6 批）：过期时刻
                // 用户可读格式化——Instant.toString() 输出
                // ISO-8601（2026-09-27T04:30:00Z），普通用户不可读。
                Text(
                    stringResource(
                        R.string.confirm_expires,
                        ExpiryFormat.format(pending.request.expiresAt),
                    ),
                )
            }
        },
        confirmButton = {
            TextButton(onClick = onApprove) { Text(stringResource(R.string.confirm_approve)) }
        },
        dismissButton = {
            TextButton(onClick = onReject) { Text(stringResource(R.string.confirm_reject)) }
        },
    )
}

/**
 * AD-331（2026-10-02 审计）：仅查询参数命中危险扩展的下载确认对话框——
 * 路径/文件名命中的硬拦截不进本面（WebViewDownloadHandler 直接 Toast）。
 * 批准即继续入队；关闭/取消即放弃（fail-closed）。
 */
@Suppress("FunctionNaming")
@Composable
internal fun DownloadConfirmationDialog(
    pending: PendingDownloadConfirmation,
    onApprove: () -> Unit,
    onReject: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onReject,
        title = { Text(stringResource(R.string.download_confirm_title)) },
        text = { Text(stringResource(R.string.download_confirm_message, pending.url)) },
        confirmButton = {
            TextButton(onClick = onApprove) { Text(stringResource(R.string.download_confirm_allow)) }
        },
        dismissButton = {
            TextButton(onClick = onReject) { Text(stringResource(R.string.confirm_reject)) }
        },
    )
}

/**
 * 阅读模式对话框（正文分段渲染——AD-226；对话框本体自 MainActivity 抽出）。
 */
@Suppress("FunctionNaming")
@Composable
internal fun ReaderDialog(
    content: ReaderContent,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        // AD-322（2026-10-02 审计）：标题空值兜底迁 UI 层资源单源——
        // ReaderMode 数据层不再硬编码中文标题（不可本地化）。
        title = { Text(content.title.ifBlank { stringResource(R.string.reader_mode_title) }) },
        text = {
            // AD-226（2026-09-26 审计）：正文分段渲染——原单个 Text 一次性
            // 测量至 200K 字符（ReaderMode.MAX_TEXT 上限），低端机测量/重组
            // 卡顿（ANR 面）。按 2K 字符分段 LazyColumn 只测量可视段。
            // AD-261（2026-10-01 审计）：分段按 UTF-16 char 切段可劈开代理对
            // （emoji/增补汉字在分段处渲染 �）——分段处复用码点边界回退
            // （见 chunkAtCharBoundary）。
            val chunks =
                remember(content.text) { chunkTextAtCharBoundary(content.text, READER_TEXT_CHUNK_SIZE) }
            LazyColumn(
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .heightIn(max = UiDimens.READER_DIALOG_MAX_HEIGHT.dp),
            ) {
                items(chunks) { chunk ->
                    Text(text = chunk, modifier = Modifier.fillMaxWidth())
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.dialog_close))
            }
        },
    )
}

/** AD-226：阅读对话框正文分段长度（原 MainActivity 私有常量随迁）。 */
internal const val READER_TEXT_CHUNK_SIZE = 2000

/**
 * AD-261（2026-10-01 审计）：分段边界代理对安全切分——String.chunked 按
 * UTF-16 char 计长，切点落在增补字符（emoji 等）的代理对中间会产生孤立
 * 代理（渲染 � 且 length 语义失真）。切点尾部为高代理时把该 char 让渡给
 * 后段（与 ReaderMode.takeAtCharBoundary 同口径——分段版）。ASCII 文本
 * 行为与 chunked 一致。
 */
internal fun chunkTextAtCharBoundary(
    text: String,
    chunkSize: Int,
): List<String> {
    val raw = text.chunked(chunkSize).toMutableList()
    // AD-300（P2，2026-10-02 审计）：原 `for (i in raw.indices - 1)` 语义错误
    // ——IntRange 无 minus(Int) 运算，实际命中 Iterable<Int>.minus（移除值为
    // 1 的元素）：分段 1 的边界代理对永不迁移，且末段（i=size-1）参与循环
    // 时 raw[i+1] 越界（末段恰以高代理结尾即 IndexOutOfBounds）。改为
    // 0 until raw.size - 1（除末段外逐段检查——末段无后继可让渡）。
    for (i in 0 until raw.size - 1) {
        val chunk = raw[i]
        if (chunk.isNotEmpty() && Character.isHighSurrogate(chunk.last())) {
            raw[i] = chunk.dropLast(1)
            raw[i + 1] = chunk.last() + raw[i + 1]
        }
    }
    return raw.toList()
}

/**
 * AD-151/183：对话框宿主——单槽状态机的组合挂载点（MainActivity 只收集
 * 状态并回调上抛，槽位裁决与渲染收敛在本文件）。
 *
 * @Suppress 与 AddressBarRow 同口径：状态/回调装配点参数多系设计使然。
 */
@Suppress("FunctionNaming", "LongParameterList")
@Composable
internal fun MainDialogHost(
    pendingConfirmation: PendingNavigationConfirmation?,
    pendingDownload: PendingDownloadConfirmation?,
    webViewAlert: WebViewAlertNotice?,
    readerContent: ReaderContent?,
    onApprove: () -> Unit,
    onReject: () -> Unit,
    onApproveDownload: () -> Unit,
    onRejectDownload: () -> Unit,
    onDismissAlert: () -> Unit,
    onGoUpdate: () -> Unit,
    onDismissReader: () -> Unit,
) {
    when (resolveActiveDialog(pendingConfirmation, pendingDownload, webViewAlert, readerContent)) {
        ActiveDialog.PENDING_CONFIRMATION -> {
            pendingConfirmation?.let { pending ->
                NavigationConfirmationDialog(
                    pending = pending,
                    onApprove = onApprove,
                    onReject = onReject,
                )
            }
        }

        ActiveDialog.DOWNLOAD_CONFIRMATION -> {
            // AD-331：二级（仅查询参数命中）下载确认——批准继续/拒绝放弃
            pendingDownload?.let { pending ->
                DownloadConfirmationDialog(
                    pending = pending,
                    onApprove = onApproveDownload,
                    onReject = onRejectDownload,
                )
            }
        }

        ActiveDialog.WEB_VIEW_ALERT -> {
            webViewAlert?.let { notice ->
                WebViewAlertDialog(
                    notice = notice,
                    onGoUpdate = onGoUpdate,
                    onDismiss = onDismissAlert,
                )
            }
        }

        ActiveDialog.READER_CONTENT -> {
            readerContent?.let { content ->
                ReaderDialog(
                    content = content,
                    onDismiss = onDismissReader,
                )
            }
        }

        null -> {
            Unit
        }
    }
}
