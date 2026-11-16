#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"
: "${PIA_POSTGRES_DSN:?Use scripts/postgres-cloud-e2e.sh for an isolated Cloud test}"
export PIA_DATA_PROVIDER=fixture
export PIA_CLOUD_AUTH_TOKEN="${PIA_CLOUD_AUTH_TOKEN:-cloud-e2e-token}"
export PIA_CLOUD_USERS="${PIA_CLOUD_USERS:-cloud-e2e-token=default,user-b-token=user-b}"
export PIA_PORT="${PIA_PORT:-8877}"
export PIA_DB_PATH="${PIA_DB_PATH:-$(mktemp -d)/pia-cloud.sqlite3}"
"$PWD/scripts/python.sh" -m pia_runtime.cli cloud >/tmp/pia-cloud-e2e.log 2>&1 &
api_pid=$!
worker_pid=""
cleanup() {
  kill "$api_pid" ${worker_pid:+"$worker_pid"} 2>/dev/null || true
  wait "$api_pid" ${worker_pid:+"$worker_pid"} 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 30); do
  if curl --noproxy '*' --connect-timeout 1 --max-time 2 -fsS "http://127.0.0.1:${PIA_PORT}/api/health" >/dev/null 2>&1; then break; fi
  sleep 0.2
done
health="$(curl --noproxy '*' -fsS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/health")"
"$PWD/scripts/python.sh" -c 'import json,sys; assert json.load(sys.stdin)["runtime"] == "cloud"; print("CLOUD RUNTIME PASS")' <<<"$health"
unauthorized="$(curl --noproxy '*' -sS -o /tmp/pia-cloud-unauthorized.json -w '%{http_code}' "http://127.0.0.1:${PIA_PORT}/api/tasks")"
test "$unauthorized" = "401"
cors_methods="$(curl --noproxy '*' -sS -X OPTIONS -H 'Origin: http://localhost:4173' -H 'Access-Control-Request-Method: DELETE' -D - -o /dev/null "http://127.0.0.1:${PIA_PORT}/api/devices/cloud-e2e-device")"
grep -q 'GET, POST, DELETE, OPTIONS' <<<"$cors_methods"
default_rules="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/rules")"
provider_health="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/providers")"
"$PWD/scripts/python.sh" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["providers"]; assert all("provider_id" in item and "status" in item for item in payload["providers"]); print("PROVIDER HEALTH PASS")' <<<"$provider_health"
invalid_json_status="$(curl --noproxy '*' -sS -o /tmp/pia-cloud-invalid-json.json -w '%{http_code}' \
  -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/data/sync" \
  -H 'Content-Type: application/json' -d '{')"
test "$invalid_json_status" = "400"
invalid_shape_status="$(curl --noproxy '*' -sS -o /tmp/pia-cloud-invalid-shape.json -w '%{http_code}' \
  -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/data/sync" \
  -H 'Content-Type: application/json' -d '[]')"
test "$invalid_shape_status" = "400"
updated_default_rules="$("$PWD/scripts/python.sh" -c 'import json,sys; payload=json.loads(sys.stdin.read()); rules=payload["rules"]; rules["version"]="v-cloud-e2e"; print(json.dumps({"rules":rules}))' <<<"$default_rules")"
updated_rules_response="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/rules" -H 'Content-Type: application/json' -d "$updated_default_rules")"
"$PWD/scripts/python.sh" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["rules"]["version"] == "v-cloud-e2e"; print("RULESET VERSION PASS", payload["rule_snapshot_id"])' <<<"$updated_rules_response"

task_json="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks" -H 'Content-Type: application/json' -d '{"trigger_type":"MarketClose","target":{"as_of":"2026-11-05"},"fixture":{"market":"close-2026-11-05.json","portfolio":"default.json"}}')"
task_id="$("$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$task_json")"
cancel_task_json="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks" -H 'Content-Type: application/json' -d '{"trigger_type":"MarketClose","target":{"as_of":"2026-11-05"},"fixture":{"market":"close-2026-11-05.json","portfolio":"empty.json"}}')"
cancel_task_id="$("$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$cancel_task_json")"
cancel_response="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks/${cancel_task_id}/cancel" -H 'Content-Type: application/json' -d '{"reason":"cloud e2e cancellation"}')"
"$PWD/scripts/python.sh" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["task"]["status"] == "CANCELLED"; assert payload["task"]["error"]["code"] == "TASK_CANCELLED"' <<<"$cancel_response"
echo "TASK CANCEL PASS $cancel_task_id"
lease_json="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -H 'X-Worker-Id: cloud-e2e' "http://127.0.0.1:${PIA_PORT}/api/tasks/${task_id}/lease")"
lease_id="$("$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["lease_id"])' <<<"$lease_json")"
cross_user_heartbeat="$(curl --noproxy '*' -sS -o /tmp/pia-cloud-lease-heartbeat-isolation.json -w '%{http_code}' \
  -H 'Authorization: Bearer user-b-token' -X POST "http://127.0.0.1:${PIA_PORT}/api/leases/${lease_id}/heartbeat" \
  -H 'Content-Type: application/json' -d '{"worker_id":"cloud-e2e"}')"
