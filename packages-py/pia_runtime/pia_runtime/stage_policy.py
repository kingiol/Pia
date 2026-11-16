from __future__ import annotations

import time
from typing import Any

from .models import now_iso


POLICY_VERSION = "1"
STAGES = {
    "required_data": (60, True), "supplemental_data": (45, False),
    "context": (5, True), "agents": (50, True), "llm_research": (90, False),
    "rules": (10, True), "synthesize": (10, True),
}


class StageTimeout(TimeoutError):
    code = "STAGE_TIMEOUT"


class StageBudget:
    def __init__(self, db: Any, task: Any, total_seconds: float, *, clock=time.monotonic, required_stages=()):
        self.db, self.task, self.clock = db, task, clock
        self.total_seconds = total_seconds
        self.started = clock()
        self.prior = float(task.target.get("_runtime_consumed_seconds", 0))
        self.paused = 0.0
        self.current: dict | None = None
        self.deadline: float | None = None
        self.completed = {row["stage_id"] for row in db.fetchall(
            "SELECT stage_id FROM task_stage_runs WHERE task_id=? AND outcome='completed'", (task.id,),
        )}
        self.required = {name: required or name in required_stages for name, (_, required) in STAGES.items()}

    def remaining(self) -> float:
        return max(0.0, self.total_seconds - self.prior - (self.clock() - self.started - self.paused))

    def start(self, stage_id: str, *, required: bool | None = None) -> bool:
        self.finish()
        cap, _ = STAGES[stage_id]
        required = self.required[stage_id] if required is None else required
        ordered = list(STAGES)
        reserve = sum(STAGES[name][0] for name in ordered[ordered.index(stage_id) + 1:]
                      if self.required[name] and name not in self.completed)
        allocated = max(0.0, min(cap, self.remaining() - reserve))
        attempt = self.db.fetchone(
            "SELECT COUNT(*) AS n FROM task_stage_runs WHERE task_id=? AND stage_id=?",
            (self.task.id, stage_id),
        )["n"] + 1
        self.current = {
            "stage_id": stage_id, "attempt": attempt, "policy_version": POLICY_VERSION,
            "required": required, "allocated_ms": round(allocated * 1000),
            "started_at": now_iso(), "outcome": "running", "reason_code": None,
            "artifact_ids": [],
        }
        self.deadline = self.clock() + allocated
        self._persist()
        self.db.append_event(self.task.id, "STAGE_STARTED", self.current)
        if allocated <= 0 and not required:
            self.finish("skipped", "STAGE_TIMEOUT")
            return False
        self.check()
        return True

    def check(self) -> None:
        if self.remaining() <= 0 or (self.deadline is not None and self.clock() >= self.deadline):
            raise StageTimeout("Stage runtime budget exhausted.")

    def timeout(self) -> float:
        self.check()
        return min(self.remaining(), max(0.001, (self.deadline or self.clock() + 45) - self.clock()), 45)

    def add_pause(self, seconds: float) -> None:
        self.paused += seconds
        if self.deadline is not None:
            self.deadline += seconds

    def finish(self, outcome: str = "completed", reason_code: str | None = None) -> None:
        if self.current is None:
            return
        self.current.update(outcome=outcome, reason_code=reason_code, finished_at=now_iso())
        self._persist()
        kind = {"completed": "STAGE_COMPLETED", "skipped": "STAGE_SKIPPED"}.get(outcome, "STAGE_FAILED")
        self.db.append_event(self.task.id, kind, self.current)
        if outcome == "completed":
            self.completed.add(self.current["stage_id"])
        self.task.target["_runtime_consumed_seconds"] = self.prior + self.clock() - self.started - self.paused
        current = self.db.get_task(self.task.id)
        if current and current.status.value in {"CANCELLED", "FAILED", "TIMEOUT", "EXPIRED"}:
            self.task.status, self.task.error, self.task.finished_at = current.status, current.error, current.finished_at
        self.db.update_task(self.task)
        self.current, self.deadline = None, None

    def _persist(self) -> None:
        import json
        row = self.current
        self.db.execute(
            """INSERT INTO task_stage_runs
               (user_id, task_id, stage_id, attempt, policy_version, required, allocated_ms,
                started_at, finished_at, outcome, reason_code, artifact_ids)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(task_id, stage_id, attempt) DO UPDATE SET
               finished_at=excluded.finished_at, outcome=excluded.outcome, reason_code=excluded.reason_code""",
            (self.task.user_id, self.task.id, row["stage_id"], row["attempt"], POLICY_VERSION,
             int(row["required"]), row["allocated_ms"], row["started_at"], row.get("finished_at"),
             row["outcome"], row["reason_code"], json.dumps(row["artifact_ids"])),
        )
