from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .decision_context import content_hash, validate_pack
from .models import Decision, DecisionStatus, RuleResult


class AgentOpinion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    opinion_id: str
    source_opinion_id: str | None = None
    agent_name: str
    pack_id: str
    subject: str | None
    claim_key: str
    dimension: Literal["market", "portfolio", "technical", "fundamentals", "sources", "risk"]
    stance: Literal["support", "oppose", "neutral"]
    evidence_ids: list[str]
    rationale: str
    origin: Literal["computed", "llm", "fixture", "stub"]
    limitations: list[str] = Field(default_factory=list)


def graph_opinions(pack: dict, outputs: dict[str, dict]) -> list[dict]:
    dimensions = {
        "Market Analyst": "market", "Portfolio Analyst": "portfolio",
        "Technical Analyst": "technical", "Stock Researcher": "fundamentals",
        "News Analyst": "sources", "Risk / Rules Agent": "risk",
    }
    opinions = []
    for name, output in sorted(outputs.items()):
        if name == "LLM Research Manager":
            for index, raw in enumerate(output.get("opinions", []) if isinstance(output.get("opinions"), list) else []):
                if not isinstance(raw, dict):
                    continue
                opinions.append({
                    **raw, "schema_version": "1",
                    "opinion_id": "opinion_" + content_hash([pack["content_hash"], name, index, raw])[:24],
                    "agent_name": name, "pack_id": pack["pack_id"], "subject": pack["subject"], "origin": "llm",
                })
            continue
        dimension = dimensions.get(name)
        if dimension is None:
            continue
        source_type = {"market": {"market"}, "portfolio": {"portfolio"},
                       "sources": {"news", "filing"}, "fundamentals": {"company"}}.get(dimension)
        ids = [item["id"] for item in pack["evidence"]
               if source_type is None or item.get("source_type") in source_type]
        origin = "fixture" if pack["data_mode"] == "fixture" else (
            "computed" if dimension in {"market", "portfolio", "risk"} else "stub"
        )
        opinions.append(AgentOpinion(
            opinion_id="opinion_" + content_hash([pack["content_hash"], name])[:24],
            agent_name=name, pack_id=pack["pack_id"], subject=pack["subject"],
            claim_key=f"{dimension}.observation", dimension=dimension, stance="neutral",
            evidence_ids=ids, rationale=f"{name} observations recorded in task trace.",
            origin=origin, limitations=list(output.get("unresolved_questions", [])),
        ).model_dump())
    return opinions


def evidence_rejection(pack: dict, row: dict) -> str | None:
    if row.get("task_id") not in {None, pack["task_id"]} and pack["execution_mode"] != "replay":
        return "EVIDENCE_TASK_MISMATCH"
    if row.get("subject") not in {None, pack["subject"]}:
        return "EVIDENCE_SUBJECT_MISMATCH"
    evaluation = datetime.fromisoformat(f"{pack['analysis_as_of']}T16:00:00+08:00")
    try:
        if str(row["as_of"])[:10] > pack["analysis_as_of"]:
            return "EVIDENCE_IN_FUTURE"
        if row.get("expires_at") and datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")) < evaluation:
            return "EVIDENCE_EXPIRED"
        published = row.get("published_at") or (row.get("observed_at") if row.get("source_type") in {"news", "filing"} else None)
        if published and datetime.fromisoformat(published.replace("Z", "+00:00")) > evaluation:
            return "EVIDENCE_IN_FUTURE"
        datetime.fromisoformat(str(row["as_of"]))
    except (KeyError, TypeError, ValueError):
        return "EVIDENCE_TIME_INVALID"
    if row.get("quality") != "verified":
        return "EVIDENCE_QUALITY_INSUFFICIENT"
    return None


def valid_evidence_ids(pack: dict) -> list[str]:
    return sorted({row["id"] for row in pack["evidence"] if evidence_rejection(pack, row) is None})


