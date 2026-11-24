from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from .analytics import AnalyticsStore


MARKET_SYNC_STAGES = (
    "market_snapshot", "trading_calendar", "universe", "daily_bars",
    "fundamentals", "news", "filing",
)
RECEIPT_AGES = {
    "universe": timedelta(days=1),
    "fundamentals": timedelta(days=1),
    "news": timedelta(hours=1),
    "filing": timedelta(hours=1),
}
Progress = Callable[[dict[str, Any]], None]


class MarketSyncProgress:
    def __init__(
        self, analytics: AnalyticsStore, as_of: str, now: datetime, scope: str,
        refresh_stage: str | None, on_progress: Progress | None,
    ) -> None:
        self.analytics = analytics
        self.as_of = as_of
        self.now = now
        self.scope = hashlib.sha256(scope.encode()).hexdigest()
        self.refresh_stage = refresh_stage
        self.on_progress = on_progress
        self.stages: dict[str, dict[str, Any]] = {}
        self.receipts = {
            (receipt["stage"], receipt["symbol"]): receipt
            for receipt in analytics.market_sync_receipts(as_of, self.scope)
        }

    def publish(self, stage: str, **update: Any) -> None:
        frame = {"stage": stage, **self.stages.get(stage, {}), **update}
        self.stages[stage] = frame
        if self.on_progress:
            self.on_progress(frame.copy())

    def start(self, stage: str, total: int) -> None:
        self.publish(
            stage, status="running", total=total, fetched=0, reused=0, failed=0, saved_rows=0,
        )

    def should_fetch(self, stage: str) -> bool:
        return self.refresh_stage in (None, stage) or (
            self.refresh_stage == "market_snapshot" and stage in ("trading_calendar", "universe")
        )

    def reuse(self, stage: str, symbol: str = "") -> dict[str, Any] | None:
        receipt = self.receipts.get((stage, symbol))
        if not receipt or stage == self.refresh_stage:
            return None
        checked_at = datetime.fromisoformat(receipt["checked_at"])
        if checked_at > self.now:
            return None
        if stage == "trading_calendar" and checked_at.date() != self.now.date():
            return None
        if stage in RECEIPT_AGES and self.now - checked_at >= RECEIPT_AGES[stage]:
            return None
        return receipt

    def save(self, stage: str, count: int, *, symbol: str = "", artifact: str | None = None) -> None:
        receipt = {
            "stage": stage, "symbol": symbol, "count": count,
            "checked_at": self.now.isoformat(), "artifact": artifact,
        }
        key = hashlib.sha256(f"{self.scope}\0{self.as_of}\0{stage}\0{symbol}".encode()).hexdigest()
        self.analytics.save_snapshot(
            snapshot_id=f"market_sync_{key}", kind="market_sync_receipt",
            as_of=self.as_of, observed_at=receipt["checked_at"], source=self.scope,
            quality="verified", payload=receipt,
        )

    def item_done(self, stage: str, outcome: str, count: int = 0) -> None:
        state = self.stages[stage]
        self.publish(stage, **{outcome: state[outcome] + 1}, saved_rows=state["saved_rows"] + count)

    def finish(self, stage: str) -> None:
        state = self.stages[stage]
        if state["failed"]:
            status = "partial" if state["fetched"] or state["reused"] or state["saved_rows"] else "failed"
        else:
            status = "reused" if state["reused"] and not state["fetched"] else "done"
        self.publish(stage, status=status, symbol=None)


@dataclass
class _Run:
    request: tuple
    updates: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: BaseException | None = None
    finished: bool = False


class MarketSyncRuns:
    """Attach identical requests and serialize overlapping scopes for a user and day."""

    def __init__(self) -> None:
        self._changed = threading.Condition()
        self._active: dict[tuple[str, str], _Run] = {}

    def run(self, key: tuple[str, str], request: tuple, work, on_progress: Progress | None):
        with self._changed:
            while active := self._active.get(key):
                if active.request == request:
                    break
                self._changed.wait()
            if active is None:
                active = self._active[key] = _Run(request)
                owner = True
            else:
                owner = False

        if not owner:
            offset = 0
            while True:
                with self._changed:
                    self._changed.wait_for(lambda: offset < len(active.updates) or active.finished)
                    updates = active.updates[offset:]
                    offset += len(updates)
                    finished = active.finished
                if on_progress:
                    for update in updates:
                        on_progress(update)
                if finished:
                    if active.error:
                        raise active.error
                    return active.result

        def publish(update: dict[str, Any]) -> None:
            with self._changed:
                active.updates.append(update)
                self._changed.notify_all()
            if on_progress:
                on_progress(update)

        try:
            active.result = work(publish)
            return active.result
        except BaseException as error:
            active.error = error
            raise
        finally:
            with self._changed:
                active.finished = True
                del self._active[key]
                self._changed.notify_all()
