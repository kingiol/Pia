#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"

if [ "${1:-}" = "desktop" ]; then
  export PIA_MODE=local
  export PIA_HOST=127.0.0.1
  export PIA_RUNTIME_ROOT="$PWD"
  export PIA_DB_PATH="${PIA_DB_PATH:-$PWD/.pia/debug/pia.sqlite3}"
  export PIA_MANAGED_RUNTIME=0
  export RUST_BACKTRACE="${RUST_BACKTRACE:-1}"
fi

api_port="${PIA_PORT:-8765}"
if ! "$PWD/scripts/python.sh" - "$api_port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket() as sock:
    sock.settimeout(0.2)
    try:
        sock.connect(("127.0.0.1", port))
    except OSError:
        raise SystemExit(0)
raise SystemExit(1)
PY
then
  api_port="$("$PWD/scripts/python.sh" -c 'import socket; sock=socket.socket(); sock.bind(("127.0.0.1", 0)); print(sock.getsockname()[1]); sock.close()')"
  echo "Pia API port ${PIA_PORT:-8765} is already in use; starting the local runtime on ${api_port}." >&2
fi

export PIA_PORT="$api_port"
if [ "${1:-}" = "desktop" ]; then
  export VITE_API_BASE="http://127.0.0.1:${api_port}/api"
else
  export VITE_API_BASE="${VITE_API_BASE:-http://127.0.0.1:${api_port}/api}"
fi

"$PWD/scripts/python.sh" -m pia_runtime.cli serve &
runtime_pid=$!
cleanup() {
  kill "$runtime_pid" 2>/dev/null || true
  wait "$runtime_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for _ in $(seq 1 40); do
  if curl --noproxy '*' --connect-timeout 1 --max-time 2 -fsS \
      "http://127.0.0.1:${api_port}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl --noproxy '*' --connect-timeout 1 --max-time 2 -fsS \
    "http://127.0.0.1:${api_port}/api/health" >/dev/null 2>&1; then
  echo "Pia local runtime failed to start on port ${api_port}." >&2
  exit 1
fi

if [ "${1:-}" = "desktop" ]; then
  "$PWD/scripts/desktop.sh"
else
  pnpm run dev
fi