def synthesize(pack: dict, opinions: list[dict], rules: RuleResult) -> Decision:
    pack = validate_pack(pack)
    evidence = {row["id"]: row for row in pack["evidence"]}
    valid, rejected = [], []
    groups: set[tuple] = set()
    dimensions: set[str] = set()
    for raw in sorted(opinions, key=lambda item: str(item.get("opinion_id", ""))):
        reason = None
        try:
            opinion = AgentOpinion.model_validate(raw)
        except ValidationError:
            rejected.append({"opinion_id": str(raw.get("opinion_id", "")), "reason_code": "OPINION_SCHEMA_INVALID"})
            continue
        if opinion.pack_id != pack["pack_id"] or opinion.subject != pack["subject"]:
            reason = "OPINION_CONTEXT_MISMATCH"
        elif not opinion.evidence_ids:
            reason = "OPINION_EVIDENCE_MISSING"
        for evidence_id in opinion.evidence_ids:
            row = evidence.get(evidence_id)
            if row is None:
                reason = "EVIDENCE_NOT_IN_PACK"
                break
            rejection = evidence_rejection(pack, row)
            if rejection:
                reason = rejection
                break
        if reason:
            rejected.append({"opinion_id": opinion.opinion_id, "reason_code": reason})
            continue
        valid.append(opinion)
        if opinion.origin in {"computed", "llm"}:
            dimensions.add(opinion.dimension)
            for evidence_id in opinion.evidence_ids:
                row = evidence[evidence_id]
                groups.add((row.get("provider_id") or row.get("source"),
                            row.get("snapshot_id") or row.get("content_hash")))
    claims: dict[str, set[str]] = {}
    for opinion in valid:
        claims.setdefault(opinion.claim_key, set()).add(opinion.stance)
    conflicts = sorted(key for key, stances in claims.items() if {"support", "oppose"} <= stances)
    required = {"market", "portfolio", "risk"}
    if pack["subject"]:
        required.add("technical")
    if pack["blocks"]["sources"]["required"]:
        required.add("sources")
    missing = sorted(required - dimensions)
    unavailable = sorted(name for name, block in pack["blocks"].items()
                         if block["required"] and block["status"] in {"unavailable", "stale"})
    status = DecisionStatus.WATCH
    if rules.decision in {"BLOCKED", "NO_ACTION"}:
        status = DecisionStatus(rules.decision)
    elif unavailable:
        status = DecisionStatus.BLOCKED
    confidence_reasons = []
    if missing:
        confidence_reasons.append("REQUIRED_DIMENSIONS_MISSING")
    if conflicts:
        confidence_reasons.append("OPINION_CONFLICT")
    if rejected:
        confidence_reasons.append("OPINIONS_REJECTED")
    if unavailable:
        confidence_reasons.append("REQUIRED_CONTEXT_UNAVAILABLE")
    medium = not (missing or conflicts or rejected or unavailable or rules.warnings) and len(groups) >= 2
    return Decision(
        status=status, confidence="medium" if medium else "low",
        risk_level="high" if status == DecisionStatus.BLOCKED else "medium",
        rationale=[reason.message for reason in [*rules.reasons, *rules.warnings]]
                  + [opinion.rationale for opinion in valid]
                  + ([f"Research coverage missing: {', '.join(missing)}."] if missing else []),
        next_action="Review evidence and unresolved research limitations.",
        invalidation=["New market snapshot", "Ruleset version change", "Evidence expiry"],
        rule_result=rules,
        synthesis={
            "synthesizer_version": "1", "pack_id": pack["pack_id"],
            "valid_opinion_ids": [opinion.opinion_id for opinion in valid],
            "rejected_opinions": rejected, "conflicts": conflicts,
            "confidence_reasons": confidence_reasons, "missing_dimensions": missing,
            "evidence_group_count": len(groups), "opinions": [item.model_dump() for item in valid],
        },
    )
