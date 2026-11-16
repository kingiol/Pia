from __future__ import annotations

import io
import json
import unittest

from pia_runtime.observability import RuntimeObservability


class ObservabilityTest(unittest.TestCase):
    def test_snapshot_tracks_request_count_errors_and_p95(self):
        stream = io.StringIO()
        observability = RuntimeObservability(enabled=True, stream=stream)
        observability.record_request("GET", "/api/health", 200, 4.0)
        observability.record_request("POST", "/api/tasks", 500, 12.0)

        snapshot = observability.snapshot()

        self.assertEqual(snapshot["request_count"], 2)
        self.assertEqual(snapshot["error_count"], 1)
        self.assertEqual(snapshot["request_p95_ms"], 12.0)
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(records[1]["event"], "http_request")
        self.assertEqual(records[1]["status"], 500)

    def test_logs_redact_credentials(self):
        stream = io.StringIO()
        observability = RuntimeObservability(enabled=True, stream=stream)
        observability.log("info", "credentials", api_key="secret", authorization="Bearer token")

        payload = json.loads(stream.getvalue())

        self.assertEqual(payload["api_key"], "[REDACTED]")
        self.assertEqual(payload["authorization"], "[REDACTED]")

    def test_snapshot_tracks_worker_heartbeat(self):
        observability = RuntimeObservability()
        observability.record_worker_heartbeat("worker-a")

        snapshot = observability.snapshot()

        self.assertIn("worker-a", snapshot["worker_heartbeats"])
        self.assertGreaterEqual(snapshot["worker_heartbeats"]["worker-a"]["age_seconds"], 0)

    def test_snapshot_tracks_provider_call_latency_and_errors(self):
        observability = RuntimeObservability()
        observability.record_provider_call(
            "market_snapshot",
            "primary",
            "get_market_snapshot",
            8.0,
            success=False,
            error=TimeoutError("token=secret-value upstream timeout"),
        )
        observability.record_provider_call(
            "market_snapshot",
            "secondary",
            "get_market_snapshot",
            4.0,
            success=True,
        )

        snapshot = observability.snapshot()

        primary = snapshot["provider_calls"]["primary:market_snapshot:get_market_snapshot"]
        secondary = snapshot["provider_calls"]["secondary:market_snapshot:get_market_snapshot"]
        self.assertEqual(primary["error_count"], 1)
        self.assertEqual(primary["error_rate"], 1.0)
        self.assertEqual(primary["last_status"], "error")
        self.assertNotIn("secret-value", primary["last_error"])
        self.assertIn("[REDACTED]", primary["last_error"])
        self.assertEqual(secondary["p95_ms"], 4.0)


if __name__ == "__main__":
    unittest.main()
