from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field

from .models import new_id, now_iso
from .security import redact_secrets


VERSIONS = {
    "builder": "1",
    "graph": "1",
    "rules_evaluator": "1",
    "synthesizer": "1",
}
EXECUTION_FIELDS = {
    "content_hash", "pack_id", "task_id", "input_binding_id",
    "source_pack_id", "execution_mode", "created_at",
}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sanitize_context(value: Any) -> Any:
    """Remove transport credentials without redacting research token counters."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in {"headers", "http_headers", "authorization", "api_key",
                              "access_token", "refresh_token", "password", "secret",
                              "credential", "credentials"}:
                continue
            result[str(key)] = sanitize_context(item)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize_context(item) for item in value]
    if isinstance(value, str):
        if value.startswith(("https://", "http://")):
            try:
                parsed = urlsplit(value)
                port = parsed.port
            except ValueError:
                return "[invalid source URL]"
            hostname = parsed.hostname or ""
            if port:
                hostname += f":{port}"
            query = [
                (key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
                if not any(word in key.lower() for word in
                           ("key", "token", "secret", "password", "auth", "signature"))
            ]
            value = urlunsplit((parsed.scheme, hostname, parsed.path,
                                urlencode(query), parsed.fragment))
        return redact_secrets(value)
    return value


class ContextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["verified", "partial", "stale", "unavailable"]
    required: bool
    as_of: str | None = None
    observed_at: str | None = None
    expires_at: str | None = None
    snapshot_ids: list[str] = Field(default_factory=list)
    content_hash: str
    data: Any
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class DecisionContextPack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    pack_id: str
    task_id: str
    input_binding_id: str
    source_pack_id: str | None = None
    analysis_as_of: str
    created_at: str
    subject: str | None
    trigger_type: str
    data_mode: Literal["fixture", "live"]
    execution_mode: Literal["run", "replay"] = "run"
    profile_snapshot: dict[str, Any]
    rule_snapshot: dict[str, Any]
    confirmed_memories: list[dict[str, Any]]
    blocks: dict[str, ContextBlock]
    evidence: list[dict[str, Any]]
    versions: dict[str, str]
    content_hash: str


def pack_hash(pack: dict[str, Any]) -> str:
    return content_hash({
        key: value for key, value in pack.items() if key not in EXECUTION_FIELDS
    })


def validate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    validated = DecisionContextPack.model_validate(pack).model_dump()
    if pack_hash(validated) != validated["content_hash"]:
        raise ValueError("CONTEXT_HASH_MISMATCH")
    for block in validated["blocks"].values():
        if content_hash(block["data"]) != block["content_hash"]:
            raise ValueError("CONTEXT_BLOCK_HASH_MISMATCH")
    return validated


def _block(data: Any, *, required: bool, as_of: str) -> dict[str, Any]:
    data = sanitize_context(deepcopy(data))
    metadata = data if isinstance(data, dict) else {}
    status = metadata.get("quality", "partial" if data else "unavailable")
    if status not in {"verified", "partial", "stale", "unavailable"}:
        status = "partial"
    return ContextBlock(
        status=status, required=required, as_of=metadata.get("as_of", as_of),
        observed_at=metadata.get("observed_at"),
        expires_at=metadata.get("expires_at"),
        snapshot_ids=[str(metadata["snapshot_id"])] if metadata.get("snapshot_id") else [],
        content_hash=content_hash(data), data=data,
        missing_fields=[] if data else ["data"],
        warnings=list(metadata.get("quality_errors", [])),
        provenance=metadata.get("provenance", {
            "provider_id": metadata.get("provider_id", metadata.get("source")),
        }),
    ).model_dump()


def build_context_pack(
    *, task: Any, binding: dict[str, Any], market: dict[str, Any],
    portfolio: dict[str, Any], research: dict[str, Any],
    evidence: list[dict[str, Any]], data_mode: str,
) -> dict[str, Any]:
    """Assemble supplied snapshots only; no repository or provider access."""
    as_of = str(task.target.get("as_of", market.get("as_of")))
    symbol = task.target.get("symbol")
    sources = {
        "news": research.get("news", []),
        "filings": research.get("filings", []),
    }
    source_rows = [*sources["news"], *sources["filings"]]
    if source_rows:
        statuses = [row.get("quality", "partial") for row in source_rows]
        sources["quality"] = max(statuses, key=lambda status: ["verified", "partial", "stale", "unavailable"].index(
            status if status in {"verified", "partial", "stale", "unavailable"} else "partial"))
        sources["provenance"] = {
            "fallback_used": any(row.get("provenance", {}).get("fallback_used") for row in source_rows),
            "attempts": [attempt for row in source_rows for attempt in row.get("provenance", {}).get("attempts", [])],
        }
    source_required = task.trigger_type in {"FilingPublished", "AnnouncementPublished"}
    instrument = deepcopy(research.get("instrument", research.get("company_profile", {})))
    if "instrument" in research and research.get("company_profile"):
        instrument["company_profile"] = research["company_profile"]
    blocks = {
        "market": _block(market, required=True, as_of=as_of),
        "portfolio": _block(portfolio, required=True, as_of=as_of),
        "instrument": _block(instrument, required=bool(symbol), as_of=as_of),
        "fundamentals": _block(research.get("fundamentals", {}), required=False, as_of=as_of),
        "sources": _block(sources if any(sources.values()) else {}, required=source_required, as_of=as_of),
        "events": _block(task.target.get("event", task.target if source_required else {}), required=source_required, as_of=as_of),
    }
    payload = binding["payload"]
    pack = {
        "schema_version": "1", "pack_id": new_id("pack"), "task_id": task.id,
        "input_binding_id": binding["id"], "source_pack_id": None,
        "analysis_as_of": as_of, "created_at": now_iso(), "subject": symbol,
        "trigger_type": task.trigger_type, "data_mode": data_mode,
        "execution_mode": "run",
        "profile_snapshot": payload["profile"],
        "rule_snapshot": payload["rules"],
        "confirmed_memories": payload["confirmed_memories"],
        "blocks": blocks, "evidence": sanitize_context(evidence),
        "versions": dict(VERSIONS), "content_hash": "",
    }
    pack["content_hash"] = pack_hash(pack)
    return validate_pack(pack)


def replay_pack(pack: dict[str, Any], task_id: str, binding_id: str) -> dict[str, Any]:
    result = deepcopy(validate_pack(pack))
    if result["versions"] != VERSIONS:
        raise ValueError("REPLAY_VERSION_MISMATCH")
    result.update(
        pack_id=new_id("pack"), task_id=task_id, input_binding_id=binding_id,
        source_pack_id=pack["pack_id"], execution_mode="replay", created_at=now_iso(),
    )
    return validate_pack(result)


def pack_overview(pack: dict[str, Any]) -> dict[str, Any]:
    pack = validate_pack(pack)
    return {
        key: value for key, value in pack.items()
        if key not in {"profile_snapshot", "rule_snapshot", "confirmed_memories", "evidence", "blocks"}
    } | {
        "blocks": {
            name: {key: value for key, value in block.items() if key != "data"}
            for name, block in pack["blocks"].items()
        },
    }
