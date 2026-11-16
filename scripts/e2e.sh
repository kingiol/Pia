#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"
export PIA_DB_PATH="${PIA_DB_PATH:-$(mktemp -d)/pia-e2e.sqlite3}"
export PIA_DUCKDB_PATH="${PIA_DUCKDB_PATH:-${PIA_DB_PATH%.sqlite3}.duckdb}"
export PIA_DATA_PROVIDER=fixture
"$PWD/scripts/python.sh" -m pia_runtime.cli serve >/tmp/pia-local-runtime.log 2>&1 &
runtime_pid=$!
trap 'kill "$runtime_pid" 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do
  if curl --noproxy '*' --connect-timeout 1 --max-time 2 -fsS http://127.0.0.1:8765/api/health >/dev/null 2>&1; then break; fi
  sleep 0.2
done
sync_json="$(curl --noproxy '*' --connect-timeout 1 --max-time 10 -fsS -X POST http://127.0.0.1:8765/api/data/sync \
  -H 'Content-Type: application/json' \
  -d '{"as_of":"2026-11-05","symbols":["600000.SH"]}')"
market_json="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS http://127.0.0.1:8765/api/market)"
python3 -c 'import json,sys; sync=json.loads(sys.argv[1]); market=json.loads(sys.argv[2]); assert sync["market_snapshot"]["snapshot_id"] == market["snapshot_id"]; print("DATA SYNC MARKET PASS", market["snapshot_id"])' "$sync_json" "$market_json"
invalid_json_status="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -sS -o /tmp/pia-local-invalid-json.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8765/api/data/sync -H 'Content-Type: application/json' -d '{')"
test "$invalid_json_status" = "400"
invalid_shape_status="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -sS -o /tmp/pia-local-invalid-shape.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8765/api/data/sync -H 'Content-Type: application/json' -d '[]')"
test "$invalid_shape_status" = "400"
watchlist="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST http://127.0.0.1:8765/api/watchlists \
  -H 'Content-Type: application/json' \
  -d '{"name":"Core","symbols":["600000.SH","510300.SH"]}')"
python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); assert d["name"] == "Core"; assert d["symbols"] == ["510300.SH","600000.SH"]; print("WATCHLIST PASS", d["id"])' <<<"$watchlist"
memory="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST http://127.0.0.1:8765/api/memory \
  -H 'Content-Type: application/json' \
  -d '{"kind":"fact","symbol":"600000.SH","title":"E2E memory","content":"Capital ratio is stable.","source":"fixture://e2e","as_of":"2026-11-05","quality":"verified"}')"
memory_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["quality"] == "verified"; print(d["id"])' <<<"$memory")"
memory_search="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS 'http://127.0.0.1:8765/api/memory?q=capital&symbol=600000.SH')"
python3 -c 'import json,sys; rows=json.load(sys.stdin)["memories"]; assert any(item["id"] == sys.argv[1] for item in rows); print("MEMORY PASS", sys.argv[1])' "$memory_id" <<<"$memory_search"
order_preview="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST http://127.0.0.1:8765/api/orders/preview \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"600000.SH","side":"BUY","quantity":100,"limit_price":8}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["status"] == "PREVIEW"; assert d["live_submit_enabled"] is False; print("PAPER ORDER PREVIEW PASS")' <<<"$order_preview"
paper_order="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST http://127.0.0.1:8765/api/orders/paper \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"600000.SH","side":"BUY","quantity":100,"limit_price":8,"client_order_id":"e2e-paper-order"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["status"] == "PAPER_ACCEPTED"; assert d["order_id"] == "e2e-paper-order"; print("PAPER ORDER PASS", d["order_id"])' <<<"$paper_order"
rules_json="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS http://127.0.0.1:8765/api/rules)"
updated_rules="$(python3 -c 'import json,sys; payload=json.loads(sys.stdin.read()); rules=payload["rules"]; rules["version"]="v-e2e"; print(json.dumps({"rules":rules}))' <<<"$rules_json")"
updated_rules_response="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST http://127.0.0.1:8765/api/rules -H 'Content-Type: application/json' -d "$updated_rules")"
python3 -c 'import json,sys; payload=json.load(sys.stdin); assert payload["rules"]["version"] == "v-e2e"; print("RULESET VERSION PASS", payload["rule_snapshot_id"])' <<<"$updated_rules_response"
task_json="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST http://127.0.0.1:8765/api/tasks -H 'Content-Type: application/json' -d '{"trigger_type":"MarketClose","target":{"as_of":"2026-11-05"},"fixture":{"market":"close-2026-11-05.json","portfolio":"default.json"}}')"
task_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$task_json")"
for _ in $(seq 1 30); do
  detail="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS "http://127.0.0.1:8765/api/tasks/$task_id")"
  status="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])' <<<"$detail")"
  case "$status" in BLOCKED|NO_ACTION|WAITING_APPROVAL|FAILED|RETRYABLE) break;; esac
  sleep 0.2
