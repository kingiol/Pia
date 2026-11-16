from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .runtime import PiaRuntime


def run_replay(runtime: PiaRuntime, fixture_path: Path) -> dict[str, Any]:
    payload = json.loads(fixture_path.read_text())
    task_input = payload["task_input"]
    task = runtime.create_task(
        task_input["trigger_type"],
        task_input["target"],
        {
            "market": Path(task_input["market_fixture"]).name,
            "portfolio": Path(task_input["portfolio_fixture"]).name,
        },
    )
    detail = runtime.wait_for_task(task.id, timeout=10)
    if detail and detail["task"]["status"] in {
        "BLOCKED",
        "NO_ACTION",
        "WAITING_APPROVAL",
        "FAILED",
        "RETRYABLE",
        "TIMEOUT",
    }:
        return detail
    raise TimeoutError(f"replay timed out for {task.id}")
