#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"

if [ -z "${PIA_FRESHNESS_DATES:-}" ] && [ -z "${PIA_FRESHNESS_LOOKBACK_DAYS:-}" ]; then
  echo "PROVIDER FRESHNESS SKIP (set PIA_FRESHNESS_DATES or PIA_FRESHNESS_LOOKBACK_DAYS)" >&2
  exit 2
fi

"$PWD/scripts/python.sh" scripts/provider_freshness.py
echo "PROVIDER FRESHNESS PASS"