test "$cross_user_heartbeat" = "404"
curl --noproxy '*' -fsS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/leases/${lease_id}/heartbeat" -H 'Content-Type: application/json' -d '{"worker_id":"cloud-e2e"}' >/dev/null
curl --noproxy '*' -fsS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/leases/${lease_id}/release" -H 'Content-Type: application/json' -d '{"worker_id":"cloud-e2e"}' >/dev/null
PIA_WORKER_POLL_SECONDS="${PIA_WORKER_POLL_SECONDS:-0.1}" \
PIA_TASK_EXECUTION_DELAY_SECONDS="${PIA_TASK_EXECUTION_DELAY_SECONDS:-1.0}" \
  "$PWD/scripts/python.sh" -m pia_runtime.cli worker --worker-id cloud-e2e >/tmp/pia-cloud-worker-e2e.log 2>&1 &
worker_pid=$!
control_task_json="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks" -H 'Content-Type: application/json' \
  -d '{"trigger_type":"MarketClose","target":{"as_of":"2026-11-05","suggested_action":"BUY_CANDIDATE"},"fixture":{"market":"close-2026-11-05.json","portfolio":"empty.json"}}')"
control_task_id="$("$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$control_task_json")"
for _ in $(seq 1 30); do
  control_status="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
    "http://127.0.0.1:${PIA_PORT}/api/tasks/${control_task_id}" |
    "$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')"
  case "$control_status" in PLANNING|RUNNING|REVIEWING) break;; esac
  sleep 0.2
done
test "$control_status" = "RUNNING" -o "$control_status" = "PLANNING" -o "$control_status" = "REVIEWING"
paused_control="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks/${control_task_id}/pause")"
"$PWD/scripts/python.sh" -c 'import json,sys; assert json.load(sys.stdin)["task"]["status"] == "PAUSED"' <<<"$paused_control"
sleep 0.5
paused_status="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  "http://127.0.0.1:${PIA_PORT}/api/tasks/${control_task_id}" |
  "$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')"
test "$paused_status" = "PAUSED"
resumed_control="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks/${control_task_id}/resume")"
"$PWD/scripts/python.sh" -c 'import json,sys; assert json.load(sys.stdin)["task"]["status"] == "RUNNING"' <<<"$resumed_control"
for _ in $(seq 1 40); do
  resumed_status="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
    "http://127.0.0.1:${PIA_PORT}/api/tasks/${control_task_id}" |
    "$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')"
  case "$resumed_status" in BLOCKED|NO_ACTION|WAITING_APPROVAL|FAILED|RETRYABLE|TIMEOUT|EXPIRED|DONE) break;; esac
  sleep 0.2
done
test "$resumed_status" = "WAITING_APPROVAL"
echo "CROSS-PROCESS PAUSE RESUME PASS $control_task_id"
for _ in $(seq 1 30); do
  task_status="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/tasks/${task_id}" | "$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')"
  case "$task_status" in BLOCKED|NO_ACTION|WAITING_APPROVAL|FAILED|RETRYABLE|TIMEOUT) break;; esac
  sleep 0.2
done
test "$task_status" = "BLOCKED"
task_data="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  "http://127.0.0.1:${PIA_PORT}/api/tasks/${task_id}/data")"
"$PWD/scripts/python.sh" -c 'import json,sys; d=json.load(sys.stdin); assert d["task_id"] == sys.argv[1]; assert d["bundles"]; assert any(bundle["raw_payloads"] for bundle in d["bundles"]); print("TASK DATA PASS", sys.argv[1])' "$task_id" <<<"$task_data"
replay_task="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks/${task_id}/replay")"
"$PWD/scripts/python.sh" -c 'import json,sys; task=json.load(sys.stdin)["task"]; assert task["parent_task_id"] == sys.argv[1]; assert task["target"]["_replay_of"] == sys.argv[1]; print("REPLAY PASS", task["id"])' "$task_id" <<<"$replay_task"
approval_task_json="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks" \
  -H 'Content-Type: application/json' \
  -d '{"trigger_type":"MarketClose","target":{"as_of":"2026-11-05","suggested_action":"BUY_CANDIDATE"},"fixture":{"market":"close-2026-11-05.json","portfolio":"empty.json"}}')"
