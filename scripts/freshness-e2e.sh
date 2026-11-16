#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHONPATH="$PWD/packages-py/pia_runtime" ./scripts/python.sh - <<'PY'
from datetime import datetime, timezone

from pia_runtime.data_quality import validate_snapshot, validate_temporal_metadata

now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
cases = [
    (
        "valid",
        {
            "as_of": "2026-11-06",
            "observed_at": "2026-11-06T16:00:00+08:00",
        },
        True,
    ),
    (
        "future_as_of",
        {
            "as_of": "2099-01-02",
            "observed_at": "2099-01-02T16:00:00+08:00",
        },
        False,
    ),
    (
        "observed_before_as_of",
        {
            "as_of": "2026-11-06",
            "observed_at": "2026-11-05T16:00:00+08:00",
        },
        False,
    ),
    (
        "expired",
        {
            "as_of": "2026-11-05",
            "observed_at": "2026-11-05T16:00:00+08:00",
            "expires_at": "2026-11-06T00:00:00+00:00",
        },
        False,
    ),
    (
        "future_publication",
        {
            "as_of": "2026-11-06",
            "observed_at": "2026-11-06T16:00:00+08:00",
            "published_at": "2026-11-08T09:00:00+08:00",
        },
        False,
    ),
]

for _ in range(200):
    for name, payload, expected in cases:
        result = validate_temporal_metadata(
            payload,
            now=now,
            published_field="published_at" if "published_at" in payload else None,
        )
        if result["valid"] != expected:
            raise SystemExit(f"{name}: unexpected result {result}")

market = {
    "snapshot_id": "freshness-market",
    "as_of": "2099-01-02",
    "observed_at": "2099-01-02T16:00:00+08:00",
    "source": "soak",
    "quality": "verified",
    "breadth": 0.5,
    "index_trend": "flat",
    "volatility": 0.2,
}
snapshot = validate_snapshot(market, "market")
if snapshot["quality"] != "unavailable" or snapshot["valid"]:
    raise SystemExit(f"future snapshot was not blocked: {snapshot}")

print("FRESHNESS E2E PASS cases=1000")
PY
