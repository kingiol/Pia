from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from .agent_contracts import GraphStateContract


class ResearchGraphState(TypedDict, total=False):
    task_id: str
    trigger_type: str
    as_of: str
    symbol: str | None
    market: dict[str, Any]
    portfolio: dict[str, Any]
    evidence_ids: list[str]
    research: dict[str, Any]
    outputs: dict[str, dict[str, Any]]


AgentRunner = Callable[
    [str, dict[str, Any], dict[str, Any], list[str]],
    dict[str, Any],
]


def build_research_graph(run_agent: AgentRunner):
    """Compile the deterministic orchestration graph used by local and cloud runtimes."""

    def invoke(state: ResearchGraphState, name: str, payload: dict[str, Any], output: dict[str, Any]) -> ResearchGraphState:
        result = run_agent(name, payload, output, list(state.get("evidence_ids", [])))
        outputs = dict(state.get("outputs", {}))
        outputs[name] = result
        return {"outputs": outputs}

    def chief(state: ResearchGraphState) -> ResearchGraphState:
        return invoke(
            state,
            "Investment Chief",
            {
                "trigger_type": state["trigger_type"],
                "as_of": state["as_of"],
                "target": {"symbol": state.get("symbol")},
            },
            {"plan": ["market_context", "portfolio_context", "risk_review"]},
        )

    def market(state: ResearchGraphState) -> ResearchGraphState:
        value = state["market"]
        return invoke(
            state,
            "Market Analyst",
            value,
            {
                "breadth": value["breadth"],
                "index_trend": value["index_trend"],
                "volatility": value["volatility"],
            },
        )

    def sector(state: ResearchGraphState) -> ResearchGraphState:
        value = state["market"]
        return invoke(
            state,
            "Sector Analyst",
            {"sectors": value.get("sectors", []), "market_snapshot_id": value["snapshot_id"]},
            {
                "leaders": sorted(
                    value.get("sectors", []),
                    key=lambda item: float(item.get("change_pct", 0)),
                    reverse=True,
                )[:3],
                "evidence_ids": list(state.get("evidence_ids", [])),
            },
        )

    def portfolio(state: ResearchGraphState) -> ResearchGraphState:
        value = state["portfolio"]
        return invoke(
            state,
            "Portfolio Analyst",
            value,
            {
                "total_value": value["total_value"],
                "drawdown": value["drawdown"],
                "exposure": [position["weight"] for position in value["positions"]],
            },
        )

    def technical(state: ResearchGraphState) -> ResearchGraphState:
        value = state["market"]
        return invoke(
            state,
            "Technical Analyst",
            value,
            {"trend": value["index_trend"], "leaders": value.get("sectors", [])[:2]},
        )

    def stock(state: ResearchGraphState) -> ResearchGraphState:
        research = state.get("research", {})
        profile = research.get("company_profile", {})
        evidence_ids = list(state.get("evidence_ids", []))
        return invoke(
            state,
            "Stock Researcher",
            {
                "symbol": state["symbol"],
                "market_snapshot_id": state["market"]["snapshot_id"],
                "evidence_ids": evidence_ids,
            },
            {
                "symbol": state["symbol"],
                "company": profile.get("name", state["symbol"]),
                "industry": profile.get("industry", "unknown"),
                "facts": [item["excerpt"] for item in research.get("filings", [])],
                "evidence_ids": evidence_ids,
            },
        )

    def news(state: ResearchGraphState) -> ResearchGraphState:
        research = state.get("research", {})
        evidence_ids = list(state.get("evidence_ids", []))
        return invoke(
            state,
            "News Analyst",
            {"symbol": state["symbol"], "evidence_ids": evidence_ids},
            {
                "news_count": len(research.get("news", [])),
                "filing_count": len(research.get("filings", [])),
                "evidence_ids": evidence_ids,
                "unresolved_questions": ["Will the next filing confirm the current risk trend?"],
            },
        )

    def bull(state: ResearchGraphState) -> ResearchGraphState:
        market = state["market"]
        evidence_ids = list(state.get("evidence_ids", []))
        return invoke(
            state,
            "Bull Case Analyst",
            {"market_snapshot_id": market["snapshot_id"], "evidence_ids": evidence_ids},
            {
                "stance": "bull",
                "points": [
                    f"Market breadth is {market['breadth']:.0%}.",
                    f"Index trend is {market['index_trend']}.",
                ],
                "evidence_ids": evidence_ids[:2],
                "unresolved_questions": ["Can breadth persist over the next session?"],
            },
        )

    def bear(state: ResearchGraphState) -> ResearchGraphState:
        portfolio_value = state["portfolio"]
        evidence_ids = list(state.get("evidence_ids", []))
        return invoke(
            state,
            "Bear Case Analyst",
            {"market_snapshot_id": state["market"]["snapshot_id"], "evidence_ids": evidence_ids},
            {
                "stance": "bear",
                "points": [
                    f"Portfolio drawdown is {portfolio_value['drawdown']:.1%}.",
                    "Position concentration can amplify downside risk.",
                ],
                "evidence_ids": [evidence_ids[-1]] if evidence_ids else [],
                "unresolved_questions": ["Will concentration remain above the configured limit?"],
            },
        )

    def debate(state: ResearchGraphState) -> ResearchGraphState:
        return invoke(
            state,
            "Debate Chair",
            {
                "bull_agent": "Bull Case Analyst",
                "bear_agent": "Bear Case Analyst",
            },
            {
                "verdict": "Risk gates take precedence until concentration and market conditions are resolved.",
                "unresolved_questions": [
                    "Whether the next market snapshot confirms the current trend.",
                    "Whether portfolio weights return below the configured limits.",
                ],
            },
        )

    def research_manager(state: ResearchGraphState) -> ResearchGraphState:
        outputs = state.get("outputs", {})
        bull = outputs.get("Bull Case Analyst", {})
        bear = outputs.get("Bear Case Analyst", {})
        unresolved = [
            *bull.get("unresolved_questions", []),
            *bear.get("unresolved_questions", []),
        ]
        return invoke(
            state,
            "Research Manager",
            {
                "market_snapshot_id": state["market"]["snapshot_id"],
                "evidence_ids": list(state.get("evidence_ids", [])),
            },
            {
                "summary": "Deterministic evidence summary prepared for Rules and Risk Review.",
                "bull_points": list(bull.get("points", [])),
                "bear_points": list(bear.get("points", [])),
                "unresolved_questions": unresolved,
                "evidence_ids": list(state.get("evidence_ids", [])),
            },
        )

    def route_research(state: ResearchGraphState) -> str:
        return "research" if state.get("symbol") else "bull"

    builder = StateGraph(ResearchGraphState)
    builder.add_node("chief", chief)
    builder.add_node("market", market)
    builder.add_node("sector", sector)
    builder.add_node("portfolio", portfolio)
    builder.add_node("technical", technical)
    builder.add_node("stock", stock)
    builder.add_node("news", news)
    builder.add_node("bull", bull)
    builder.add_node("bear", bear)
    builder.add_node("debate", debate)
    builder.add_node("research_manager", research_manager)
    builder.add_edge(START, "chief")
    builder.add_edge("chief", "market")
    builder.add_edge("market", "sector")
    builder.add_edge("sector", "portfolio")
    builder.add_edge("portfolio", "technical")
    builder.add_conditional_edges("technical", route_research, {"research": "stock", "bull": "bull"})
    builder.add_edge("stock", "news")
    builder.add_edge("news", "bull")
    builder.add_edge("bull", "bear")
    builder.add_edge("bear", "debate")
    builder.add_edge("debate", "research_manager")
    builder.add_edge("research_manager", END)
    return builder.compile()


def validate_graph_state(state: dict[str, Any]) -> dict[str, Any]:
    return GraphStateContract.model_validate(state).model_dump()
