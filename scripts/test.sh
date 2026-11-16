#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"
"$PWD/scripts/test-runtime.sh"
"$PWD/scripts/python.sh" scripts/generate_ts_client.py --check
node --test scripts/ci_changes.test.mjs
"$PWD/scripts/python.sh" scripts/check_docs.py
git diff --check
if [ -d node_modules ]; then
  pnpm run test:desktop
  pnpm run typecheck
  pnpm run build
else
  echo "node_modules not installed; skipped frontend build"
fi
