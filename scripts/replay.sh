#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"
"$PWD/scripts/python.sh" -m pia_runtime.cli replay --fixture "${1:-tests/fixtures/replay/close-review.json}"
