#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

auth_token="${PIA_PUSH_ACCEPTANCE_AUTH_TOKEN:-pia-push-acceptance-token}"
port="${PIA_PUSH_ACCEPTANCE_PORT:-8892}"
root_tmp="$(mktemp -d)"
trap 'rm -rf "$root_tmp"' EXIT

platforms=()

gateway_url() {
  case "$1" in
    web) printf '%s' "${PIA_WEB_PUSH_GATEWAY_URL:-}" ;;
    ios) printf '%s' "${PIA_APNS_GATEWAY_URL:-}" ;;
    android) printf '%s' "${PIA_FCM_GATEWAY_URL:-}" ;;
  esac
}

device_token() {
  case "$1" in
    web) printf '%s' "${PIA_PUSH_ACCEPTANCE_WEB_TOKEN:-}" ;;
    ios) printf '%s' "${PIA_PUSH_ACCEPTANCE_IOS_TOKEN:-}" ;;
    android) printf '%s' "${PIA_PUSH_ACCEPTANCE_ANDROID_TOKEN:-}" ;;
  esac
}

for platform in web ios android; do
  if [[ -n "$(gateway_url "$platform")" ]]; then
    if [[ -z "$(device_token "$platform")" ]]; then
      platform_upper="$(printf '%s' "$platform" | tr '[:lower:]' '[:upper:]')"
      echo "Missing PIA_PUSH_ACCEPTANCE_${platform_upper}_TOKEN for configured ${platform} gateway" >&2
      exit 2
    fi
    platforms+=("$platform")
  fi
done

if (( ${#platforms[@]} == 0 )); then
  echo "At least one platform push gateway URL is required" >&2
  exit 2
fi
: "${PIA_POSTGRES_DSN:?PIA_POSTGRES_DSN is required for Cloud push acceptance}"

PIA_MODE=cloud \
PIA_CLOUD_AUTH_TOKEN="$auth_token" \
PIA_CLOUD_USERS="${auth_token}=default" \
PIA_PORT="$port" \
PIA_AUTOSTART_TASKS=0 \
PIA_DATA_PROVIDER=fixture \
  "$PWD/scripts/python.sh" -m pia_runtime.cli cloud \
  >"$root_tmp/cloud.log" 2>&1 &
cloud_pid=$!
cleanup() {
  kill "$cloud_pid" 2>/dev/null || true
  wait "$cloud_pid" 2>/dev/null || true
  rm -rf "$root_tmp"
}
trap cleanup EXIT

base_url="http://127.0.0.1:${port}/api"
for _ in $(seq 1 60); do
  if curl --noproxy '*' --connect-timeout 1 --max-time 2 -fsS "$base_url/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done
if ! curl --noproxy '*' --connect-timeout 1 --max-time 2 -fsS "$base_url/health" >/dev/null 2>&1; then
  cat "$root_tmp/cloud.log" >&2
  echo "Push acceptance Cloud API did not become ready" >&2
  exit 2
fi

for platform in "${platforms[@]}"; do
  payload="$("$PWD/scripts/python.sh" - "$platform" "$(device_token "$platform")" <<'PY'
import json
import sys

print(json.dumps({
    "device_id": f"push-acceptance-{sys.argv[1]}",
    "platform": sys.argv[1],
    "device_name": "Pia external push acceptance",
    "push_token": sys.argv[2],
}))
PY
)"
  curl --noproxy '*' --connect-timeout 2 --max-time 5 -fsS \
    -H "Authorization: Bearer ${auth_token}" \
    -H "Content-Type: application/json" \
    -X POST "$base_url/devices" \
    -d "$payload" >/dev/null
done

event_payload='{"event_type":"DataQualityDegraded","dedupe_key":"external-push-acceptance","payload":{"source":"release-gate","as_of":"2026-11-07","reason":"external_push_acceptance"}}'
curl --noproxy '*' --connect-timeout 2 --max-time 5 -fsS \
  -H "Authorization: Bearer ${auth_token}" \
  -H "Content-Type: application/json" \
  -X POST "$base_url/events" \
  -d "$event_payload" >/dev/null

notification_id="$(
  curl --noproxy '*' --connect-timeout 2 --max-time 5 -fsS \
    -H "Authorization: Bearer ${auth_token}" \
    "$base_url/notifications" |
    "$PWD/scripts/python.sh" -c 'import json,sys; items=json.load(sys.stdin)["notifications"]; assert items; print(items[0]["id"])'
)"
deliveries="$(
  curl --noproxy '*' --connect-timeout 2 --max-time 5 -fsS \
    -H "Authorization: Bearer ${auth_token}" \
    "$base_url/notifications/${notification_id}/deliveries"
)"
"$PWD/scripts/python.sh" - "$deliveries" "${platforms[*]}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
platforms = sys.argv[2].split()
rows = payload["deliveries"]
assert rows, "no delivery receipt was persisted"
assert any(
    row["provider_id"] == "platform-push-gateway" and row["status"] == "DELIVERED"
    for row in rows
), rows
print("EXTERNAL PUSH ACCEPTANCE PASS", ",".join(platforms), rows[0]["id"])
PY
