from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .decision_context import canonical_json
from .models import new_id, now_iso


class BudgetExceeded(RuntimeError):
    code = "COST_BUDGET_EXCEEDED"


class RoutePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    provider_id: str
    endpoint: str
    model: str
    credential_ref: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    priority: int = 100
    capabilities: list[Literal["structured_output", "streaming", "tool_calls", "token_usage"]]
    allowed_data_classes: list[Literal["market_public", "portfolio", "confirmed_memory"]] = ["market_public"]
    input_cost_per_1k: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_cost_per_1k: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    token_upper_bound: Literal["utf8_bytes"] | None = None

    @model_validator(mode="after")
    def validate_endpoint(self):
        parsed = urlsplit(self.endpoint)
        if (parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("INVALID_LLM_ENDPOINT")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("LLM_ENDPOINT_REQUIRES_TLS")
        return self


class LLMPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"] = "1"
    routes: list[RoutePolicy] = Field(min_length=1)
    max_routes_per_stage: int = Field(default=2, ge=1, le=2)
    max_http_attempts_per_stage: int = Field(default=6, ge=1, le=6)
    task_budget_usd: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    user_daily_budget_usd: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def unique_routes(self):
        if len({item.route_id for item in self.routes}) != len(self.routes):
            raise ValueError("DUPLICATE_LLM_ROUTE")
        return self


class BudgetLedger:
    def __init__(self, db, task_limit=None, daily_limit=None):
        self.db = db
        self.task_limit = Decimal(str(task_limit)) if task_limit is not None else None
        self.daily_limit = Decimal(str(daily_limit)) if daily_limit is not None else None

    def route_allowed(self, route):
        if self.task_limit is None and self.daily_limit is None:
            return True
        return (getattr(route, "token_upper_bound", None) == "utf8_bytes"
                and all(Decimal(str(value or 0)) > 0 for value in
                        [route.input_cost_per_1k, route.output_cost_per_1k]))

    def _lock(self, identities):
        from .postgres import PostgresDatabase
        for identity in sorted(identities):
            self.db.execute("INSERT INTO llm_budget_locks(id) VALUES (?) ON CONFLICT DO NOTHING", (identity,))
            suffix = " FOR UPDATE" if isinstance(self.db, PostgresDatabase) else ""
            self.db.fetchone("SELECT id FROM llm_budget_locks WHERE id=?" + suffix, (identity,))

    def reserve(self, context, route, input_bytes, output_tokens=1024, *, day=None):
        day = day or datetime.now(timezone.utc).date().isoformat()
        rates = [Decimal(str(route.input_cost_per_1k or 0)), Decimal(str(route.output_cost_per_1k or 0))]
        priced = all(rate > 0 and rate.is_finite() for rate in rates)
        strict = self.task_limit is not None or self.daily_limit is not None
        if strict and (not priced or getattr(route, "token_upper_bound", None) != "utf8_bytes"):
            raise BudgetExceeded("COST_BOUND_UNAVAILABLE")
        reserved = (Decimal(input_bytes) * rates[0] + Decimal(output_tokens) * rates[1]) / 1000 if priced else Decimal(0)
        attempt_id = new_id("llm_attempt")
        with self.db.transaction():
            self._lock([f"user:{context.user_id}:{day}", f"task:{context.task_id}"])
            rows = self.db.fetchall("SELECT task_id, day_utc, accounted_usd FROM llm_budget_reservations WHERE user_id=?",
                                    (context.user_id,))
            task_spent = sum((Decimal(row["accounted_usd"]) for row in rows if row["task_id"] == context.task_id), Decimal(0))
            daily_spent = sum((Decimal(row["accounted_usd"]) for row in rows if row["day_utc"] == day), Decimal(0))
            if (self.task_limit is not None and task_spent + reserved > self.task_limit
                    or self.daily_limit is not None and daily_spent + reserved > self.daily_limit):
                raise BudgetExceeded("COST_BUDGET_EXCEEDED")
            self.db.execute("INSERT INTO llm_attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (attempt_id, context.user_id, context.task_id, context.request_id,
                             route.route_id or route.provider_id, route.provider_id, route.model, day,
                             "reserved", "unknown", None, None, now_iso()))
            self.db.execute("INSERT INTO llm_budget_reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (attempt_id, context.user_id, context.task_id, day, str(reserved), str(reserved),
                             canonical_json({"input": str(rates[0]), "output": str(rates[1]), "priced": priced}), 0))
        return attempt_id

    def settle(self, attempt_id, usage, reason_code=None):
        with self.db.transaction():
            row = self.db.fetchone("SELECT * FROM llm_budget_reservations WHERE attempt_id=?", (attempt_id,))
            if not row:
                raise KeyError(attempt_id)
            self._lock([f"user:{row['user_id']}:{row['day_utc']}", f"task:{row['task_id']}"])
            row = self.db.fetchone("SELECT * FROM llm_budget_reservations WHERE attempt_id=?", (attempt_id,))
            if row["settled"]:
                return
            price = json.loads(row["price_json"])
            valid_usage = bool(usage and all(isinstance(usage.get(key), int) and not isinstance(usage[key], bool) and usage[key] >= 0
                                            for key in ["prompt_tokens", "completion_tokens"]))
            known = valid_usage and price["priced"]
            actual = ((Decimal(usage["prompt_tokens"]) * Decimal(price["input"])
                       + Decimal(usage["completion_tokens"]) * Decimal(price["output"])) / 1000) if known else Decimal(row["reserved_usd"])
            self.db.execute("UPDATE llm_budget_reservations SET accounted_usd=?, settled=1 WHERE attempt_id=?",
                            (str(actual), attempt_id))
            self.db.execute("UPDATE llm_attempts SET status=?, cost_status=?, usage_json=?, reason_code=? WHERE id=?",
                            ("failed" if reason_code else "completed", "known" if known else "unknown",
                             canonical_json(usage) if usage else None, reason_code, attempt_id))

    def summary(self, user_id, task_id=None):
        rows = self.db.fetchall(
            """SELECT a.*, r.reserved_usd, r.accounted_usd, r.settled
               FROM llm_attempts a JOIN llm_budget_reservations r ON r.attempt_id=a.id
               WHERE a.user_id=?""" + (" AND a.task_id=?" if task_id else "") + " ORDER BY a.created_at, a.id",
            (user_id, task_id) if task_id else (user_id,),
        )
        return {
            "known_cost_usd": str(sum((Decimal(row["accounted_usd"]) for row in rows if row["cost_status"] == "known"), Decimal(0))),
            "conservative_reserved_usd": str(sum((Decimal(row["accounted_usd"]) for row in rows if row["cost_status"] != "known"), Decimal(0))),
            "unknown_count": sum(row["cost_status"] == "unknown" for row in rows),
            "day_boundary": "UTC", "attempts": [dict(row) for row in rows],
        }
