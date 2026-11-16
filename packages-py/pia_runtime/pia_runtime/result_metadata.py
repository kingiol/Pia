from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ReasonCode = Literal[
    "PROVIDER_FALLBACK", "LAST_GOOD_SNAPSHOT", "STALE_DATA", "CAPABILITY_UNAVAILABLE",
    "OPTIONAL_STAGE_FAILED", "STAGE_TIMEOUT", "TOKEN_BUDGET_EXCEEDED", "COST_BUDGET_EXCEEDED",
    "LLM_STREAM_INTERRUPTED", "CONTEXT_INCOMPLETE", "LEGACY_RESULT_UNKNOWN",
]


class ResultReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: ReasonCode
    stage_id: str | None = None
    capability: str | None = None
    required: bool
    retryable: bool
    artifact_refs: list[str] = Field(default_factory=list)


class ResultMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"] = "1"
    completion: Literal["complete", "partial", "none", "unknown"]
    degraded: bool
    missing_capabilities: list[str] = Field(default_factory=list)
    reasons: list[ResultReason] = Field(default_factory=list)
    quality_summary: Literal["verified", "partial", "stale", "unavailable"]
    context_pack_id: str | None = None
    policy_version: str | None = None
    action_eligible: bool = False


def legacy_metadata():
    return ResultMetadata(
        completion="unknown", degraded=True, quality_summary="unavailable",
        reasons=[ResultReason(code="LEGACY_RESULT_UNKNOWN", required=False, retryable=False)],
    ).model_dump()


def build_result_metadata(pack, stages, events, *, has_result, error=None):
    reasons, missing, qualities = [], set(), []
    if pack:
        for name, block in sorted(pack["blocks"].items()):
            applicable = block["required"] or bool(pack["subject"]) and name in {"fundamentals", "sources"}
            if not applicable:
                continue
            qualities.append(block["status"])
            if block["status"] != "verified":
                missing.add(name)
                reasons.append(ResultReason(
                    code="STALE_DATA" if block["status"] == "stale" else "CAPABILITY_UNAVAILABLE",
                    capability=name, stage_id="required_data" if block["required"] else "supplemental_data",
                    required=block["required"], retryable=True, artifact_refs=block["snapshot_ids"],
                ))
            provenance = block["provenance"]
            if provenance.get("fallback_used"):
                reasons.append(ResultReason(
                    code="LAST_GOOD_SNAPSHOT" if provenance.get("source_type") == "last_good_snapshot" else "PROVIDER_FALLBACK",
                    capability=name, stage_id="required_data", required=block["required"],
                    retryable=False, artifact_refs=block["snapshot_ids"],
                ))
    else:
        reasons.append(ResultReason(code="CONTEXT_INCOMPLETE", required=True, retryable=True))
    known = {"STAGE_TIMEOUT", "TOKEN_BUDGET_EXCEEDED", "COST_BUDGET_EXCEEDED", "LLM_STREAM_INTERRUPTED"}
    for stage in stages:
        if stage["outcome"] in {"failed", "skipped"}:
            code = stage.get("reason_code")
            reasons.append(ResultReason(
                code=code if code in known else "CONTEXT_INCOMPLETE" if stage["required"] else "OPTIONAL_STAGE_FAILED",
                stage_id=stage["stage_id"], required=bool(stage["required"]), retryable=True,
            ))
            missing.add(stage["stage_id"])
    for event in events:
        if event["event_type"] == "CAPABILITY_UNAVAILABLE":
            payload = event["payload"]
            missing.add(payload["capability"])
            reasons.append(ResultReason(code="CAPABILITY_UNAVAILABLE", stage_id=payload.get("stage_id"),
                                        capability=payload["capability"], required=payload.get("required", False), retryable=True))
        if event["event_type"] == "LLM_USAGE_RECORDED" and event["payload"].get("omitted"):
            reasons.append(ResultReason(code="TOKEN_BUDGET_EXCEEDED", stage_id="llm_research", required=False,
                                        retryable=False, artifact_refs=event["payload"]["omitted"]))
    if error:
        code = error.get("code")
        reasons.append(ResultReason(code=code if code in known else "CONTEXT_INCOMPLETE",
                                    required=True, retryable=bool(error.get("retryable", True))))
    unique = {(item.code, item.stage_id, item.capability, item.required, item.retryable,
               tuple(item.artifact_refs)): item for item in reasons}
    reasons = sorted(unique.values(), key=lambda item: (item.code, item.stage_id or "", item.capability or ""))
    missing_reasons = [item for item in reasons if item.code != "PROVIDER_FALLBACK"]
    quality = max(qualities, key=lambda item: ["verified", "partial", "stale", "unavailable"].index(item)) if qualities else "unavailable"
    return ResultMetadata(
        completion=("partial" if missing_reasons else "complete") if has_result else "none",
        degraded=bool(reasons), missing_capabilities=sorted(missing), reasons=reasons,
        quality_summary=quality, context_pack_id=pack["pack_id"] if pack else None, policy_version="1",
        action_eligible=False,
    ).model_dump()