done
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["task"]["status"] == "BLOCKED"; assert d["decision"]["status"] == "BLOCKED"; assert len(d["evidence"]) >= 3; print("E2E PASS", d["task"]["id"])' <<<"$detail"
context="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS "http://127.0.0.1:8765/api/tasks/$task_id/context")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["task_detail"]["task"]["id"] == sys.argv[1]; assert d["rule_snapshot_id"]; print("CONTEXT EXPORT PASS", sys.argv[1])' "$task_id" <<<"$context"
task_data="$(curl --noproxy '*' --connect-timeout 1 --max-time 5 -fsS "http://127.0.0.1:8765/api/tasks/$task_id/data")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["task_id"] == sys.argv[1]; assert d["bundles"]; assert any(bundle["raw_payloads"] for bundle in d["bundles"]); print("TASK DATA PASS", sys.argv[1])' "$task_id" <<<"$task_data"
replay_task="$(curl --noproxy '*' --connect-timeout 1 --max-time 5 -fsS -X POST "http://127.0.0.1:8765/api/tasks/$task_id/replay")"
replay_task_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["task"]["parent_task_id"] == sys.argv[1]; assert d["task"]["target"]["_replay_of"] == sys.argv[1]; print(d["task"]["id"])' "$task_id" <<<"$replay_task")"
echo "REPLAY PASS $replay_task_id"
retrospective="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST "http://127.0.0.1:8765/api/tasks/$task_id/retrospectives" \
  -H 'Content-Type: application/json' \
  -d '{"action_taken":"NOT_TAKEN","outcome":{"status":"observed","return_pct":0.0},"notes":"local e2e retrospective"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["task_id"] == sys.argv[1]; assert d["outcome"]["status"] == "observed"; print("RETROSPECTIVE WRITE PASS", d["id"])' "$task_id" <<<"$retrospective"
retrospectives="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS "http://127.0.0.1:8765/api/tasks/$task_id/retrospectives")"
python3 -c 'import json,sys; rows=json.load(sys.stdin)["retrospectives"]; assert rows and rows[0]["task_id"] == sys.argv[1]; print("RETROSPECTIVE READ PASS", sys.argv[1])' "$task_id" <<<"$retrospectives"

approval_task_json="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST http://127.0.0.1:8765/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"trigger_type":"MarketClose","target":{"as_of":"2026-11-05","suggested_action":"BUY_CANDIDATE"},"fixture":{"market":"close-2026-11-05.json","portfolio":"empty.json"}}')"
approval_task_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$approval_task_json")"
for _ in $(seq 1 30); do
  approval_detail="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS "http://127.0.0.1:8765/api/tasks/$approval_task_id")"
  approval_status="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])' <<<"$approval_detail")"
  [ "$approval_status" = "WAITING_APPROVAL" ] && break
  sleep 0.2
done
test "$approval_status" = "WAITING_APPROVAL"
approved="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST "http://127.0.0.1:8765/api/tasks/$approval_task_id/approve" \
  -H 'Content-Type: application/json' \
  -d '{"action":"NO_ACTION","notes":"local e2e research review"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["task"]["status"] == "NO_ACTION"; assert d["approval_id"]; print("RESEARCH REVIEW E2E PASS", d["task"]["id"])' <<<"$approved"