approval_task_id="$("$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$approval_task_json")"
for _ in $(seq 1 30); do
  approval_status="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
    "http://127.0.0.1:${PIA_PORT}/api/tasks/${approval_task_id}" |
    "$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')"
  [ "$approval_status" = "WAITING_APPROVAL" ] && break
  sleep 0.2
done
test "$approval_status" = "WAITING_APPROVAL"
approved="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks/${approval_task_id}/approve" \
  -H 'Content-Type: application/json' \
  -d '{"action":"NO_ACTION","notes":"cloud e2e research review"}')"
"$PWD/scripts/python.sh" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["task"]["status"] == "NO_ACTION"; assert payload["approval_id"]; print("RESEARCH REVIEW E2E PASS", payload["task"]["id"])' <<<"$approved"

watch_task_json="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks" \
  -H 'Content-Type: application/json' \
  -d '{"trigger_type":"StockResearch","target":{"as_of":"2026-11-05","symbol":"600000.SH","suggested_action":"BUY_CANDIDATE"},"fixture":{"market":"close-2026-11-05.json","portfolio":"empty.json"}}')"
watch_task_id="$("$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$watch_task_json")"
for _ in $(seq 1 30); do
  watch_status="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
    "http://127.0.0.1:${PIA_PORT}/api/tasks/${watch_task_id}" |
    "$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')"
  [ "$watch_status" = "WAITING_APPROVAL" ] && break
  sleep 0.2
done
test "$watch_status" = "WAITING_APPROVAL"
watch_result="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks/${watch_task_id}/approve" \
  -H 'Content-Type: application/json' \
  -d '{"action":"MARK_AS_WATCH","notes":"cloud e2e watch"}')"
"$PWD/scripts/python.sh" -c 'import json,sys; d=json.load(sys.stdin); assert d["task"]["status"] == "NO_ACTION"; assert "600000.SH" in d["watchlist"]["symbols"]; print("MARK AS WATCH PASS", d["task"]["id"])' <<<"$watch_result"

invalid_status="$(curl --noproxy '*' -sS -o /tmp/pia-cloud-invalid.json -w '%{http_code}' -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/profile" -H 'Content-Type: application/json' -d '{"payload":{"risk_tolerance":"low"}}')"
test "$invalid_status" = "400"
curl --noproxy '*' -fsS -H 'Authorization: Bearer user-b-token' -X POST "http://127.0.0.1:${PIA_PORT}/api/profile" -H 'Content-Type: application/json' -d '{"payload":{"risk_tolerance":"low","investment_objective":"preserve capital","allowed_asset_types":["stock"],"universe":["main"]}}' >/dev/null
curl --noproxy '*' -fsS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/portfolio/import" \
  -H 'Content-Type: application/json' \
  -d '{"format":"manual","content":[{"symbol":"600000.SH","quantity":10,"avg_cost":10,"market_value":100}]}' >/dev/null
curl --noproxy '*' -fsS -H 'Authorization: Bearer user-b-token' -X POST "http://127.0.0.1:${PIA_PORT}/api/portfolio/import" \
  -H 'Content-Type: application/json' \
  -d '{"format":"manual","content":[{"symbol":"510300.SH","quantity":10,"avg_cost":5,"market_value":100}]}' >/dev/null
