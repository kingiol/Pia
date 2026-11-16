from __future__ import annotations

import json
import re
from typing import Any


class ToolPermissionDenied(PermissionError):
    code = "TOOL_PERMISSION_DENIED"


AGENT_TOOL_PERMISSIONS: dict[str, set[str]] = {
    "Investment Chief": {
        "get_market_snapshot",
        "get_portfolio_snapshot",
        "get_task_trace",
        "create_research_task",
    },
    "Market Analyst": {
        "get_market_snapshot",
        "get_market_breadth",
        "get_index_series",
        "get_sector_strength",
    },
    "Sector Analyst": {"get_market_snapshot", "get_sector_strength"},
    "Stock Researcher": {
        "get_financial_statements",
        "get_company_profile",
        "search_filings",
        "search_news",
        "compare_instruments",
    },
    "Technical Analyst": {
        "get_market_snapshot",
        "get_price_volume_features",
        "get_index_series",
    },
    "Portfolio Analyst": {
        "get_portfolio_snapshot",
        "calculate_exposure",
        "simulate_position_change",
        "compare_instruments",
    },
    "News Analyst": {
        "search_filings",
        "search_news",
        "get_earnings_summary",
    },
    "Risk / Rules Agent": {
        "get_market_snapshot",
        "get_portfolio_snapshot",
        "check_rule_violations",
        "request_human_approval",
    },
    "Decision Agent": {
        "get_task_trace",
        "check_rule_violations",
        "request_human_approval",
        "schedule_follow_up",
    },
    "Research Manager": {
        "get_task_trace",
        "save_evidence",
        "request_human_approval",
        "schedule_follow_up",
    },
    "Bull Case Analyst": {"get_market_snapshot", "get_task_trace"},
    "Bear Case Analyst": {"get_market_snapshot", "get_portfolio_snapshot", "get_task_trace"},
    "Debate Chair": {"get_task_trace", "save_evidence"},
}


def assert_tool_allowed(agent_name: str, tool_name: str) -> None:
    allowed = AGENT_TOOL_PERMISSIONS.get(agent_name, set())
    if tool_name == "submit_order" or tool_name not in allowed:
        raise ToolPermissionDenied(
            f"{agent_name} is not allowed to call {tool_name}"
        )


def sanitize_external_text(value: Any) -> str:
    """Keep source text useful while making instruction-like content inert."""
    text = str(value or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    instruction_patterns = (
        r"ignore\s+(all|the)\s+previous\s+instructions?",
        r"system\s*prompt",
        r"developer\s+message",
        r"tool\s*call",
        r"submit\s+order",
        r"下单",
        r"忽略之前的指令",
        r"系统提示",
    )
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in instruction_patterns):
        return "[UNTRUSTED_EXTERNAL_TEXT] " + text
    return text


def redact_secrets(value: Any) -> Any:
    """Redact common credential keys before values reach logs or audit payloads."""
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _looks_secret(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, str):
        return re.sub(
            r"(?i)(bearer\s+|api[_-]?key\s*=\s*|token\s*=\s*)[A-Za-z0-9._~+/=-]+",
            r"\1[REDACTED]",
            value,
        )
    return value


def safe_json(value: Any) -> str:
    return json.dumps(redact_secrets(value), ensure_ascii=False, sort_keys=True)


def _looks_secret(key: str) -> bool:
    normalized = re.sub(r"[^a-z]", "", key.lower())
    return any(token in normalized for token in ("apikey", "token", "secret", "password", "authorization", "credential"))