watch_task_json="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST http://127.0.0.1:8765/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"trigger_type":"StockResearch","target":{"as_of":"2026-11-05","symbol":"600000.SH","suggested_action":"BUY_CANDIDATE"},"fixture":{"market":"close-2026-11-05.json","portfolio":"empty.json"}}')"
watch_task_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$watch_task_json")"
for _ in $(seq 1 30); do
  watch_status="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS "http://127.0.0.1:8765/api/tasks/$watch_task_id" | python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')"
  [ "$watch_status" = "WAITING_APPROVAL" ] && break
  sleep 0.2
done
test "$watch_status" = "WAITING_APPROVAL"
watch_result="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST "http://127.0.0.1:8765/api/tasks/$watch_task_id/approve" \
  -H 'Content-Type: application/json' \
  -d '{"action":"MARK_AS_WATCH","notes":"local e2e watch"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["task"]["status"] == "NO_ACTION"; assert "600000.SH" in d["watchlist"]["symbols"]; print("MARK AS WATCH PASS", d["task"]["id"])' <<<"$watch_result"

curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST http://127.0.0.1:8765/api/events \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"DataQualityDegraded","payload":{"as_of":"2026-11-05","expires_at":"2020-01-01T00:00:00+00:00"}}' >/dev/null
notifications="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS http://127.0.0.1:8765/api/notifications)"
notification_id="$(python3 -c 'import json,sys; items=json.load(sys.stdin)["notifications"]; assert items; print(items[0]["id"])' <<<"$notifications")"
deliveries="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS "http://127.0.0.1:8765/api/notifications/$notification_id/deliveries")"
python3 -c 'import json,sys; rows=json.load(sys.stdin)["deliveries"]; assert rows and rows[0]["notification_id"] == sys.argv[1]; print("NOTIFICATION DELIVERY PASS", sys.argv[1])' "$notification_id" <<<"$deliveries"
curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST "http://127.0.0.1:8765/api/notifications/$notification_id/read" >/dev/null
unread="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS 'http://127.0.0.1:8765/api/notifications?unread=1')"
python3 -c 'import json,sys; ids={item["id"] for item in json.load(sys.stdin)["notifications"]}; assert sys.argv[1] not in ids; print("NOTIFICATION PASS", sys.argv[1])' "$notification_id" <<<"$unread"
device_id="e2e-device"
curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X POST http://127.0.0.1:8765/api/devices \
  -H 'Content-Type: application/json' \
  -d "{\"device_id\":\"$device_id\",\"platform\":\"web\",\"device_name\":\"E2E\",\"push_token\":\"push-token\"}" >/dev/null
curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS -X DELETE "http://127.0.0.1:8765/api/devices/$device_id" >/dev/null
devices="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS http://127.0.0.1:8765/api/devices)"
python3 -c 'import json,sys; assert all(item["device_id"] != sys.argv[1] for item in json.load(sys.stdin)["devices"]); print("DEVICE LIFECYCLE PASS", sys.argv[1])' "$device_id" <<<"$devices"
events="$(curl --noproxy '*' --connect-timeout 1 --max-time 5 -fsS "http://127.0.0.1:8765/api/tasks/$task_id/events")"
grep -q '^event: TASK_STATUS$' <<<"$events"
grep -q '^data: ' <<<"$events"
echo "SSE PASS $task_id"
metrics="$(curl --noproxy '*' --connect-timeout 1 --max-time 3 -fsS http://127.0.0.1:8765/api/metrics)"
python3 -c 'import json,sys; d=json.load(sys.stdin); system=d["system"]; assert d["task_total"] >= 1; assert d["terminal_success_rate"] == 1.0; assert d["p95_within_timeout"] is True; assert isinstance(system["queue_depth"], int); assert isinstance(system["active_task_count"], int); assert "oldest_active_task_age_seconds" in system; assert set(system["storage_bytes"]) >= {"database", "analytics_database"}; assert system["database_backend"] == "sqlite"; print("METRICS PASS", d["task_duration_p95_seconds"])' <<<"$metrics"
