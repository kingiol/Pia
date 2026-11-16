from __future__ import annotations

import threading
from datetime import datetime, time as clock_time
from typing import Any
from zoneinfo import ZoneInfo


class LocalMarketScheduler:
    """Trigger one MarketClose event per trading weekday at the configured local time."""

    def __init__(
        self,
        runtime: Any,
        *,
        timezone_name: str = "Asia/Shanghai",
        close_time: str = "15:05",
        poll_seconds: float = 15.0,
    ) -> None:
        self.runtime = runtime
        self.timezone = ZoneInfo(timezone_name)
        hour, minute = (int(item) for item in close_time.split(":", 1))
        self.close_time = clock_time(hour, minute)
        self.poll_seconds = max(1.0, poll_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_dispatched_date: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="pia-local-scheduler",
        )
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=timeout)
        self._thread = None

    def health(self) -> dict[str, Any]:
        return {
            "enabled": bool(self._thread and self._thread.is_alive()),
            "timezone": str(self.timezone),
            "close_time": self.close_time.strftime("%H:%M"),
            "last_dispatched_date": self._last_dispatched_date,
        }

    def dispatch_if_due(self, now: datetime | None = None) -> dict[str, Any] | None:
        current = (now or datetime.now(self.timezone)).astimezone(self.timezone)
        if current.weekday() >= 5 or current.time() < self.close_time:
            return None
        current_date = current.date().isoformat()
        is_trading_day = getattr(self.runtime, "is_trading_day", None)
        if is_trading_day and not is_trading_day(current_date):
            return None
        if self._last_dispatched_date == current_date:
            return None
        user_ids = self._user_ids()
        settings = getattr(self.runtime, "settings", None)
        sync_result: dict[str, Any] | None = None
        if getattr(settings, "data_provider", "fixture") != "fixture":
            try:
                sync_result = self.runtime.sync_market_data(
                    current_date,
                    list(getattr(settings, "scheduler_symbols", [])),
                )
                if (
                    sync_result.get("quality") != "verified"
                    or sync_result.get("failures")
                ):
                    for user_id in user_ids:
                        self._report_data_quality(
                            current_date,
                            "Data synchronization completed with degraded quality.",
                            sync_result,
                            user_id=user_id,
                        )
            except Exception as error:
                self.runtime.db.audit(None, "DATA_SYNC_FAILED", {
                    "as_of": current_date,
                    "error": type(error).__name__,
                    "message": str(error),
                })
                for user_id in user_ids:
                    self._report_data_quality(
                        current_date,
                        "Data synchronization failed before the market-close workflow.",
                        {
                            "error": type(error).__name__,
                            "message": str(error),
                        },
                        user_id=user_id,
                    )
        payload = {
            "as_of": current_date,
            "occurred_at": current.isoformat(),
            "_market_snapshot_id": (
                sync_result.get("snapshot_id")
                if sync_result
                else None
            ),
        }
        results = []
        for user_id in user_ids:
            dedupe_key = f"market-close:{current_date}"
            if user_id != "default":
                dedupe_key = f"{dedupe_key}:{user_id}"
            if user_id == "default" and getattr(settings, "mode", "local") != "cloud":
                result = self.runtime.ingest_event(
                    "MarketClose",
                    payload,
                    dedupe_key=dedupe_key,
                )
            else:
                result = self.runtime.ingest_event(
                    "MarketClose",
                    payload,
                    dedupe_key=dedupe_key,
                    user_id=user_id,
                )
            results.append(result)
        self._last_dispatched_date = current_date
        if len(results) == 1:
            return results[0]
        return {
            "status": "DISPATCHED",
            "as_of": current_date,
            "user_ids": user_ids,
            "results": results,
        }

    def _user_ids(self) -> list[str]:
        settings = getattr(self.runtime, "settings", None)
        if getattr(settings, "mode", "local") != "cloud":
            return ["default"]
        database = getattr(self.runtime, "db", None)
        list_user_ids = getattr(database, "list_user_ids", None)
        if callable(list_user_ids):
            users = [str(user_id) for user_id in list_user_ids() if str(user_id).strip()]
            if users:
                return users
        return ["default"]

    def _report_data_quality(
        self,
        as_of: str,
        message: str,
        detail: dict[str, Any],
        *,
        user_id: str = "default",
    ) -> None:
        events = getattr(self.runtime, "events", None)
        ingest = getattr(events, "ingest", None)
        if ingest:
            try:
                ingest(
                    "DataQualityDegraded",
                    {
                        "as_of": as_of,
                        "occurred_at": datetime.now(self.timezone).isoformat(),
                        "quality": "partial",
                        "reason": message,
                        "detail": detail,
                    },
                    dedupe_key=(
                        f"data-quality:{as_of}"
                        if user_id == "default"
                        else f"data-quality:{as_of}:{user_id}"
                    ),
                    user_id=user_id,
                )
            except Exception as error:
                self.runtime.db.audit(None, "DATA_QUALITY_EVENT_FAILED", {
                    "as_of": as_of,
                    "error": type(error).__name__,
                    "message": str(error),
                })
        notify = getattr(events, "notify", None)
        if notify and not ingest:
            notify(
                "DataQualityDegraded",
                "Pia data quality degraded",
                f"{message} as_of={as_of}.",
                None,
                user_id=user_id,
            )
        self.runtime.db.audit(None, "DATA_SYNC_DEGRADED", {
            "as_of": as_of,
            "message": message,
            "detail": detail,
        }, user_id=user_id)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.dispatch_if_due()
            except Exception as error:
                self.runtime.db.audit(
                    None,
                    "SCHEDULER_ERROR",
                    {"error": type(error).__name__, "message": str(error)},
                )
            self._stop.wait(self.poll_seconds)
