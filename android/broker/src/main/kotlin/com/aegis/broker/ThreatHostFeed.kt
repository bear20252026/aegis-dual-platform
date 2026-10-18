package com.aegis.broker

import java.util.Locale

/**
 * 威胁 host 名单的文本解析与分批（R9-B95 / 第九轮，队列 Q51 的机制半边）。
 *
 * 为什么要这份文件：核心的黑名单注入入口
 * `aegis_policy_core_broker_update_host_denylist_json`（v4 起第三参是档位）此前在
 * Android **从未被声明**——`android/` 全树对 `ThreatFeed|denylist|blocklist` 零命中，
 * 于是「Android 整条取源→校验→灌核心的链不存在」这件事（§五 Q51 / §4.0 表 D3）
 * 不是「有链但名单为空」，而是**连灌入口都没有**。本批落机制，名单内容归用户。
 *
 * 解析口径与 Windows
 * `windows/src/Aegis.Windows.App/Core/Security/ThreatFeed.cs` 的 `ParseFeedLine`
 * （= legacy `legacy/windows-pywebview/app/threat_feed.py` 的 `parse_feed_line`）逐条
 * 同形，理由不是审美：同一份订阅源文本必须在三端解析出同一集合，否则「两端行为一致」
 * 这句验收口径无从谈起。三处实现（Py/C#/Kotlin）至今**没有共享向量**——这条缺口按
 * Q71 登记在台账，本批不顺手扩向量面（新文件要同改 CONSUMER_MANIFEST、份数下界与
 * README 抄数，属独立一题）。
 *
 * 公开而非 internal：`:app` 侧的内置名单装载器要用它解析 asset 文本，而 Kotlin 的
 * internal 不跨模块——解析口径因此只有一份（在 :broker 里），不在 app 侧重写一遍。
 *
 * 分批的硬需求同 Windows R7-RS-02：核心 `read_utf8` 对单批载荷有 64 KiB 上限，
 * 而托管侧订阅源允许 5 MiB ⇒ 不切批就必然注入失败，且失败形态是「核心拒这一批」
 * 而不是「名单没生效」——不切批就等于假装成功。
 */
object ThreatHostFeed {
    /** 与核心 `denylist::MAX_ENTRY_BYTES` 同值（由 AbiSurfaceAlignmentTest 跨语言对账）。 */
    const val MAX_ENTRY_BYTES = 256

    /** 与核心 `denylist::MAX_BATCH_BYTES` / C ABI `FFI_INPUT_MAX_BYTES` 同值。 */
    const val MAX_BATCH_BYTES = 64 * 1024

    /**
     * 单批 host 载荷预算：比核心上限少 4 KiB，留给数组括号、引号与逗号。
     * 与 Windows `MaxChunkPayloadBytes` 同值——宁可多切一刀，也不能让任何一批撞上限
     *（撞上的那一批是被**拒绝**，不是被截断）。
     */
    const val CHUNK_PAYLOAD_BYTES = 60 * 1024

    /** 内置名单文件的 asset 路径（单源在此，app 侧与锚点用例都读这一个常量）。 */
    const val BUILT_IN_ASSET_PATH = "threat/hosts.txt"

    /** 解析结果：`hosts` 已去重、已按字典序排（可复现——同一输入永远同一批次划分）。 */
    data class Parsed(
        val hosts: List<String>,
        val rejected: List<String>,
    )

