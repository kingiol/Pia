from __future__ import annotations

import json
import math
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, TextIO

from .models import now_iso
from .security import redact_secrets


@dataclass(slots=True)
class RuntimeObservability:
    """Small, dependency-free observability surface for local and cloud runtimes."""

    enabled: bool = False
    service: str = "pia-runtime"
    stream: TextIO = field(default_factory=lambda: sys.stderr)
    _lock: threading.RLock = field(init=False, repr=False)
    _started_monotonic: float = field(init=False, repr=False)
    _request_count: int = field(init=False, repr=False)
    _error_count: int = field(init=False, repr=False)
    _durations_ms: list[float] = field(init=False, repr=False)
    _worker_heartbeats: dict[str, float] = field(init=False, repr=False)
    _provider_calls: dict[str, dict[str, Any]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self._started_monotonic = time.monotonic()
        self._request_count = 0
        self._error_count = 0
        self._durations_ms: list[float] = []
        self._worker_heartbeats: dict[str, float] = {}
        self._provider_calls: dict[str, dict[str, Any]] = {}

    def record_worker_heartbeat(self, worker_id: str) -> None:
        with self._lock:
            self._worker_heartbeats[worker_id] = time.time()

    def record_provider_call(
        self,
        capability: str,
        provider_id: str,
        method: str,
        duration_ms: float,
        *,
        success: bool,
        error: BaseException | None = None,
    ) -> None:
        """Record one provider route attempt for capability-level diagnostics."""
        key = f"{provider_id}:{capability}:{method}"
        with self._lock:
            entry = self._provider_calls.setdefault(
                key,
                {
                    "provider_id": provider_id,
                    "capability": capability,
                    "method": method,
                    "call_count": 0,
                    "error_count": 0,
                    "durations_ms": [],
                    "last_error": None,
                    "last_status": None,
                },
            )
            entry["call_count"] += 1
            if not success:
                entry["error_count"] += 1
                entry["last_error"] = (
                    str(redact_secrets(f"{type(error).__name__}: {error}"))
                    if error
                    else "provider call failed"
                )
            entry["last_status"] = "ok" if success else "error"
            durations = entry["durations_ms"]
            durations.append(round(max(0.0, duration_ms), 3))
            if len(durations) > 256:
                del durations[:-256]
        self.log(
            "error" if not success else "info",
            "provider_call",
            provider_id=provider_id,
            capability=capability,
            method=method,
            status="ok" if success else "error",
            duration_ms=round(max(0.0, duration_ms), 3),
            error_type=type(error).__name__ if error else None,
            error=str(error) if error else None,
        )

    def log(self, level: str, event: str, **fields: Any) -> None:
        if not self.enabled:
            return
        payload = {
            "timestamp": now_iso(),
            "level": level,
            "service": self.service,
            "event": event,
            **redact_secrets(fields),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=self.stream, flush=True)

    def record_request(
        self,
        method: str,
        path: str,
        status: int,
        duration_ms: float,
    ) -> None:
        with self._lock:
            self._request_count += 1
            if status >= 500:
                self._error_count += 1
            self._durations_ms.append(round(max(0.0, duration_ms), 3))
            if len(self._durations_ms) > 512:
                del self._durations_ms[:-512]
        self.log(
            "error" if status >= 500 else "info",
            "http_request",
            method=method,
            path=path,
            status=status,
            duration_ms=round(max(0.0, duration_ms), 3),
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            durations = sorted(self._durations_ms)
            p95 = None
            if durations:
                p95 = round(durations[min(len(durations) - 1, math.ceil(len(durations) * 0.95) - 1)], 3)
            now = time.time()
            worker_heartbeats = {
                worker_id: {
                    "last_seen_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ",
                        time.gmtime(last_seen),
                    ),
                    "age_seconds": round(max(0.0, now - last_seen), 3),
                }
                for worker_id, last_seen in self._worker_heartbeats.items()
            }
            provider_calls = {}
            for key, entry in self._provider_calls.items():
                durations_ms = sorted(entry["durations_ms"])
                p95 = None
                if durations_ms:
                    p95 = round(
                        durations_ms[
                            min(
                                len(durations_ms) - 1,
                                math.ceil(len(durations_ms) * 0.95) - 1,
                            )
                        ],
                        3,
                    )
                call_count = int(entry["call_count"])
                error_count = int(entry["error_count"])
                provider_calls[key] = {
                    "provider_id": entry["provider_id"],
                    "capability": entry["capability"],
                    "method": entry["method"],
                    "call_count": call_count,
                    "error_count": error_count,
                    "error_rate": round(error_count / call_count, 4)
                    if call_count
                    else 0.0,
                    "p95_ms": p95,
                    "last_error": entry["last_error"],
                    "last_status": entry["last_status"],
                }
            return {
                "service": self.service,
                "structured_logs": self.enabled,
                "uptime_seconds": round(max(0.0, time.monotonic() - self._started_monotonic), 3),
                "request_count": self._request_count,
                "error_count": self._error_count,
                "request_p95_ms": p95,
                "worker_heartbeats": worker_heartbeats,
                "provider_calls": provider_calls,
            }
