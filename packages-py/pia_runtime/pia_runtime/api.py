from __future__ import annotations

import json
import hashlib
import ipaddress
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .runtime import PiaRuntime
from .schema import SchemaValidationError, validate_named, validate_schema
from .security import redact_secrets


SSE_TERMINAL_TASK_STATUSES = frozenset({
    "APPROVED",
    "REJECTED",
    "BLOCKED",
    "NO_ACTION",
    "FAILED",
    "RETRYABLE",
    "TIMEOUT",
    "CANCELLED",
    "DONE",
    "EXPIRED",
})

LOCAL_CREDENTIAL_ORIGINS = frozenset({
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
})
LOCAL_CREDENTIAL_PATHS = {"/api/settings/deepseek", "/api/settings/tushare"}


def serve(
    runtime: PiaRuntime, host: str, port: int, auth_token: str | None = None, *,
    desktop_identity: dict[str, str] | None = None,
) -> None:
    desktop_prefix = f"/{desktop_identity['instance_id']}" if desktop_identity else ""

    class Handler(BaseHTTPRequestHandler):
        server_version = "PiaLocalRuntime/0.1"
        _request_started_at: float | None = None

        def _route(self) -> str:
            path = urlparse(self.path).path
            if desktop_prefix and not path.startswith(f"{desktop_prefix}/"):
                return ""
            return path[len(desktop_prefix):]

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            started_at = self._request_started_at or time.perf_counter()
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            runtime.observability.record_request(
                self.command,
                self._route(),
                status,
                (time.perf_counter() - started_at) * 1000,
            )

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode() or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise SchemaValidationError("request body must be valid JSON") from error
            if not isinstance(payload, dict):
                raise SchemaValidationError("request body must be a JSON object")
            return payload

        def _authorized(self) -> bool:
            return self._user_id() is not None

        def _local_credentials_allowed(self) -> bool:
            # Restrict the host as well as the peer to prevent DNS rebinding.
            return (
                runtime.settings.mode == "local"
                and ipaddress.ip_address(self.client_address[0]).is_loopback
                and urlparse("//" + self.headers.get("Host", "")).hostname
                in {"localhost", "127.0.0.1", "::1"}
                and self.headers.get("Origin") in {None, *LOCAL_CREDENTIAL_ORIGINS}
            )

        def _local_credential_request(self, path: str) -> None:
            if not self._local_credentials_allowed():
                return self._send(403, {"error": "local_credentials_only"})
            tushare = path == "/api/settings/tushare"
            status = runtime.tushare_credential_status if tushare else runtime.deepseek_credential_status
            update = runtime.update_tushare_credential if tushare else runtime.update_deepseek_credential
            value = None
            if self.command == "POST":
                if (
                    self.headers.get_content_type() != "application/json"
                    or not 0 < int(self.headers.get("Content-Length", "0")) <= 4096
                ):
                    return self._send(400, {"error": "invalid_credential_request"})
                body = self._body()
                field = "token" if tushare else "api_key"
                value = body.get(field)
                if (
                    set(body) != {field}
                    or not isinstance(value, str)
                    or len(value) > 1024
                    or not value.strip()
                    or value.strip().startswith("__")
                    or any(character.isspace() for character in value.strip())
                ):
                    return self._send(400, {"error": "invalid_tushare_token" if tushare else "invalid_api_key"})
                value = value.strip()
            try:
                return self._send(200, status() if self.command == "GET" else update(value))
            except Exception:
                return self._send(500, {"error": "credential_store_unavailable"})

        def _user_id(self) -> str | None:
            if not auth_token:
                return "default"
            header = self.headers.get("Authorization", "")
            token = header.removeprefix("Bearer ").strip()
            return runtime.settings.cloud_users.get(token)

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, Authorization, Idempotency-Key, X-Worker-Id",
            )
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.end_headers()

        def do_GET(self) -> None:
            self._request_started_at = time.perf_counter()
            try:
                path = self._route()
                if path != "/api/health" and not self._authorized():
                    return self._send(401, {"error": "unauthorized"})
                if path == "/api/health":
                    health = runtime.health()
                    if desktop_identity is not None:
                        health["desktop_runtime"] = desktop_identity
                    return self._send(200, health)
                if path in LOCAL_CREDENTIAL_PATHS:
                    return self._local_credential_request(path)
                if path == "/api/tasks":
                    return self._send(200, {"tasks": runtime.list_tasks(self._user_id() or "default")})
                if path == "/api/rules":
                    return self._send(200, runtime.get_rules(self._user_id() or "default"))
                if path == "/api/profile":
                    return self._send(200, runtime.get_profile(self._user_id() or "default"))
                if path == "/api/watchlists":
                    return self._send(200, {
                        "watchlists": runtime.list_watchlists(self._user_id() or "default"),
                    })
                if path == "/api/journal":
                    query = parse_qs(urlparse(self.path).query)
                    filters = {
                        "user_id": self._user_id() or "default",
                        "symbol": query.get("symbol", [None])[0],
                        "intent": query.get("intent", [None])[0],
                        "outcome_status": query.get("outcome_status", [None])[0],
                        "rule_snapshot_id": query.get("rule_snapshot_id", [None])[0],
                        "from_date": query.get("from", [None])[0],
                        "to_date": query.get("to", [None])[0],
                    }
                    return self._send(200, runtime.list_journal(
                        **filters,
                        cursor=query.get("cursor", [None])[0],
                        limit=int(query.get("limit", ["50"])[0]),
                    ))
                if path in {"/api/journal/summary", "/api/journal/patterns"}:
                    query = parse_qs(urlparse(self.path).query)
                    filters = {
                        "user_id": self._user_id() or "default",
                        "symbol": query.get("symbol", [None])[0],
                        "intent": query.get("intent", [None])[0],
                        "outcome_status": query.get("outcome_status", [None])[0],
                        "rule_snapshot_id": query.get("rule_snapshot_id", [None])[0],
                        "from_date": query.get("from", [None])[0],
                        "to_date": query.get("to", [None])[0],
                    }
                    payload = (
                        runtime.journal_summary(**filters)
                        if path.endswith("/summary")
                        else runtime.journal_patterns(**filters)
                    )
                    return self._send(200, payload)
                if path.startswith("/api/journal/memory-candidates/") and path.endswith("/usage"):
                    candidate_id = path.split("/")[4]
                    return self._send(200, runtime.list_journal_memory_candidate_usages(
                        candidate_id,
                        user_id=self._user_id() or "default",
                    ))
                if path.startswith("/api/tasks/") and path.endswith("/lease"):
                    task_id = path.split("/")[3]
                    if not runtime.task_detail(task_id, self._user_id() or "default"):
                        return self._send(404, {"error": "task_not_found"})
                    worker_id = self.headers.get("X-Worker-Id", "cloud-worker")
                    return self._send(200, runtime.db.acquire_lease(task_id, worker_id))
                if path == "/api/providers":
                    return self._send(200, {
                        "providers": runtime.providers.health(),
                    })
                if path == "/api/scheduler":
                    return self._send(200, runtime.scheduler.health())
                if path == "/api/events":
                    user_id = self._user_id() or "default"
                    rows = runtime.db.fetchall(
                        "SELECT * FROM events WHERE user_id=? "
                        "ORDER BY occurred_at DESC LIMIT 100",
                        (user_id,),
                    )
                    return self._send(200, {"events": [dict(row) for row in rows]})
                if path == "/api/memory":
                    query = parse_qs(urlparse(self.path).query)
                    return self._send(200, {
                        "memories": runtime.search_memories(
                            query.get("q", [""])[0],
                            symbol=query.get("symbol", [None])[0],
                            limit=int(query.get("limit", ["50"])[0]),
                            user_id=self._user_id() or "default",
                        ),
                    })
                if path == "/api/portfolio":
                    user_id = self._user_id() or "default"
                    snapshot = runtime.db.get_latest_portfolio_snapshot(user_id, include_fixture=False)
                    if snapshot is None:
                        snapshot = runtime.db.get_latest_portfolio_snapshot(user_id)
                    return self._send(200, snapshot or {"status": "unavailable"})
                if path == "/api/market":
                    detail = runtime.db.fetchone(
                        "SELECT payload_json FROM market_snapshots ORDER BY as_of DESC LIMIT 1"
                    )
                    return self._send(200, json.loads(detail["payload_json"]) if detail else {"status": "unavailable"})
                if path == "/api/candidates":
                    query = parse_qs(urlparse(self.path).query)
                    return self._send(200, runtime.scan_candidates(
                        query.get("as_of", ["2026-11-05"])[0],
                        query.get("fixture", [None])[0],
                        self._user_id() or "default",
                    ))
                if path == "/api/screening-strategies":
                    return self._send(200, {"strategies": list(runtime.strategies.values())})
                if path.startswith("/api/candidate-scans/"):
                    return self._send(200, runtime.candidate_scan(path.split("/")[3], self._user_id() or "default"))
                if path == "/api/audit":
                    rows = runtime.db.fetchall(
                        "SELECT * FROM audit_log WHERE user_id=? "
                        "ORDER BY id DESC LIMIT 100",
                        (self._user_id() or "default",),
                    )
                    return self._send(200, {"audit": [dict(row) for row in rows]})
                if path == "/api/notifications":
                    query = parse_qs(urlparse(self.path).query)
                    unread_only = query.get("unread", ["0"])[0] == "1"
                    return self._send(200, {
                        "notifications": runtime.db.list_notifications(
                            unread_only,
                            self._user_id() or "default",
                        ),
                    })
                if path.startswith("/api/notifications/") and path.endswith("/deliveries"):
                    notification_id = path.split("/")[3]
                    user_id = self._user_id() or "default"
                    notification = runtime.db.fetchone(
                        "SELECT id FROM notifications WHERE id=? AND user_id=?",
                        (notification_id, user_id),
                    )
                    if not notification:
                        return self._send(404, {"error": "notification_not_found"})
                    return self._send(200, {
                        "deliveries": runtime.db.list_notification_deliveries(
                            notification_id,
                            user_id,
                        ),
                    })
                if path == "/api/devices":
                    return self._send(200, {
                        "devices": runtime.db.list_devices(self._user_id() or "default"),
                    })
                if path == "/api/sync":
                    query = parse_qs(urlparse(self.path).query)
                    return self._send(200, runtime.db.sync_changes(
                        int(query.get("cursor", ["0"])[0]),
                        int(query.get("limit", ["100"])[0]),
                        self._user_id() or "default",
                    ))
                if path == "/api/metrics":
                    return self._send(200, runtime.metrics(self._user_id() or "default"))
                if path.startswith("/api/tasks/") and path.endswith("/events"):
                    return self._stream_events(path.split("/")[3], self._user_id() or "default")
                if path.startswith("/api/tasks/") and path.endswith("/context"):
                    query = parse_qs(urlparse(self.path).query)
                    return self._send(200, runtime.task_context(
                        path.split("/")[3],
                        self._user_id() or "default",
                        view=query.get("view", ["overview"])[0],
                    ))
                if path.startswith("/api/tasks/") and path.endswith("/flow"):
                    query = parse_qs(urlparse(self.path).query)
                    return self._send(200, runtime.task_flow(
                        path.split("/")[3], self._user_id() or "default",
                        int(query.get("after_seq", ["0"])[0]), int(query.get("limit", ["100"])[0]),
                        int(query["snapshot_seq"][0]) if "snapshot_seq" in query else None,
                    ))
                if path.startswith("/api/tasks/") and path.endswith("/data"):
                    return self._send(200, runtime.task_data(
                        path.split("/")[3],
                        self._user_id() or "default",
                    ))
                if path.startswith("/api/tasks/") and path.endswith("/export"):
                    return self._send(200, runtime.export_task(path.split("/")[3], self._user_id() or "default"))
                if path.startswith("/api/tasks/") and path.endswith("/retrospectives"):
                    task_id = path.split("/")[3]
                    if not runtime.task_detail(task_id, self._user_id() or "default"):
                        return self._send(404, {"error": "task_not_found"})
                    return self._send(200, {
                        "retrospectives": runtime.db.list_retrospectives(
                            task_id,
                            self._user_id() or "default",
                        ),
                    })
                if path.startswith("/api/tasks/"):
                    task_id = path.split("/")[3]
                    detail = runtime.task_detail(task_id, self._user_id() or "default")
                    return self._send(200 if detail else 404, detail or {"error": "task_not_found"})
                return self._send(404, {"error": "not_found"})
            except KeyError as error:
                return self._send(404, {"error": "not_found", "detail": redact_secrets(str(error))})
            except ValueError as error:
                return self._send(409, {"error": "invalid_state", "detail": redact_secrets(str(error))})
            except Exception as error:
                return self._send(500, {
                    "error": type(error).__name__,
                    "detail": redact_secrets(str(error)),
                })

        def _stream_events(self, task_id: str, user_id: str) -> None:
            if not runtime.task_detail(task_id, user_id):
                return self._send(404, {"error": "task_not_found"})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            runtime.observability.record_request(
                self.command,
                self._route(),
                200,
                (time.perf_counter() - (self._request_started_at or time.perf_counter())) * 1000,
            )
            self.close_connection = True
            sent = 0
            idle_ticks = 0
            while idle_ticks < 80:
                events = runtime.db.task_events(task_id)
                for event in events[sent:]:
                    chunk = f"event: {event['event_type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    sent += 1
                detail = runtime.task_detail(task_id, user_id)
                status = detail["task"]["status"] if detail else "FAILED"
                if status in SSE_TERMINAL_TASK_STATUSES:
                    break
                idle_ticks += 1
                time.sleep(0.25)

        def do_POST(self) -> None:
            self._request_started_at = time.perf_counter()
            path = self._route()
            try:
                if not path:
                    return self._send(404, {"error": "not_found"})
                if not self._authorized():
                    return self._send(401, {"error": "unauthorized"})
                if path in LOCAL_CREDENTIAL_PATHS:
                    return self._local_credential_request(path)
                body = self._body()
                if path == "/api/candidate-scans":
                    allowed = {"as_of", "strategy_id", "strategy_version", "fixture"}
                    if set(body) - allowed or not isinstance(body.get("as_of"), str):
                        return self._send(400, {"error": "INVALID_SCAN_PARAMETERS"})
                    try:
                        result = runtime.scan_candidates(
                            body["as_of"], body.get("fixture"), self._user_id() or "default",
                            body.get("strategy_id", "legacy_momentum_v1"), body.get("strategy_version", "1.0.0"),
                            persist=True,
                        )
                    except ValueError:
                        return self._send(400, {"error": "INVALID_SCAN_PARAMETERS"})
                    return self._send(201, result)
                if path.startswith("/api/candidate-scans/") and path.endswith("/replay"):
                    return self._send(200, runtime.candidate_scan(path.split("/")[3], self._user_id() or "default", replay=True))
                if path == "/api/tasks":
                    validate_schema(body, {
                        "type": "object",
                        "properties": {
                            "trigger_type": {"type": "string"},
                            "target": {"type": "object"},
                            "fixture": {"type": ["object", "null"]},
                        },
                    })
                    user_id = self._user_id() or "default"
                    idempotency_key = self.headers.get("Idempotency-Key", "").strip()
                    request_hash = hashlib.sha256(
                        json.dumps(body, ensure_ascii=False, sort_keys=True).encode()
                    ).hexdigest()
                    if idempotency_key:
                        existing = runtime.db.get_idempotent_response(
                            user_id,
                            "create_task",
                            idempotency_key,
                            request_hash,
                        )
                        if existing:
                            return self._send(200, existing)
                    task = runtime.create_task(
                        body.get("trigger_type", "MarketClose"),
                        body.get("target", {}),
                        body.get("fixture"),
                        user_id=user_id,
                    )
                    response = {"task": task.to_dict()}
                    if idempotency_key:
                        response = runtime.db.save_idempotent_response(
                            user_id,
                            "create_task",
                            idempotency_key,
                            response,
                            request_hash,
                        )
                    return self._send(201, response)
                if path == "/api/events":
                    validate_named(body, "event")
                    return self._send(202, runtime.ingest_event(
                        body["event_type"],
                        body.get("payload", {}),
                        body.get("dedupe_key"),
                        user_id=self._user_id() or "default",
                    ))
                if path == "/api/data/sync":
                    validate_schema(body, {
                        "type": "object",
                        "required": ["as_of"],
                        "properties": {
                            "as_of": {"type": "string"},
                            "symbols": {"type": "array", "items": {"type": "string"}},
                        },
                    })
                    return self._send(202, runtime.sync_market_data(
                        body["as_of"],
                        body.get("symbols", []),
                        user_id=self._user_id() or "default",
                    ))
                if path == "/api/orders/preview":
                    validate_schema(body, {
                        "type": "object",
                        "required": ["symbol", "side", "quantity"],
                        "properties": {
                            "symbol": {"type": "string"},
                            "side": {"type": "string", "enum": ["BUY", "SELL"]},
                            "quantity": {"type": "number", "exclusiveMinimum": 0},
                            "limit_price": {"type": ["number", "null"], "exclusiveMinimum": 0},
                            "client_order_id": {"type": ["string", "null"]},
                        },
                    })
                    return self._send(200, runtime.preview_order(
                        body,
                        user_id=self._user_id() or "default",
                    ))
                if path == "/api/orders/paper":
                    validate_schema(body, {
                        "type": "object",
                        "required": ["symbol", "side", "quantity"],
                        "properties": {
                            "symbol": {"type": "string"},
                            "side": {"type": "string", "enum": ["BUY", "SELL"]},
                            "quantity": {"type": "number", "exclusiveMinimum": 0},
                            "limit_price": {"type": ["number", "null"], "exclusiveMinimum": 0},
                            "client_order_id": {"type": ["string", "null"]},
                        },
                    })
                    return self._send(201, runtime.paper_submit_order(
                        body,
                        user_id=self._user_id() or "default",
                    ))
                if path == "/api/scheduler/start":
                    runtime.scheduler.start()
                    return self._send(200, runtime.scheduler.health())
                if path == "/api/scheduler/stop":
                    runtime.scheduler.stop()
                    return self._send(200, runtime.scheduler.health())
                if path == "/api/portfolio/import":
                    validate_schema(body, {
                        "type": "object",
                        "required": ["format", "content"],
                        "properties": {
                            "format": {"type": "string", "enum": ["csv", "xlsx", "excel", "manual"]},
                            "content": {},
                            "as_of": {"type": "string", "format": "date"},
                        },
                    })
                    return self._send(201, {"portfolio": runtime.import_portfolio(
                        body.get("format", "manual"),
                        body.get("content", []),
                        user_id=self._user_id() or "default",
                        as_of=body.get("as_of"),
                    )})
                if path == "/api/portfolio/positions":
                    required = ["snapshot_id", "as_of", "mode", "symbol"]
                    if body.get("mode") != "delete":
                        required.extend(("quantity", "avg_cost", "market_value"))
                    validate_schema(body, {
                        "type": "object",
                        "required": required,
                        "properties": {
                            "snapshot_id": {"type": ["string", "null"]},
                            "as_of": {"type": "string", "format": "date"},
                            "mode": {"type": "string", "enum": ["add", "edit", "delete"]},
                            "symbol": {"type": "string", "minLength": 1},
                            "position_index": {"type": "integer", "minimum": 0},
                            "quantity": {"type": "number", "minimum": 0},
                            "avg_cost": {"type": "number", "minimum": 0},
                            "market_value": {"type": "number", "minimum": 0},
                        },
                    })
                    return self._send(201, {"portfolio": runtime.save_portfolio_position(
                        body, user_id=self._user_id() or "default",
                    )})
                if path == "/api/profile":
                    payload = body.get("payload", body)
                    validate_schema(payload, {
                        "type": "object",
                        "required": ["risk_tolerance", "investment_objective", "allowed_asset_types", "universe"],
                        "properties": {
                            "risk_tolerance": {"type": "string"},
                            "investment_objective": {"type": "string"},
                            "allowed_asset_types": {"type": "array", "items": {"type": "string"}},
                            "universe": {"type": "array", "items": {"type": "string"}},
                        },
                    })
                    return self._send(201, runtime.update_profile(payload, self._user_id() or "default"))
                if path in {"/api/watchlists", "/api/watchlists/append"}:
                    validate_schema(body, {
                        "type": "object",
                        "required": ["name", "symbols"],
                        "properties": {
                            "name": {"type": "string"},
                            "symbols": {"type": "array", "items": {"type": "string"}},
                        },
                    })
                    return self._send(201, runtime.save_watchlist(
                        body["name"],
                        body["symbols"],
                        self._user_id() or "default",
                        append=path == "/api/watchlists/append",
                    ))
                if path == "/api/journal/memory-candidates":
                    validate_schema(body, {
                        "type": "object",
                        "required": ["candidate_key"],
                        "properties": {
                            "candidate_key": {"type": "string", "minLength": 1},
                        },
                        "additionalProperties": False,
                    })
                    return self._send(201, runtime.materialize_journal_memory_candidate(
                        body["candidate_key"],
                        user_id=self._user_id() or "default",
                    ))
                if path.startswith("/api/journal/memory-candidates/") and path.endswith("/review"):
                    candidate_id = path.split("/")[4]
                    validate_schema(body, {
                        "type": "object",
                        "required": ["action"],
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["CONFIRM", "EDIT_AND_CONFIRM", "REJECT", "ARCHIVE"],
                            },
                            "title": {"type": ["string", "null"]},
                            "content": {"type": ["string", "null"]},
                            "notes": {"type": "string"},
                        },
                        "additionalProperties": False,
                    })
                    return self._send(200, runtime.review_journal_memory_candidate(
                        candidate_id,
                        action=body["action"],
                        title=body.get("title"),
                        content=body.get("content"),
                        notes=body.get("notes", ""),
                        user_id=self._user_id() or "default",
                    ))
                if path.startswith("/api/journal/memory-candidates/") and path.endswith("/feedback"):
                    candidate_id = path.split("/")[4]
                    validate_schema(body, {
                        "type": "object",
                        "required": ["rating"],
                        "properties": {
                            "rating": {
                                "type": "string",
                                "enum": ["HELPFUL", "NOT_HELPFUL", "UNCERTAIN"],
                            },
                            "usage_id": {"type": ["string", "null"]},
                            "notes": {"type": "string"},
                        },
                        "additionalProperties": False,
                    })
                    return self._send(200, runtime.record_journal_memory_candidate_feedback(
                        candidate_id,
                        rating=body["rating"],
                        usage_id=body.get("usage_id"),
                        notes=body.get("notes", ""),
                        user_id=self._user_id() or "default",
                    ))
                if path == "/api/memory":
                    validate_schema(body, {
                        "type": "object",
                        "required": ["title", "content"],
                        "properties": {
                            "kind": {"type": "string"},
                            "symbol": {"type": ["string", "null"]},
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "source": {"type": "string"},
                            "as_of": {"type": ["string", "null"]},
                            "observed_at": {"type": ["string", "null"]},
                            "quality": {"type": "string"},
                        },
                    })
                    return self._send(201, runtime.save_memory(
                        body,
                        user_id=self._user_id() or "default",
                    ))
                if path == "/api/rules":
                    validate_schema(body, {
                        "type": "object",
                        "required": ["rules"],
                        "properties": {"rules": {"type": "object"}},
                    })
                    return self._send(201, runtime.update_rules(
                        body["rules"],
                        self._user_id() or "default",
                    ))
                if path == "/api/devices":
                    validate_named(body, "device")
                    return self._send(201, runtime.db.register_device(
                        body["device_id"],
                        body["platform"],
                        body.get("device_name"),
                        body.get("push_token"),
                        self._user_id() or "default",
                    ))
                if path.startswith("/api/leases/") and path.endswith("/heartbeat"):
                    lease_id = path.split("/")[3]
                    return self._send(200, runtime.db.heartbeat_lease(
                        lease_id,
                        body.get("worker_id", self.headers.get("X-Worker-Id", "cloud-worker")),
                        int(body.get("ttl_seconds", 60)),
                        self._user_id() or "default",
                    ))
                if path.startswith("/api/leases/") and path.endswith("/release"):
                    lease_id = path.split("/")[3]
                    worker_id = body.get("worker_id", self.headers.get("X-Worker-Id", "cloud-worker"))
                    runtime.db.release_lease(
                        lease_id,
                        worker_id,
                        self._user_id() or "default",
                    )
                    return self._send(200, {"status": "released", "lease_id": lease_id})
                if path.startswith("/api/notifications/") and path.endswith("/read"):
                    notification_id = path.split("/")[3]
                    runtime.db.mark_notification_read(notification_id, self._user_id() or "default")
                    return self._send(200, {"status": "read", "notification_id": notification_id})
                if path.startswith("/api/tasks/") and path.endswith("/approve"):
                    task_id = path.split("/")[3]
                    validate_schema(body, {
                        "type": "object",
                        "required": ["action"],
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "APPROVE",
                                    "REJECT",
                                    "NO_ACTION",
                                    "REQUEST_MORE_RESEARCH",
                                    "MARK_AS_WATCH",
                                ],
                            },
                            "notes": {"type": "string"},
                        },
                    })
                    result = runtime.approve_task(
                        task_id,
                        body.get("action", "REJECT"),
                        body.get("notes", ""),
                        self._user_id() or "default",
                    )
                    return self._send(200, result)
                if path.startswith("/api/tasks/") and path.endswith("/pause"):
                    task = runtime.pause_task(path.split("/")[3], self._user_id() or "default")
                    return self._send(200, {"task": task.to_dict()})
                if path.startswith("/api/tasks/") and path.endswith("/resume"):
                    task = runtime.resume_task(path.split("/")[3], self._user_id() or "default")
                    return self._send(200, {"task": task.to_dict()})
                if path.startswith("/api/tasks/") and path.endswith("/retry"):
                    task_id = path.split("/")[3]
                    task = runtime.retry_task(task_id, self._user_id() or "default")
                    return self._send(202, {"task": task.to_dict()})
                if path.startswith("/api/tasks/") and path.endswith("/replay"):
                    task_id = path.split("/")[3]
                    task = runtime.replay_task(task_id, self._user_id() or "default")
                    return self._send(202, {"task": task.to_dict()})
                if path.startswith("/api/tasks/") and path.endswith("/cancel"):
                    task = runtime.cancel_task(
                        path.split("/")[3],
                        self._user_id() or "default",
                        body.get("reason", ""),
                    )
                    return self._send(200, {"task": task.to_dict()})
                if path.startswith("/api/tasks/") and path.endswith("/takeover"):
                    return self._send(200, runtime.takeover_task(
                        path.split("/")[3],
                        self._user_id() or "default",
                        body.get("notes", ""),
                    ))
                if path.startswith("/api/tasks/") and path.endswith("/retrospectives"):
                    validate_schema(body, {
                        "type": "object",
                        "required": ["action_taken", "outcome"],
                        "properties": {
                            "action_taken": {
                                "type": "string",
                                "minLength": 1,
                            },
                            "outcome": {
                                "type": "object",
                                "additionalProperties": True,
                            },
                            "notes": {"type": "string"},
                            "observed_at": {"type": ["string", "null"]},
                        },
                    })
                    return self._send(201, runtime.record_retrospective(
                        path.split("/")[3],
                        action_taken=body["action_taken"],
                        outcome=body["outcome"],
                        notes=body.get("notes", ""),
                        observed_at=body.get("observed_at"),
                        user_id=self._user_id() or "default",
                    ))
                return self._send(404, {"error": "not_found"})
            except KeyError as error:
                return self._send(404, {"error": "not_found", "detail": redact_secrets(str(error))})
            except SchemaValidationError as error:
                return self._send(400, {"error": "invalid_request", "detail": redact_secrets(str(error))})
            except ValueError as error:
                return self._send(409, {"error": "conflict", "detail": redact_secrets(str(error))})
            except Exception as error:
                return self._send(500, {
                    "error": type(error).__name__,
                    "detail": redact_secrets(str(error)),
                })

        def do_DELETE(self) -> None:
            self._request_started_at = time.perf_counter()
            path = self._route()
            try:
                if not self._authorized():
                    return self._send(401, {"error": "unauthorized"})
                if path in LOCAL_CREDENTIAL_PATHS:
                    return self._local_credential_request(path)
                if path.startswith("/api/devices/"):
                    device_id = path.split("/")[3]
                    runtime.db.unregister_device(
                        device_id,
                        self._user_id() or "default",
                    )
                    return self._send(200, {
                        "status": "unregistered",
                        "device_id": device_id,
                    })
                return self._send(404, {"error": "not_found"})
            except KeyError as error:
                return self._send(404, {"error": "not_found", "detail": redact_secrets(str(error))})
            except Exception as error:
                return self._send(500, {
                    "error": type(error).__name__,
                    "detail": redact_secrets(str(error)),
                })

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    address = f"http://{host}:{server.server_port}"
    try:
        if desktop_identity is None:
            print(f"Pia {runtime.settings.mode} runtime listening on {address}", flush=True)
        else:
            print("PIA_DESKTOP_READY " + json.dumps({**desktop_identity, "base_url": f"{address}{desktop_prefix}/api"}), flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
