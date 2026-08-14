package com.aegis.browser

import android.net.Uri

object DownloadPolicy {
    private val dangerousExtensions =
        setOf(
            "exe",
            "bat",
            "cmd",
            "com",
            "msi",
            "scr",
            "pif",
            "vbs",
            "vbe",
            "js",
            "jse",
            "wsf",
            "wsh",
            "ps1",
            "psm1",
            "lnk",
            "hta",
            "jar",
            "apk",
            "dll",
            "reg",
            "cpl",
            "appref-ms",
        )

    fun requiresExplicitConfirmation(url: String): Boolean {
        val extension =
            Uri
                .parse(url)
                .lastPathSegment
                ?.substringAfterLast('.', missingDelimiterValue = "")
                ?.lowercase()
                .orEmpty()
        return extension in dangerousExtensions
    }
}
