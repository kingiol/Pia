package com.pia.mobile

import java.text.NumberFormat
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import org.json.JSONObject

internal fun JSONObject.text(key: String): String? =
    optString(key).takeIf { it.isNotBlank() && it != "null" }

internal fun JSONObject.symbol(): String? =
    (opt("symbol") as? String)?.trim()?.takeIf { it.isNotEmpty() }

internal val PiaTask.title: String
    get() = if (triggerType == "MarketClose") "收盘市场复盘" else symbol?.let { "$it 研究" } ?: triggerType

internal fun createdDisplay(timestamp: String): String =
    parseResearchTimestamp(timestamp)?.atZone(ZoneId.systemDefault())
        ?.format(DateTimeFormatter.ofPattern("MM-dd HH:mm:ss")) ?: "—"

private fun parseResearchTimestamp(timestamp: String): Instant? =
    runCatching { OffsetDateTime.parse(timestamp).toInstant() }.getOrNull()

internal fun researchNextAction(value: String): String =
    if (value == "Review evidence and unresolved research limitations.") "核对证据与尚未解决的研究限制。" else value

internal fun researchLevel(value: String): String = when (value) {
    "low" -> "低"
    "medium" -> "中"
    "high" -> "高"
    else -> value
}

internal fun evidenceQuality(evidence: JSONObject): String {
    val expiry = evidence.text("expires_at")?.let(::parseResearchTimestamp)
    if (expiry != null && expiry <= Instant.now()) return "已过期"
    return when (val quality = evidence.text("quality")) {
        "verified" -> "已验证"
        "partial" -> "部分验证"
        "stale" -> "已过期"
        "unavailable" -> "不可用"
        else -> quality ?: "未知"
    }
}

internal data class ResearchRule(val title: String, val comparison: String, val isBlocking: Boolean)

internal fun researchRules(decision: JSONObject?): List<ResearchRule> {
    val result = decision?.optJSONObject("rationale")?.optJSONObject("rules") ?: return emptyList()
    return buildList {
        for (key in listOf("reasons", "warnings")) {
            val rows = result.optJSONArray(key) ?: continue
            for (index in 0 until rows.length()) {
                val row = rows.optJSONObject(index) ?: continue
                add(researchRule(row, isBlocking = key == "reasons"))
            }
        }
    }
}

private fun researchRule(row: JSONObject, isBlocking: Boolean): ResearchRule {
    val id = row.text("rule_id").orEmpty()
    val title = when {
        id.startsWith("portfolio.position.") -> "${id.removePrefix("portfolio.position.")} 仓位超限"
        id.startsWith("portfolio.sector.") -> "${id.removePrefix("portfolio.sector.")} 行业仓位超限"
        else -> when (row.text("code")) {
            "STALE_DATA" -> "行情快照已过期"
            "DATA_UNAVAILABLE" -> "行情快照未通过验证"
            "DRAWDOWN_LIMIT" -> "组合回撤触及限制"
            "DRAWDOWN_WARNING" -> "组合回撤触及预警阈值"
            "RISK_REVIEW_FAILED" -> "组合回撤触及严重阈值"
            "EVIDENCE_INSUFFICIENT" -> "证据条数不足"
            "MARKET_VOLATILITY_FAILED" -> "市场波动率超过阈值"
            "MARKET_CONDITION_FAILED" -> if (id == "market.breadth") "市场宽度低于阈值" else "指数趋势未满足规则"
            else -> row.text("message") ?: "规则未通过"
        }
    }
    val ratio = id.startsWith("portfolio.position.") || id.startsWith("portfolio.sector.") ||
        id.startsWith("portfolio.drawdown.") || id in setOf("market.breadth", "market.volatility")
    var actual = row.text("actual") ?: "—"
    var limit = row.text("expected") ?: "—"
    val number = row.opt("actual") as? Number
    if (ratio && number != null) {
        val percent = NumberFormat.getPercentInstance().apply { maximumFractionDigits = 2 }
        actual = percent.format(number)
        val parts = limit.split(" ", limit = 2)
        parts.getOrNull(1)?.toDoubleOrNull()?.let { limit = "${parts[0]} ${percent.format(it)}" }
    }
    limit = limit.replace("<=", "≤").replace(">=", "≥")
    return ResearchRule(title, "实际 $actual · 要求 $limit", isBlocking)
}

internal fun taskActions(
    status: String,
    eligible: Boolean = false,
    hasSymbol: Boolean = false,
): List<Pair<String, String>> = when (status) {
    "WAITING_APPROVAL" -> buildList {
        if (eligible) add("接受建议" to "APPROVE")
        add("暂不行动" to "NO_ACTION")
        add("继续研究" to "REQUEST_MORE_RESEARCH")
        if (hasSymbol) add("加入关注" to "MARK_AS_WATCH")
        add("拒绝建议" to "REJECT")
    }
    "QUEUED" -> listOf("取消" to "CANCEL")
    "PAUSED" -> listOf("继续运行" to "RESUME", "取消" to "CANCEL")
    "PLANNING", "RUNNING", "REVIEWING" -> listOf("暂停" to "PAUSE", "取消" to "CANCEL")
    "RETRYABLE", "FAILED", "TIMEOUT" -> listOf("人工接管" to "TAKEOVER", "重试" to "RETRY")
    else -> emptyList()
}
