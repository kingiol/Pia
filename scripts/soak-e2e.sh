#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PIA_SLA_TASK_COUNT="${PIA_SLA_TASK_COUNT:-200}"
export PIA_SLA_ROOT="${PIA_SLA_ROOT:-$(mktemp -d)}"
trap 'rm -rf "$PIA_SLA_ROOT"' EXIT

echo "Running local SLA soak with ${PIA_SLA_TASK_COUNT} fixture tasks"
./scripts/sla-e2e.sh
echo "SLA SOAK PASS"