    /**
     * 一行订阅源文本 → 规范 host；返回 null 表示「不是条目」或「条目形态非法」。
     * 分支顺序与 C# 版逐条对应（`!`/`#` 注释、`||` 前缀、`^` 后缀、协议、路径、
     * 端口、大小写、必须含点或 localhost、字符白名单）。
     *
     * **一处有意的不一致**：`../etc` 这类形态 C# 版剥完路径会得到 `..` 并**放行**
     * （`ThreatFeed.cs:ParseFeedLine` 没有空段那一刀），而这里当场拒收。有效集合因此
     * 相同——核心 `entry_shape_ok` 两侧同判，Windows 那条会以 `accepted<input`
     * 的部分接受形态露出来——但 Android 把它挪到端侧计成「被拒条目数」，
     * 因为本端装载是内置文件，提前露出比推给核心再报部分接受更可解释。
     * 三端解析器无共享向量（缺口按 Q71 登记在册），这类漂移今天靠注释，不靠判据。
     */
    fun parseLine(rawLine: String): String? {
        val trimmed = rawLine.trim()
        if (trimmed.isEmpty() || trimmed.startsWith("!") || trimmed.startsWith("#")) {
            return null
        }
        val host = stripDecorations(trimmed)
        return if (candidateIsAHost(host)) host else null
    }

    /** 一条候选 host 的验收：非空，且「localhost」或「含点 + 形态合法」——C# 版的最后三刀。 */
    private fun candidateIsAHost(host: String): Boolean =
        host.isNotEmpty() && (host == LOCALHOST || (host.contains('.') && entryShapeOk(host)))

    /**
     * 按 C# 版的顺序剥装饰：`||` 前缀 → 尾部 `^` → 协议 → 路径 → 大小写 → 再剥尾 `^` → 端口。
     * 顺序本身有语义（先剥协议才会露出路径分隔符），所以这里保持与
     * `ThreatFeed.cs:ParseFeedLine` 逐行同序，不做"等价重排"。
     */
    private fun stripDecorations(input: String): String {
        var text = input
        if (text.startsWith(ADBLOCK_PREFIX)) {
            text = text.substring(ADBLOCK_PREFIX.length)
        }
        text = text.trimEnd('^')
        val schemeEnd = text.indexOf("://")
        if (schemeEnd >= 0) {
            text = text.substring(schemeEnd + SCHEME_MARKER_LENGTH)
        }
        val slash = text.indexOf('/')
        if (slash >= 0) {
            text = text.substring(0, slash)
        }
        text = text.trim().trimEnd('^').lowercase()
        val colon = text.indexOf(':')
        if (colon >= 0) {
            text = text.substring(0, colon)
        }
        return text
    }

    /**
     * 核心侧 `entry_shape_ok` 的同口径形态检（长度 + 字符白名单 + 首尾点 + 空段）。
     * 越界的 host 永远不会等于任何被规范化的导航 host，收下即制造「已登记但永不生效」
     * 的死条目——比不登记更坏，因为名单看起来是工作的。
     */
    fun entryShapeOk(host: String): Boolean =
        host.isNotEmpty() &&
            host.length <= MAX_ENTRY_BYTES &&
            !host.startsWith('.') &&
            !host.endsWith('.') &&
            !host.contains("..") &&
            host.all(::isHostChar)

    /**
     * 与核心 `entry_shape_ok` 的 `is_ascii_alphanumeric() || '.' || '-'` 逐字对应的单字判定。
     *
     * 为什么不复用 `OriginPolicy.isAllowedHostChar`：那个谓词是**导航 host** 的口径
     * （只收小写、`c.isDigit()` 含非 ASCII 数字、还要排除内嵌 IPv4 的 alternate 形态），
     * 而名单条目的验收权在核心——照抄导航谓词会造出「Android 拒收、核心其实收下」的
     * 第二类漂移。两处各有判据，混用只会同时失去两边的可比性。
     */
    private fun isHostChar(c: Char): Boolean = c in 'a'..'z' || c in 'A'..'Z' || c in '0'..'9' || c == '.' || c == '-'

