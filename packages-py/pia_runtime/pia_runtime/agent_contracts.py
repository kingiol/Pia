from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentInputContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    agent_name: str
    payload: dict[str, Any]
    evidence_ids: list[str] = Field(default_factory=list)


class AgentOutputContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    status: Literal["DONE", "BLOCKED", "FAILED"] = "DONE"
    payload: dict[str, Any]
    evidence_ids: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class GraphStateContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str
    trigger_type: str
    as_of: str
    symbol: str | None = None
    market: dict[str, Any]
    portfolio: dict[str, Any]
    evidence_ids: list[str] = Field(default_factory=list)
    research: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)

