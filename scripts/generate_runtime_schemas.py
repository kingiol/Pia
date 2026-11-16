#!/usr/bin/env python3
"""Export runtime-validated contracts as JSON Schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pia_runtime.decision_context import DecisionContextPack
from pia_runtime.decision_synthesizer import AgentOpinion
from pia_runtime.run_flow import RunFlow
from pia_runtime.screening import ScreeningStrategy
from pia_runtime.result_metadata import ResultMetadata


ROOT = Path(__file__).resolve().parents[1]


def inline_definitions(schema: dict) -> dict:
    definitions = schema.pop("$defs", {})

    def visit(value):
        if isinstance(value, dict):
            if "$ref" in value and value["$ref"].startswith("#/$defs/"):
                return visit(definitions[value["$ref"].split("/")[-1]])
            return {key: visit(item) for key, item in value.items()}
        if isinstance(value, list):
            return [visit(item) for item in value]
        return value

    return visit(schema)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    models = {"decision-context-pack": DecisionContextPack, "agent-opinion": AgentOpinion,
              "run-flow": RunFlow, "screening-strategy": ScreeningStrategy,
              "result-metadata": ResultMetadata}
    for name, model in models.items():
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                  **inline_definitions(model.model_json_schema())}
        output = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
        path = ROOT / "contracts" / "schemas" / f"{name}.json"
        if args.check:
            if not path.exists() or path.read_text() != output:
                raise SystemExit(f"Outdated runtime schema: {path.name}")
        else:
            path.write_text(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