    /** 整份文本 → 去重排序的 host 清单 + 被拒条目。
     *
     * 「被拒」只统计**看起来是条目却不合法**的行（注释与空行不算）：这个数必须进留痕，
     * 否则一份满是坏条目的源会解析成「0 条、成功」——那正是本仓反复记的
     * 「读起来像工作，实际什么都没拦」。
     */
    fun parse(text: String): Parsed {
        val accepted = linkedSetOf<String>()
        val rejected = mutableListOf<String>()
        for (line in text.lineSequence()) {
            val trimmed = line.trim()
            if (trimmed.isEmpty() || trimmed.startsWith("#") || trimmed.startsWith("!")) {
                continue
            }
            val host = parseLine(trimmed)
            if (host == null) {
                rejected.add(trimmed)
            } else {
                accepted.add(host)
            }
        }
        return Parsed(accepted.sorted(), rejected)
    }

    /**
     * 按字节预算切批。计费用 [quote]——与 [encode] 产出载荷的**同一个**函数，所以
     * "估算"与实际发出的字节逐字节同形（按 char 数计费会低估非 ASCII 与转义，那正好
     * 是让某一批撞上限的算错方向；撞上限的那一批是被核心**整批拒收**，不是被截断）。
     *
     * 空清单**也要出一批**（一个空载荷）：`drive` 因此发一次整批替换，核心回
     * `Published(0/0)`——「链跑过、名单为空」。返回空列表会让这轮变成
     * `NotPublished(denylist_no_batch)`，把「出厂就是空名单」错报成「链断了」。
     */
    fun batches(hosts: List<String>): List<List<String>> {
        if (hosts.isEmpty()) {
            return listOf(emptyList())
        }
        val out = mutableListOf<List<String>>()
        var current = mutableListOf<String>()
        var bytes = BRACKETS_BYTES
        for (host in hosts) {
            val cost = jsonEntryBytes(host)
            if (current.isNotEmpty() && bytes + cost > CHUNK_PAYLOAD_BYTES) {
                out.add(current.toList())
                current = mutableListOf()
                bytes = BRACKETS_BYTES
            }
            current.add(host)
            bytes += cost
        }
        if (current.isNotEmpty()) {
            out.add(current.toList())
        }
        return out
    }

    /**
     * 一批 host 的 JSON 数组载荷（核心按 `Vec<String>` 反序列化；**非良构即整批被拒**，
     * 所以这里必须做转义：`batches`/`encode` 是公开面，`AndroidBroker.updateThreatHostDenylist`
     * 的调用方可以不经 [parse] 直接递任意字符串——不转义时一个带引号的 host 就会把
     * 同批的合法条目全带走）。空批产出 `[]`：提交批与「清空名单」都靠它，
     * 而 `joinToString` 带前后缀时空集合会产出 `[""]`，那会被核心当成「一条空 host」。
     */
    fun encode(batch: List<String>): String =
        buildString {
            append('[')
            batch.forEachIndexed { index, host ->
                if (index > 0) {
                    append(',')
                }
                append(quote(host))
            }
            append(']')
        }

    /** 一条 host 上线时的 JSON 字面量字节数（含引号与分隔逗号）。 */
    private fun jsonEntryBytes(host: String): Int = quote(host).toByteArray(Charsets.UTF_8).size + COMMA_BYTES

    /** JSON 字符串字面量：转义引号、反斜杠与控制字符，其余原样（含非 ASCII → UTF-8 多字节）。 */
    private fun quote(value: String): String {
        val out = StringBuilder(value.length + 2)
        out.append('"')
        for (c in value) {
            when {
                c == '"' -> out.append("\\\"")
                c == '\\' -> out.append("\\\\")
                c == '\n' -> out.append("\\n")
                c == '\r' -> out.append("\\r")
                c == '\t' -> out.append("\\t")
                c < ' ' -> out.append("\\u").append(String.format(Locale.ROOT, "%04x", c.code))
                else -> out.append(c)
            }
        }
        return out.append('"').toString()
    }

    private const val LOCALHOST = "localhost"
    private const val ADBLOCK_PREFIX = "||"

    private const val SCHEME_MARKER_LENGTH = 3
    private const val BRACKETS_BYTES = 2
    private const val COMMA_BYTES = 1
}
