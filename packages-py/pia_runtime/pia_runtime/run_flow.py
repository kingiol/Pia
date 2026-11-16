from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FlowNode(BaseModel):
    id: str
    stage_id: str
    attempt: int = 1
    label: str
    status: Literal["pending", "running", "completed", "skipped", "failed", "blocked"]
    required: bool = False
    started_at: str | None = None
    duration_ms: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)


class FlowEdge(BaseModel):
    source: str
    target: str
    relation: Literal["sequence", "depends_on", "fallback", "produces"]


class RunFlow(BaseModel):
    schema_version: Literal["1"] = "1"
    task_id: str
    snapshot_seq: int
    next_after_seq: int
    has_more: bool
    completeness: Literal["recorded", "legacy_incomplete"]
    nodes: list[FlowNode]
    edges: list[FlowEdge]


def project_flow(db, task_id: str, user_id: str, after_seq=0, limit=100, snapshot_seq=None) -> dict:
    task = db.get_task(task_id)
    if task is None or task.user_id != user_id:
        raise KeyError(task_id)
    if after_seq < 0 or not 1 <= limit <= 500:
        raise ValueError("INVALID_FLOW_PAGE")
    maximum = db.fetchone("SELECT MAX(id) AS seq FROM task_events WHERE task_id=?", (task_id,))["seq"] or 0
    upper = min(maximum, snapshot_seq) if snapshot_seq is not None else maximum
    events = db.fetchall("SELECT id, event_type, payload_json, created_at FROM task_events WHERE task_id=? AND id<=? ORDER BY id",
                         (task_id, upper))
    page = [row for row in events if row["id"] > after_seq][:limit]
    next_seq = page[-1]["id"] if page else after_seq
    nodes, changed, edges = {}, set(), []
    previous_stage = previous_agent = None
    provider_calls = {}
    for row in events:
        if row["id"] > next_seq:
            break
        payload, kind = json.loads(row["payload_json"]), row["event_type"]
        node = None
        if kind.startswith("STAGE_"):
            identity = f"{task_id}:stage:{payload['stage_id']}:{payload['attempt']}"
            node = nodes.get(identity, FlowNode(
                id=identity, stage_id=payload["stage_id"], attempt=payload["attempt"],
                label=payload["stage_id"], status="running", required=payload["required"],
                started_at=payload["started_at"],
            ))
            node.status = {"STAGE_COMPLETED": "completed", "STAGE_SKIPPED": "skipped",
                           "STAGE_FAILED": "failed"}.get(kind, "running")
            node.reason_codes = [payload["reason_code"]] if payload.get("reason_code") else []
            if payload.get("finished_at"):
                node.duration_ms = max(0, (datetime.fromisoformat(payload["finished_at"]) -
                                           datetime.fromisoformat(payload["started_at"])).total_seconds() * 1000)
            if kind == "STAGE_STARTED":
                if previous_stage:
                    edges.append(FlowEdge(source=previous_stage, target=identity, relation="sequence"))
                previous_stage = identity
        elif kind in {"AGENT_STARTED", "AGENT_COMPLETED"}:
            identity = f"{task_id}:agent:{payload['agent_name']}"
            node = nodes.get(identity, FlowNode(
                id=identity, stage_id="agents", label=payload["agent_name"], status="running",
                started_at=row["created_at"],
            ))
            node.status = "completed" if kind == "AGENT_COMPLETED" else "running"
            if kind == "AGENT_COMPLETED" and node.started_at:
                node.duration_ms = max(0, (datetime.fromisoformat(row["created_at"]) -
                                           datetime.fromisoformat(node.started_at)).total_seconds() * 1000)
            if kind == "AGENT_STARTED":
                if previous_agent:
                    edges.append(FlowEdge(source=previous_agent, target=identity, relation="sequence"))
                previous_agent = identity
        elif kind == "PROVIDER_ATTEMPT":
            identity = f"{task_id}:provider:{payload['attempt_id']}"
            node = FlowNode(
                id=identity, stage_id=payload["capability"], attempt=payload.get("ordinal", 1),
                label=f"{payload['capability']} / {payload['provider_id']}",
                status="completed" if payload["outcome"] == "success" else "failed",
                started_at=payload["started_at"], duration_ms=payload["duration_ms"],
                reason_codes=[payload["reason_code"]] if payload.get("reason_code") else [],
                artifact_refs=[payload["attempt_id"]],
            )
            previous = provider_calls.get(payload["call_id"])
            if previous:
                edges.append(FlowEdge(source=previous, target=identity, relation="fallback"))
            provider_calls[payload["call_id"]] = identity
        elif kind == "DECISION_CREATED":
            identity = f"{task_id}:decision"
            node = FlowNode(id=identity, stage_id="synthesize", label=f"Decision: {payload['status']}",
                            status="blocked" if payload["status"] == "BLOCKED" else "completed",
                            artifact_refs=[payload["id"]], required=True)
            if previous_stage:
                edges.append(FlowEdge(source=previous_stage, target=identity, relation="produces"))
        elif kind == "TASK_STATUS" and payload.get("status") in {
            "FAILED", "RETRYABLE", "TIMEOUT", "CANCELLED", "EXPIRED",
        }:
            for pending in nodes.values():
                if pending.status == "running":
                    pending.status = "failed"
                    pending.reason_codes = sorted(set([*pending.reason_codes, f"TASK_{payload['status']}"]))
                    if row["id"] > after_seq:
                        changed.add(pending.id)
        if node:
            nodes[node.id] = node
            if row["id"] > after_seq:
                changed.add(node.id)
    return RunFlow(
        task_id=task_id, snapshot_seq=upper, next_after_seq=next_seq,
        has_more=any(row["id"] > next_seq for row in events),
        completeness="recorded" if db.get_context_pack(task_id, user_id) else "legacy_incomplete",
        nodes=[node for identity, node in nodes.items() if identity in changed],
        edges=[edge for edge in edges if edge.target in changed or edge.source in changed],
    ).model_dump()