default_portfolio="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/portfolio")"
"$PWD/scripts/python.sh" -c 'import json,sys; assert json.load(sys.stdin)["positions"][0]["symbol"] == "600000.SH"' <<<"$default_portfolio"
user_b_portfolio="$(curl --noproxy '*' -sS -H 'Authorization: Bearer user-b-token' "http://127.0.0.1:${PIA_PORT}/api/portfolio")"
"$PWD/scripts/python.sh" -c 'import json,sys; assert json.load(sys.stdin)["positions"][0]["symbol"] == "510300.SH"' <<<"$user_b_portfolio"
echo "PORTFOLIO ISOLATION PASS"
default_audit="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/audit")"
"$PWD/scripts/python.sh" -c 'import json,sys; rows=json.load(sys.stdin)["audit"]; assert rows and all(row["user_id"] == "default" for row in rows)' <<<"$default_audit"
user_b_audit="$(curl --noproxy '*' -sS -H 'Authorization: Bearer user-b-token' "http://127.0.0.1:${PIA_PORT}/api/audit")"
"$PWD/scripts/python.sh" -c 'import json,sys; rows=json.load(sys.stdin)["audit"]; assert rows and all(row["user_id"] == "user-b" for row in rows)' <<<"$user_b_audit"
echo "AUDIT ISOLATION PASS"
user_b_task_json="$(curl --noproxy '*' -sS -H 'Authorization: Bearer user-b-token' -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks" -H 'Content-Type: application/json' -d '{"trigger_type":"MarketClose","target":{"as_of":"2026-11-05"},"fixture":{"market":"close-2026-11-05.json","portfolio":"empty.json"}}')"
user_b_task_id="$("$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$user_b_task_json")"
default_tasks="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/tasks")"
"$PWD/scripts/python.sh" -c 'import json,sys; ids={task["id"] for task in json.load(sys.stdin)["tasks"]}; assert sys.argv[1] not in ids' "$user_b_task_id" <<<"$default_tasks"
user_b_tasks="$(curl --noproxy '*' -sS -H 'Authorization: Bearer user-b-token' "http://127.0.0.1:${PIA_PORT}/api/tasks")"
"$PWD/scripts/python.sh" -c 'import json,sys; ids={task["id"] for task in json.load(sys.stdin)["tasks"]}; assert sys.argv[1] in ids' "$user_b_task_id" <<<"$user_b_tasks"
for _ in $(seq 1 30); do
  user_b_status="$(curl --noproxy '*' -sS -H 'Authorization: Bearer user-b-token' \
    "http://127.0.0.1:${PIA_PORT}/api/tasks/${user_b_task_id}" |
    "$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')"
  [ "$user_b_status" = "WAITING_APPROVAL" ] && break
  sleep 0.2
done
test "$user_b_status" = "WAITING_APPROVAL"
user_b_approved="$(curl --noproxy '*' -sS -H 'Authorization: Bearer user-b-token' \
  -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks/${user_b_task_id}/approve" \
  -H 'Content-Type: application/json' \
  -d '{"action":"NO_ACTION","notes":"user-b cloud e2e research review"}')"
"$PWD/scripts/python.sh" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["task"]["status"] == "NO_ACTION"; assert payload["approval_id"]; print("USER B REVIEW PASS", payload["task"]["id"])' <<<"$user_b_approved"
user_b_approval_audit="$(curl --noproxy '*' -sS -H 'Authorization: Bearer user-b-token' "http://127.0.0.1:${PIA_PORT}/api/audit")"
"$PWD/scripts/python.sh" -c 'import json,sys; rows=json.load(sys.stdin)["audit"]; assert any(row["event_type"] == "APPROVAL_RECORDED" for row in rows)' <<<"$user_b_approval_audit"
user_b_retrospective="$(curl --noproxy '*' -sS -H 'Authorization: Bearer user-b-token' \
  -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks/${user_b_task_id}/retrospectives" \
  -H 'Content-Type: application/json' \
  -d '{"action_taken":"APPROVE","outcome":{"status":"positive","return_pct":2.5},"notes":"user-b retrospective"}')"
"$PWD/scripts/python.sh" -c 'import json,sys; value=json.load(sys.stdin); assert value["user_id"] == "user-b"; assert value["outcome"]["status"] == "positive"; print("USER B RETROSPECTIVE PASS", value["id"])' <<<"$user_b_retrospective"
user_b_retrospectives="$(curl --noproxy '*' -sS -H 'Authorization: Bearer user-b-token' "http://127.0.0.1:${PIA_PORT}/api/tasks/${user_b_task_id}/retrospectives")"
"$PWD/scripts/python.sh" -c 'import json,sys; rows=json.load(sys.stdin)["retrospectives"]; assert rows and rows[0]["user_id"] == "user-b"' <<<"$user_b_retrospectives"
default_retrospective_status="$(curl --noproxy '*' -sS -o /tmp/pia-cloud-retrospective-isolation.json -w '%{http_code}' \
  -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/tasks/${user_b_task_id}/retrospectives")"
test "$default_retrospective_status" = "404"

default_notifications="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/notifications")"
default_notification_id="$("$PWD/scripts/python.sh" -c 'import json,sys; items=json.load(sys.stdin)["notifications"]; assert items; print(items[0]["id"])' <<<"$default_notifications")"
default_deliveries="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/notifications/${default_notification_id}/deliveries")"
"$PWD/scripts/python.sh" -c 'import json,sys; rows=json.load(sys.stdin)["deliveries"]; assert rows and all(row["user_id"] == "default" for row in rows); print("NOTIFICATION DELIVERY PASS", sys.argv[1])' "$default_notification_id" <<<"$default_deliveries"
user_b_delivery_status="$(curl --noproxy '*' -sS -o /tmp/pia-cloud-delivery-isolation.json -w '%{http_code}' -H 'Authorization: Bearer user-b-token' "http://127.0.0.1:${PIA_PORT}/api/notifications/${default_notification_id}/deliveries")"
test "$user_b_delivery_status" = "404"

