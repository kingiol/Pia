#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"
"$PWD/scripts/python.sh" -m unittest discover -s tests -p 'test_*.py' -v
"$PWD/scripts/python.sh" -m compileall -q packages-py/pia_runtime
"$PWD/scripts/python.sh" scripts/generate_runtime_schemas.py --check
