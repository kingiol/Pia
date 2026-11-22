import Foundation
import PiaMobileClient

func researchErrorMessage(_ error: Error, fallback: String) -> String {
    if let apiError = error as? PiaAPIError, case .http(let status, _) = apiError {
        if status == 401 { return "访问令牌无效或已过期，请重新连接。" }
        if status == 403 { return "当前账号没有执行此操作的权限。" }
    }
    if error is URLError { return "无法连接研究服务，请检查网络后重试。" }
    return fallback
}

func researchAgentLabel(_ name: String?) -> String {
    switch name {
    case "Investment Chief": "研究统筹"
    case "Market Analyst": "市场分析"
    case "Sector Analyst": "板块分析"
    case "Portfolio Analyst": "持仓分析"
    case "Technical Analyst": "技术分析"
    case "Stock Researcher": "个股研究"
    case "News Analyst": "新闻与公告分析"
    case "Bull Case Analyst": "看多分析"
    case "Bear Case Analyst": "看空分析"
    case "Debate Chair": "多空观点汇总"
    case "Research Manager": "研究汇总"
    case "Risk / Rules Agent": "风险与规则审核"
    case "Decision Agent": "决策汇总"
    case "LLM Research Manager": "模型补充研究"
    default: name ?? "分析步骤"
    }
}

extension ResearchTask {
    var researchSymbol: String? {
        guard case .string(let symbol) = target?["symbol"] else { return nil }
        let value = symbol.trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? nil : value
    }

    var researchDate: String {
        guard case .string(let value) = target?["as_of"] else { return "—" }
        return value
    }

    var researchTitle: String {
        if triggerType == "MarketClose" { return "收盘市场复盘" }
        return researchSymbol.map { "\($0) 研究" } ?? triggerType
    }

    var createdDisplay: String {
        guard let date = parseResearchTimestamp(createdAt) else { return "—" }
        return date.formatted(.dateTime.month(.twoDigits).day(.twoDigits).hour().minute().second())
    }
}

func parseResearchTimestamp(_ value: String?) -> Date? {
    guard let value else { return nil }
    return (try? Date.ISO8601FormatStyle(includingFractionalSeconds: true).parse(value))
        ?? (try? Date.ISO8601FormatStyle().parse(value))
}

func researchLevel(_ value: String) -> String {
    ["low": "低", "medium": "中", "high": "高"][value] ?? value
}

func researchNextAction(_ value: String) -> String {
    value == "Review evidence and unresolved research limitations."
        ? "核对证据与尚未解决的研究限制。" : value
}

func researchEvidenceQuality(_ evidence: Evidence) -> String {
    if let expiry = parseResearchTimestamp(evidence.expiresAt), expiry <= Date() { return "已过期" }
    return ["verified": "已验证", "partial": "部分验证", "stale": "已过期", "unavailable": "不可用"][evidence.quality]
        ?? evidence.quality
}

struct ResearchRule {
    let title: String
    let comparison: String
    let isBlocking: Bool

    init(_ fields: [String: JSONValue], isBlocking: Bool) {
        self.isBlocking = isBlocking
        let ruleID = Self.text(fields["rule_id"]) ?? ""
        let code = Self.text(fields["code"]) ?? ""
        let message = Self.text(fields["message"]) ?? "规则未通过"
        if let range = ruleID.range(of: "portfolio.position."), range.lowerBound == ruleID.startIndex {
            title = "\(ruleID[range.upperBound...]) 仓位超限"
        } else if let range = ruleID.range(of: "portfolio.sector."), range.lowerBound == ruleID.startIndex {
            title = "\(ruleID[range.upperBound...]) 行业仓位超限"
        } else {
            title = [
                "STALE_DATA": "行情快照已过期", "DATA_UNAVAILABLE": "行情快照未通过验证",
                "DRAWDOWN_LIMIT": "组合回撤触及限制", "DRAWDOWN_WARNING": "组合回撤触及预警阈值",
                "RISK_REVIEW_FAILED": "组合回撤触及严重阈值", "EVIDENCE_INSUFFICIENT": "证据条数不足",
                "MARKET_VOLATILITY_FAILED": "市场波动率超过阈值",
                "MARKET_CONDITION_FAILED": ruleID == "market.breadth" ? "市场宽度低于阈值" : "指数趋势未满足规则",
            ][code] ?? message
        }
        let ratio = ruleID.hasPrefix("portfolio.position.") || ruleID.hasPrefix("portfolio.sector.")
            || ruleID.hasPrefix("portfolio.drawdown.") || ["market.breadth", "market.volatility"].contains(ruleID)
        let expected = Self.text(fields["expected"]) ?? "—"
        let parts = expected.split(separator: " ", maxSplits: 1)
        var actual = Self.text(fields["actual"]) ?? "—"
        var limit = expected
        if ratio, case .number(let value) = fields["actual"] {
            actual = value.formatted(.percent.precision(.fractionLength(0...2)))
            if parts.count == 2, let threshold = Double(parts[1]) {
                limit = "\(parts[0]) \(threshold.formatted(.percent.precision(.fractionLength(0...2))))"
            }
        }
        limit = limit.replacingOccurrences(of: "<=", with: "≤").replacingOccurrences(of: ">=", with: "≥")
        comparison = "实际 \(actual) · 要求 \(limit)"
    }

    private static func text(_ value: JSONValue?) -> String? {
        switch value {
        case .string(let string): return string
        case .number(let number): return number.formatted()
        default: return nil
        }
    }

    static func from(_ decision: [String: JSONValue]?) -> [ResearchRule] {
        guard case .object(let rationale) = decision?["rationale"],
              case .object(let result) = rationale["rules"] else { return [] }
        return ["reasons", "warnings"].flatMap { key -> [ResearchRule] in
            guard case .array(let values) = result[key] else { return [] }
            return values.compactMap { value in
                guard case .object(let fields) = value else { return nil }
                return ResearchRule(fields, isBlocking: key == "reasons")
            }
        }
    }
}
