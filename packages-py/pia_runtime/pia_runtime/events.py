from __future__ import annotations

import json
import weakref
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import new_id, now_iso


PRIORITY = {
    "PortfolioRiskChanged": 100,
    "DataQualityDegraded": 90,
    "FilingPublished": 70,
    "MarketClose": 60,
    "MarketBreadthChanged": 50,
    "PriceVolumeAnomaly": 40,
}


class EventEngine:
    def __init__(self, db: Any, runtime: Any) -> None:
        self.db = db
        self.runtime = weakref.proxy(runtime)

    def _notify(
        self,
        event_type: str,
        title: str,
        body: str,
        task_id: str | None,
        user_id: str,
    ) -> None:
        notification = self.db.create_notification(
            event_type,
            title,
            body,
            task_id,
            user_id=user_id,
        )
        try:
            receipt = self.runtime.notifier.deliver(
                notification["title"],
                notification["body"],
                user_id=user_id,
                notification_id=notification["id"],
            )
            self.db.record_notification_delivery(
                notification["id"],
                user_id,
                receipt.provider_id,
                receipt.status,
                receipt.detail,
            )
            if receipt.status not in {"DELIVERED", "DISABLED"}:
                self.db.audit(task_id, "NOTIFICATION_DELIVERY_FAILED", {
                    "user_id": user_id,
                    "notification_id": notification["id"],
                    "provider_id": receipt.provider_id,
                    "status": receipt.status,
                    "detail": receipt.detail,
                }, user_id=user_id)
        except Exception as error:
            self.db.record_notification_delivery(
                notification["id"],
                user_id,
                "notification-router",
                "FAILED",
                f"{type(error).__name__}: {error}",
            )
            self.db.audit(task_id, "NOTIFICATION_DELIVERY_FAILED", {
                "user_id": user_id,
                "notification_id": notification["id"],
                "error": type(error).__name__,
                "message": str(error),
            }, user_id=user_id)

    def notify(
        self,
        event_type: str,
        title: str,
        body: str,
        task_id: str | None = None,
        *,
        user_id: str = "default",
    ) -> None:
        self._notify(event_type, title, body, task_id, user_id)

    def derive_market_events(
        self,
        sync_result: dict[str, Any],
        *,
        user_id: str = "default",
    ) -> list[dict[str, Any]]:
        """Turn a completed market sync into deterministic domain events."""
        if not getattr(self.runtime.settings, "auto_event_generation", True):
            return []
        snapshot = sync_result.get("market_snapshot")
        if not snapshot:
            return []

        snapshot_id = str(snapshot["snapshot_id"])
        as_of = str(snapshot.get("as_of") or sync_result.get("as_of"))
        occurred_at = str(snapshot.get("observed_at") or now_iso())
        common = {
            "as_of": as_of,
            "occurred_at": occurred_at,
            "_market_snapshot_id": snapshot_id,
        }
        derived: list[dict[str, Any]] = []

        quality = str(sync_result.get("quality", "unavailable"))
        market_quality = str(sync_result.get("market_snapshot_quality", "unavailable"))
        failures = list(sync_result.get("failures") or [])
        if quality != "verified" or market_quality != "verified" or failures:
            derived.append(self.ingest(
                "DataQualityDegraded",
                {
                    **common,
                    "quality": quality,
                    "market_snapshot_quality": market_quality,
                    "failures": failures,
                    "reason": "Market data synchronization did not satisfy the quality gate.",
                },
                dedupe_key=self._scoped_dedupe_key(
                    f"data-quality:{snapshot_id}",
                    user_id,
                ),
                user_id=user_id,
            ))

        previous = self._latest_payload(
            "market_snapshots",
            "id <> ?",
            (snapshot_id,),
        )
        if previous:
            try:
                breadth_delta = float(snapshot.get("breadth", 0)) - float(previous.get("breadth", 0))
            except (TypeError, ValueError):
                breadth_delta = 0.0
            threshold = float(getattr(
                self.runtime.settings,
                "market_breadth_event_threshold",
                0.15,
            ))
            if abs(breadth_delta) >= threshold:
                derived.append(self.ingest(
                    "MarketBreadthChanged",
                    {
                        **common,
                        "breadth": snapshot.get("breadth"),
                        "previous_breadth": previous.get("breadth"),
                        "breadth_delta": breadth_delta,
                        "previous_snapshot_id": previous.get("snapshot_id"),
                    },
                    dedupe_key=self._scoped_dedupe_key(
                        f"market-breadth:{snapshot_id}",
                        user_id,
                    ),
                    user_id=user_id,
                ))

        anomaly_threshold = float(getattr(
            self.runtime.settings,
            "price_volume_anomaly_pct",
            5.0,
        ))
        for instrument in snapshot.get("instruments", []):
            try:
                change_pct = float(instrument.get("change_pct") or 0)
            except (TypeError, ValueError):
                change_pct = 0.0
            try:
                volume_ratio = float(instrument.get("volume_ratio") or 0)
            except (TypeError, ValueError):
                volume_ratio = 0.0
            if abs(change_pct) < anomaly_threshold and volume_ratio < 2.0:
                continue
            symbol = str(instrument.get("symbol") or "unknown")
            derived.append(self.ingest(
                "PriceVolumeAnomaly",
                {
                    **common,
                    "symbol": symbol,
                    "change_pct": change_pct,
                    "volume_ratio": volume_ratio or None,
                    "instrument": instrument,
                },
                dedupe_key=self._scoped_dedupe_key(
                    f"price-volume:{snapshot_id}:{symbol}",
                    user_id,
                ),
                user_id=user_id,
            ))

        for source in sync_result.get("research_sources", []):
            if str(source.get("source_type")) != "filing":
                continue
            if str(source.get("quality", "unavailable")) == "unavailable":
                continue
            external_id = str(source.get("external_id") or source.get("content_hash"))
            symbol = str(source.get("symbol") or "unknown")
            derived.append(self.ingest(
                "FilingPublished",
                {
                    **common,
                    "symbol": symbol,
                    "filing_id": external_id,
                    "title": source.get("title"),
                    "published_at": source.get("published_at"),
                    "source_uri": source.get("source_uri"),
                    "quality": source.get("quality"),
                },
                dedupe_key=self._scoped_dedupe_key(
                    f"filing:{snapshot_id}:{symbol}:{external_id}",
                    user_id,
                ),
                user_id=user_id,
            ))
        return derived

    @staticmethod
    def _scoped_dedupe_key(base: str, user_id: str) -> str:
        """Keep legacy default keys stable while isolating cloud users."""
        return base if user_id == "default" else f"{base}:{user_id}"

    def derive_portfolio_risk_event(
        self,
        snapshot: dict[str, Any],
        previous: dict[str, Any] | None,
        *,
        user_id: str = "default",
    ) -> dict[str, Any] | None:
        """Emit a risk event only when a portfolio risk metric changes."""
        if not getattr(self.runtime.settings, "auto_event_generation", True):
            return None
        snapshot_id = str(snapshot["snapshot_id"])
        if not previous:
            return None

        rules = self.runtime.get_rules(user_id)["rules"]
        current_drawdown = _number(snapshot.get("drawdown"))
        previous_drawdown = _number(previous.get("drawdown"))
        current_weight = _max_position_weight(snapshot, rules)
        previous_weight = _max_position_weight(previous, rules)
        drawdown_delta = current_drawdown - previous_drawdown
        weight_delta = current_weight - previous_weight
        drawdown_threshold = float(getattr(
            self.runtime.settings,
            "portfolio_risk_drawdown_delta",
            0.05,
        ))
        weight_threshold = float(getattr(
            self.runtime.settings,
            "portfolio_risk_weight_delta",
            0.10,
        ))
        crossed_breach = (
            _has_position_breach(snapshot, rules)
            and not _has_position_breach(previous, rules)
        ) or (
            current_drawdown >= float(rules.get("drawdown_limit", 1))
            and previous_drawdown < float(rules.get("drawdown_limit", 1))
        )
        if (
            abs(drawdown_delta) < drawdown_threshold
            and abs(weight_delta) < weight_threshold
            and not crossed_breach
        ):
            return None

        latest_market = self._latest_row("market_snapshots", "as_of = ?", (snapshot["as_of"],))
        payload = {
            "as_of": snapshot.get("as_of"),
            "occurred_at": snapshot.get("observed_at") or now_iso(),
            "account_id": user_id,
            "user_id": user_id,
            "_portfolio_snapshot_id": snapshot_id,
            "previous_portfolio_snapshot_id": previous.get("snapshot_id"),
            "_market_snapshot_id": latest_market.get("snapshot_id") if latest_market else None,
            "drawdown": current_drawdown,
            "previous_drawdown": previous_drawdown,
            "drawdown_delta": drawdown_delta,
            "max_position_weight": current_weight,
            "previous_max_position_weight": previous_weight,
            "weight_delta": weight_delta,
            "crossed_breach": crossed_breach,
        }
        return self.ingest(
            "PortfolioRiskChanged",
            payload,
            dedupe_key=f"portfolio-risk:{user_id}:{snapshot_id}",
            user_id=user_id,
        )

    def _latest_row(
        self,
        table: str,
        where: str = "",
        params: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        query = f"SELECT * FROM {table}"
        if where:
            query += f" WHERE {where}"
        query += " ORDER BY as_of DESC, id DESC LIMIT 1"
        row = self.db.fetchone(query, params)
        return dict(row) if row else None

    def _latest_payload(
        self,
        table: str,
        where: str = "",
        params: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        row = self._latest_row(table, where, params)
        if not row:
            return None
        payload = row.get("payload_json")
        if not payload:
            return None
        result = json.loads(payload)
        if isinstance(result, dict):
            result.setdefault("snapshot_id", row.get("id"))
            return result
        return None

    def ingest(
        self,
        event_type: str,
        payload: dict[str, Any],
        dedupe_key: str | None = None,
        *,
        user_id: str = "default",
    ) -> dict[str, Any]:
        if dedupe_key:
            key = dedupe_key
        else:
            cooldown = max(1, int(payload.get("cooldown_seconds", 86400)))
            occurred_at = self._event_time(payload)
            bucket = int(occurred_at.timestamp() // cooldown)
            scope = payload.get("symbol") or payload.get("account_id") or "global"
            key = f"{event_type}:{scope}:{bucket}"
        scoped_key = f"{user_id}:{key}"
        if self._is_expired(payload):
            event_id = new_id("event")
            self.db.execute(
                """INSERT INTO events
                   (id, event_type, user_id, dedupe_key, priority, payload_json, occurred_at, expires_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'EXPIRED')""",
                (
                    event_id,
                    event_type,
                    user_id,
                    scoped_key,
                    PRIORITY.get(event_type, 10),
                    json.dumps(payload, ensure_ascii=False),
                    now_iso(),
                    payload.get("expires_at"),
                ),
            )
            self._notify(
                event_type,
                f"{event_type} expired",
                "The event was recorded but did not start a new workflow because it was expired.",
                None,
                user_id=user_id,
            )
            return {"event_id": event_id, "status": "EXPIRED", "task_id": None}
        existing = self.db.fetchone(
            "SELECT * FROM events WHERE user_id=? AND dedupe_key=?",
            (user_id, scoped_key),
        )
        if existing:
            return {"event_id": existing["id"], "status": "DEDUPED", "task_id": self._task_for_event(existing["id"])}
        event_id = new_id("event")
        self.db.execute(
            """INSERT INTO events
               (id, event_type, user_id, dedupe_key, priority, payload_json, occurred_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'RECEIVED')""",
            (
                event_id,
                event_type,
                user_id,
                scoped_key,
                PRIORITY.get(event_type, 10),
                json.dumps(payload, ensure_ascii=False),
                now_iso(),
            ),
        )
        task_id = None
        if event_type in PRIORITY:
            priority = PRIORITY[event_type]
            if priority > PRIORITY["MarketClose"]:
                self.runtime.preempt_lower_priority(
                    priority,
                    f"{event_type} ({priority}) superseded a lower-priority queued task.",
                    user_id=user_id,
                )
            event_target = {
                **payload,
                "_event_type": event_type,
                "_priority": priority,
                "_event_id": event_id,
            }
            task = self.runtime.create_task(
                trigger_type=event_type,
                target=event_target,
                fixture=payload.get("fixture"),
                user_id=user_id,
            )
            task_id = task.id
            self.db.execute(
                "INSERT INTO event_deliveries(id, event_id, task_id, status) VALUES (?, ?, ?, 'DISPATCHED')",
                (new_id("delivery"), event_id, task_id),
            )
            self.db.execute("UPDATE events SET status='DISPATCHED' WHERE id=?", (event_id,))
            self._notify(
                event_type,
                f"{event_type} dispatched",
                f"A {event_type} task was created for local review.",
                task_id,
                user_id=user_id,
            )
        else:
            self._notify(
                event_type,
                f"{event_type} received",
                "The event was recorded but no workflow is configured for it.",
                None,
                user_id=user_id,
            )
        return {"event_id": event_id, "status": "DISPATCHED" if task_id else "RECEIVED", "task_id": task_id}

    def handle_task_result(self, task: Any) -> None:
        event_id = task.target.get("_event_id")
        if not event_id:
            return
        delivery = self.db.fetchone(
            """SELECT * FROM event_deliveries
               WHERE event_id=? ORDER BY attempt DESC LIMIT 1""",
            (event_id,),
        )
        if not delivery:
            return
        if task.status.value in {"FAILED", "RETRYABLE", "TIMEOUT"}:
            self.schedule_retry(event_id, str(task.error or task.status.value))
        else:
            self.db.execute(
                "UPDATE event_deliveries SET status='COMPLETED', last_error=NULL WHERE id=?",
                (delivery["id"],),
            )
            self.db.execute("UPDATE events SET status='COMPLETED' WHERE id=?", (event_id,))

    def schedule_retry(self, event_id: str, error: str, max_attempts: int = 3) -> dict[str, Any]:
        delivery = self.db.fetchone(
            """SELECT * FROM event_deliveries
               WHERE event_id=? ORDER BY attempt DESC LIMIT 1""",
            (event_id,),
        )
        if not delivery:
            raise KeyError(event_id)
        attempt = int(delivery["attempt"])
        if attempt >= max_attempts:
            self.db.execute(
                "UPDATE event_deliveries SET status='FAILED', last_error=? WHERE id=?",
                (error, delivery["id"]),
            )
            self.db.execute("UPDATE events SET status='FAILED' WHERE id=?", (event_id,))
            event = self.db.fetchone(
                "SELECT user_id FROM events WHERE id=?",
                (event_id,),
            )
            user_id = str(event["user_id"]) if event and event["user_id"] else "default"
            self._notify(
                "EventDeliveryFailed",
                "Event delivery failed",
                f"Event {event_id} exhausted its retry budget: {error}",
                None,
                user_id=user_id,
            )
            return {"event_id": event_id, "status": "FAILED", "attempt": attempt}
        delay = 2 ** max(0, attempt - 1)
        next_retry = datetime.now(timezone.utc) + timedelta(seconds=delay)
        self.db.execute(
            """UPDATE event_deliveries
               SET status='RETRY_SCHEDULED', next_retry_at=?, last_error=?
               WHERE id=?""",
            (next_retry.isoformat(), error, delivery["id"]),
        )
        self.db.execute("UPDATE events SET status='RETRY_SCHEDULED' WHERE id=?", (event_id,))
        self.db.audit(delivery["task_id"], "EVENT_RETRY_SCHEDULED", {
            "event_id": event_id,
            "attempt": attempt,
            "next_retry_at": next_retry.isoformat(),
            "error": error,
        })
        return {
            "event_id": event_id,
            "status": "RETRY_SCHEDULED",
            "attempt": attempt,
            "next_retry_at": next_retry.isoformat(),
        }

    def retry_due_events(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        rows = self.db.fetchall(
            """SELECT e.*, d.attempt
               FROM events e
               JOIN event_deliveries d ON d.event_id=e.id
               WHERE e.status='RETRY_SCHEDULED'
                 AND d.status='RETRY_SCHEDULED'
                 AND d.next_retry_at <= ?
                 AND d.attempt=(SELECT MAX(d2.attempt) FROM event_deliveries d2 WHERE d2.event_id=e.id)""",
            (now,),
        )
        dispatched = 0
        for row in rows:
            payload = json.loads(row["payload_json"])
            delivery = self.db.fetchone(
                "SELECT task_id FROM event_deliveries WHERE event_id=? ORDER BY attempt DESC LIMIT 1",
                (row["id"],),
            )
            previous_task = self.db.get_task(delivery["task_id"]) if delivery else None
            row_user_id = row["user_id"] if "user_id" in row.keys() else None
            user_id = str(row_user_id or (
                previous_task.user_id if previous_task else "default"
            ))
            event_target = {
                **payload,
                "_event_type": row["event_type"],
                "_priority": row["priority"],
                "_event_id": row["id"],
            }
            task = self.runtime.create_task(
                trigger_type=row["event_type"],
                target=event_target,
                fixture=payload.get("fixture"),
                user_id=user_id,
            )
            self.db.execute(
                "UPDATE event_deliveries SET status='RETRIED' WHERE event_id=? AND attempt=?",
                (row["id"], row["attempt"]),
            )
            self.db.execute(
                """INSERT INTO event_deliveries
                   (id, event_id, task_id, attempt, status)
                   VALUES (?, ?, ?, ?, 'DISPATCHED')""",
                (new_id("delivery"), row["id"], task.id, int(row["attempt"]) + 1),
            )
            self.db.execute("UPDATE events SET status='DISPATCHED' WHERE id=?", (row["id"],))
            dispatched += 1
        return dispatched

    @staticmethod
    def _event_time(payload: dict[str, Any]) -> datetime:
        value = payload.get("occurred_at") or payload.get("as_of")
        if value:
            if len(str(value)) == 10:
                value = f"{value}T00:00:00+00:00"
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)

    @staticmethod
    def _is_expired(payload: dict[str, Any]) -> bool:
        expires_at = payload.get("expires_at")
        if not expires_at:
            return False
        expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires <= datetime.now(timezone.utc)

    def _task_for_event(self, event_id: str) -> str | None:
        row = self.db.fetchone(
            "SELECT task_id FROM event_deliveries WHERE event_id=? ORDER BY attempt DESC LIMIT 1",
            (event_id,),
        )
        return row["task_id"] if row else None


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _max_position_weight(
    snapshot: dict[str, Any],
    rules: dict[str, Any],
) -> float:
    maximum = 0.0
    for position in snapshot.get("positions", []):
        weight = _number(position.get("weight"))
        maximum = max(maximum, weight)
    return maximum


def _has_position_breach(
    snapshot: dict[str, Any],
    rules: dict[str, Any],
) -> bool:
    for position in snapshot.get("positions", []):
        limit = (
            rules.get("max_etf_weight", 1)
            if position.get("asset_type") == "etf"
            else rules.get("max_position_weight", 1)
        )
        if _number(position.get("weight")) > float(limit):
            return True
    return False