default_device="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/devices" -H 'Content-Type: application/json' -d '{"device_id":"cloud-e2e-device","platform":"web","device_name":"Default browser"}')"
"$PWD/scripts/python.sh" -c 'import json,sys; assert json.load(sys.stdin)["user_id"] == "default"' <<<"$default_device"
default_devices="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/devices")"
"$PWD/scripts/python.sh" -c 'import json,sys; ids={item["device_id"] for item in json.load(sys.stdin)["devices"]}; assert "cloud-e2e-device" in ids' <<<"$default_devices"
device_conflict="$(curl --noproxy '*' -sS -o /tmp/pia-cloud-device-conflict.json -w '%{http_code}' -H 'Authorization: Bearer user-b-token' -X POST "http://127.0.0.1:${PIA_PORT}/api/devices" -H 'Content-Type: application/json' -d '{"device_id":"cloud-e2e-device","platform":"web"}')"
test "$device_conflict" = "409"

curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -X POST "http://127.0.0.1:${PIA_PORT}/api/events" \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"MarketBreadthChanged","dedupe_key":"cloud-event-isolation","payload":{"as_of":"2026-11-05","breadth":0.8}}' >/dev/null
curl --noproxy '*' -sS -H 'Authorization: Bearer user-b-token' -X POST "http://127.0.0.1:${PIA_PORT}/api/events" \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"MarketBreadthChanged","dedupe_key":"cloud-event-isolation","payload":{"as_of":"2026-11-05","breadth":0.2}}' >/dev/null
default_events="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/events")"
"$PWD/scripts/python.sh" -c 'import json,sys; events=json.load(sys.stdin)["events"]; assert events and all(event["user_id"] == "default" for event in events)' <<<"$default_events"
user_b_events="$(curl --noproxy '*' -sS -H 'Authorization: Bearer user-b-token' "http://127.0.0.1:${PIA_PORT}/api/events")"
"$PWD/scripts/python.sh" -c 'import json,sys; events=json.load(sys.stdin)["events"]; assert events and all(event["user_id"] == "user-b" for event in events)' <<<"$user_b_events"
echo "EVENT ISOLATION PASS"

idempotent_body='{"trigger_type":"MarketClose","target":{"as_of":"2026-11-05"},"fixture":{"market":"close-2026-11-05.json","portfolio":"empty.json"}}'
idempotent_first="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -H 'Idempotency-Key: cloud-e2e-idempotent' -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks" -H 'Content-Type: application/json' -d "$idempotent_body")"
idempotent_second="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -H 'Idempotency-Key: cloud-e2e-idempotent' -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks" -H 'Content-Type: application/json' -d "$idempotent_body")"
"$PWD/scripts/python.sh" -c 'import json,sys; assert json.load(sys.stdin)["task"]["id"] == sys.argv[1]' "$("$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$idempotent_first")" <<<"$idempotent_second"
idempotent_conflict="$(curl --noproxy '*' -sS -o /tmp/pia-cloud-idempotency-conflict.json -w '%{http_code}' -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" -H 'Idempotency-Key: cloud-e2e-idempotent' -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks" -H 'Content-Type: application/json' -d '{"trigger_type":"StockResearch","target":{"as_of":"2026-11-05","symbol":"600000.SH"},"fixture":{"market":"close-2026-11-05.json","portfolio":"empty.json"}}')"
test "$idempotent_conflict" = "409"

default_sync="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/sync?cursor=0&limit=500")"
"$PWD/scripts/python.sh" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["next_cursor"] >= payload["cursor"]; assert all(change.get("payload", {}).get("user_id", "default") == "default" for change in payload["changes"])' <<<"$default_sync"
cloud_metrics="$(curl --noproxy '*' -sS -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" "http://127.0.0.1:${PIA_PORT}/api/metrics")"
"$PWD/scripts/python.sh" -c 'import json,os,sys; payload=json.load(sys.stdin); system=payload["system"]; expected_backend="postgres" if os.environ.get("PIA_POSTGRES_DSN") else "sqlite"; assert payload["user_id"] == "default"; assert isinstance(system["queue_depth"], int); assert isinstance(system["active_task_count"], int); assert "oldest_active_task_age_seconds" in system; assert set(system["storage_bytes"]) >= {"database", "analytics_database"}; assert system["database_backend"] == expected_backend; print("CLOUD METRICS PASS", system["active_task_count"])' <<<"$cloud_metrics"
echo "CLOUD E2E PASS $task_id"
