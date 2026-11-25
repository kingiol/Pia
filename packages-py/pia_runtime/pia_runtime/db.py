from __future__ import annotations

import json
import hashlib
import math
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import Decision, Evidence, Task, TaskStatus, new_id, now_iso


class Database:
    RETROSPECTIVE_HORIZONS = {"T+5", "T+20", "USER_RECORDED"}
    LEGACY_ANOMALY_PREFIX = "price-volume-history-"
    APPROVAL_NOTIFICATION_PREFIX = "task-approval-"

    def __init__(self, path: Path, migrations_dir: Path) -> None:
        self.path = path
        self.migrations_dir = migrations_dir
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.RLock()
        self._transaction_depth = 0
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        for attempt in range(20):
            try:
                self.connection.execute("PRAGMA journal_mode = WAL")
                break
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower() or attempt == 19:
                    raise
                time.sleep(0.1)
        self.apply_migrations()

    def apply_migrations(self) -> None:
        with self.lock:
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version TEXT PRIMARY KEY,
                   applied_at TEXT NOT NULL
                )"""
            )
            for migration in sorted(self.migrations_dir.glob("*.sql")):
                applied = self.connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=?",
                    (migration.name,),
                ).fetchone()
                if applied:
                    continue
                try:
                    self.connection.executescript(migration.read_text())
                except sqlite3.OperationalError as error:
                    # Migration 006 was introduced after some local databases
                    # had already applied the ALTER TABLE manually.
                    if migration.name != "006_task_control.sql" or "duplicate column name" not in str(error):
                        raise
                self.connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (migration.name, now_iso()),
                )
            self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self.lock:
            cursor = self.connection.execute(query, params)
            if not self._transaction_depth:
                self.connection.commit()
            return cursor

    @contextmanager
    def transaction(self):
        with self.lock:
            outermost = self._transaction_depth == 0
            if outermost:
                self.connection.execute("BEGIN IMMEDIATE")
            self._transaction_depth += 1
            try:
                yield
                if outermost:
                    self.connection.commit()
            except BaseException:
                if outermost:
                    self.connection.rollback()
                raise
            finally:
                self._transaction_depth -= 1

    def save_task_binding(self, task: Task, payload: dict[str, Any]) -> dict[str, Any]:
        from .decision_context import canonical_json, content_hash, sanitize_context

        payload = sanitize_context(payload)
        binding = {
            "id": new_id("binding"), "payload": payload,
            "content_hash": content_hash(payload),
        }
        self.execute(
            """INSERT INTO task_input_bindings
               (id, user_id, task_id, schema_version, payload_json, content_hash, created_at)
               VALUES (?, ?, ?, '1', ?, ?, ?)""",
            (binding["id"], task.user_id, task.id, canonical_json(payload),
             binding["content_hash"], now_iso()),
        )
        return binding

    def get_task_binding(self, task_id: str, user_id: str) -> dict[str, Any] | None:
        from .decision_context import content_hash

        row = self.fetchone(
            "SELECT * FROM task_input_bindings WHERE task_id=? AND user_id=?",
            (task_id, user_id),
        )
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        if row["schema_version"] != "1" or content_hash(payload) != row["content_hash"]:
            raise ValueError("INPUT_BINDING_HASH_MISMATCH")
        return {"id": row["id"], "payload": payload, "content_hash": row["content_hash"]}

    def save_context_pack(self, task: Task, pack: dict[str, Any]) -> None:
        from .decision_context import canonical_json, validate_pack

        pack = validate_pack(pack)
        if pack["task_id"] != task.id:
            raise ValueError("CONTEXT_TASK_MISMATCH")
        self.execute(
            """INSERT INTO decision_context_packs
               (id, user_id, task_id, schema_version, payload_json, content_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pack["pack_id"], task.user_id, task.id, pack["schema_version"],
             canonical_json(pack), pack["content_hash"], pack["created_at"]),
        )

    def get_context_pack(self, task_id: str, user_id: str) -> dict[str, Any] | None:
        from .decision_context import validate_pack

        row = self.fetchone(
            "SELECT * FROM decision_context_packs WHERE task_id=? AND user_id=?",
            (task_id, user_id),
        )
        if not row:
            return None
        pack = validate_pack(json.loads(row["payload_json"]))
        if pack["task_id"] != task_id or pack["content_hash"] != row["content_hash"]:
            raise ValueError("CONTEXT_TASK_MISMATCH")
        return pack

    def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.lock:
            return self.connection.execute(query, params).fetchone()

    def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.connection.execute(query, params).fetchall()

    def user_seed(self, user_id: str = "default") -> None:
        self.execute(
            "INSERT OR IGNORE INTO users(id, created_at) VALUES (?, ?)",
            (user_id, now_iso()),
        )

    def list_user_ids(self) -> list[str]:
        rows = self.fetchall("SELECT id FROM users ORDER BY id")
        return [str(row["id"]) for row in rows] or ["default"]

    def save_profile(self, payload: dict[str, Any], user_id: str = "default") -> dict[str, Any]:
        row = self.fetchone(
            "SELECT COALESCE(MAX(version), 0) AS version FROM investor_profiles WHERE user_id=?",
            (user_id,),
        )
        version = int(row["version"]) + 1
        profile = {
            "id": f"profile_{user_id}_v{version}",
            "user_id": user_id,
            "version": version,
            "payload": payload,
            "created_at": now_iso(),
        }
        self.execute(
            """INSERT INTO investor_profiles
               (id, user_id, version, payload_json, created_at, active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (
                profile["id"],
                user_id,
                version,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                profile["created_at"],
            ),
        )
        self.audit(None, "PROFILE_VERSION_CREATED", profile)
        return profile

    def get_profile(self, user_id: str = "default") -> dict[str, Any] | None:
        row = self.fetchone(
            """SELECT id, user_id, version, payload_json, created_at
               FROM investor_profiles
               WHERE user_id=? AND active=1
               ORDER BY version DESC LIMIT 1""",
            (user_id,),
        )
        if not row:
            return None
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "version": row["version"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }

    def save_watchlist(
        self,
        name: str,
        symbols: list[str],
        user_id: str = "default",
    ) -> dict[str, Any]:
        normalized = sorted({
            str(symbol).strip().upper()
            for symbol in symbols
            if str(symbol).strip()
        })
        if not name.strip():
            raise ValueError("watchlist name is required")
        now = now_iso()
        watchlist = {
            "id": new_id("watchlist"),
            "user_id": user_id,
            "name": name.strip(),
            "symbols": normalized,
            "created_at": now,
            "updated_at": now,
        }
        self.execute(
            """INSERT INTO watchlists
               (id, user_id, name, symbols_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, name) DO UPDATE SET
                 symbols_json=excluded.symbols_json,
                 updated_at=excluded.updated_at""",
            (
                watchlist["id"],
                user_id,
                watchlist["name"],
                json.dumps(normalized, ensure_ascii=False),
                now,
                now,
            ),
        )
        row = self.fetchone(
            "SELECT * FROM watchlists WHERE user_id=? AND name=?",
            (user_id, watchlist["name"]),
        )
        result = _watchlist_row(row) if row else watchlist
        self.audit(None, "WATCHLIST_SAVED", result, user_id=user_id)
        return result

    def list_watchlists(self, user_id: str = "default") -> list[dict[str, Any]]:
        rows = self.fetchall(
            "SELECT * FROM watchlists WHERE user_id=? ORDER BY updated_at DESC",
            (user_id,),
        )
        return [_watchlist_row(row) for row in rows]

    def save_memory(
        self,
        *,
        kind: str,
        title: str,
        content: str,
        source: str,
        user_id: str = "default",
        symbol: str | None = None,
        as_of: str | None = None,
        observed_at: str | None = None,
        quality: str = "partial",
        task_id: str | None = None,
    ) -> dict[str, Any]:
        if not title.strip() or not content.strip():
            raise ValueError("memory title and content are required")
        memory = {
            "id": new_id("memory"),
            "user_id": user_id,
            "kind": kind.strip() or "semantic",
            "symbol": symbol.strip().upper() if symbol else None,
            "title": title.strip(),
            "content": content.strip(),
            "source": source.strip() or "unknown",
            "as_of": as_of,
            "observed_at": observed_at,
            "quality": quality if quality in {"verified", "partial", "stale", "unavailable"} else "partial",
            "task_id": task_id,
            "created_at": now_iso(),
        }
        self.execute(
            """INSERT INTO semantic_memories
               (id, user_id, kind, symbol, title, content, source, as_of,
                observed_at, quality, task_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                memory["id"],
                memory["user_id"],
                memory["kind"],
                memory["symbol"],
                memory["title"],
                memory["content"],
                memory["source"],
                memory["as_of"],
                memory["observed_at"],
                memory["quality"],
                memory["task_id"],
                memory["created_at"],
            ),
        )
        self.audit(None, "SEMANTIC_MEMORY_SAVED", memory, user_id=user_id)
        return memory

    def search_memories(
        self,
        query: str = "",
        *,
        user_id: str = "default",
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses = ["user_id=?"]
        params: list[Any] = [user_id]
        text = query.strip()
        if text:
            clauses.append("(title LIKE ? OR content LIKE ? OR source LIKE ?)")
            needle = f"%{text}%"
            params.extend([needle, needle, needle])
        if symbol:
            clauses.append("symbol=?")
            params.append(symbol.strip().upper())
        params.append(max(1, min(int(limit), 200)))
        rows = self.fetchall(
            "SELECT * FROM semantic_memories WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC LIMIT ?",
            tuple(params),
        )
        return [dict(row) for row in rows]

    def save_memory_candidate(
        self,
        candidate: dict[str, Any],
        *,
        user_id: str = "default",
    ) -> dict[str, Any]:
        candidate_key = str(candidate.get("candidate_key") or "").strip()
        title = str(candidate.get("title") or "").strip()
        content = str(candidate.get("content") or "").strip()
        if not candidate_key or not title or not content:
            raise ValueError("memory candidate key, title and content are required")
        source_task_ids = [
            str(value)
            for value in (candidate.get("source_task_ids") or [])
            if str(value).strip()
        ]
        source_rule_snapshot_ids = [
            str(value)
            for value in (candidate.get("source_rule_snapshot_ids") or [])
            if str(value).strip()
        ]
        existing = self.fetchone(
            "SELECT * FROM memory_candidates WHERE user_id=? AND candidate_key=?",
            (user_id, candidate_key),
        )
        now = now_iso()
        if existing and str(existing["status"]) != "CANDIDATE":
            raise ValueError("memory candidate is not mutable")
        memory = {
            "id": str(existing["id"]) if existing else new_id("memory_candidate"),
            "user_id": user_id,
            "candidate_key": candidate_key,
            "source_type": "SYSTEM_DERIVED",
            "status": "CANDIDATE",
            "kind": str(candidate.get("kind") or "RETROSPECTIVE_PATTERN"),
            "title": title,
            "content": content,
            "sample_size": int(candidate.get("sample_size") or 0),
            "comparable_outcome_count": int(candidate.get("comparable_outcome_count") or 0),
            "average_return_pct": candidate.get("average_return_pct"),
            "source_task_ids_json": json.dumps(source_task_ids, ensure_ascii=False),
            "source_rule_snapshot_ids_json": json.dumps(
                source_rule_snapshot_ids,
                ensure_ascii=False,
            ),
            "as_of": candidate.get("as_of"),
            "observed_at": candidate.get("observed_at"),
            "created_at": str(existing["created_at"]) if existing else now,
            "updated_at": now,
        }
        if existing:
            self.execute(
                """UPDATE memory_candidates
                   SET source_type=?, status=?, kind=?, title=?, content=?,
                       sample_size=?, comparable_outcome_count=?,
                       average_return_pct=?, source_task_ids_json=?,
                       source_rule_snapshot_ids_json=?, as_of=?, observed_at=?,
                       updated_at=?
                   WHERE id=? AND user_id=?""",
                (
                    memory["source_type"],
                    memory["status"],
                    memory["kind"],
                    memory["title"],
                    memory["content"],
                    memory["sample_size"],
                    memory["comparable_outcome_count"],
                    memory["average_return_pct"],
                    memory["source_task_ids_json"],
                    memory["source_rule_snapshot_ids_json"],
                    memory["as_of"],
                    memory["observed_at"],
                    memory["updated_at"],
                    memory["id"],
                    user_id,
                ),
            )
            event_type = "MEMORY_CANDIDATE_REFRESHED"
        else:
            self.execute(
                """INSERT INTO memory_candidates
                   (id, user_id, candidate_key, source_type, status, kind,
                    title, content, sample_size, comparable_outcome_count,
                    average_return_pct, source_task_ids_json,
                    source_rule_snapshot_ids_json, as_of, observed_at,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    memory["id"],
                    memory["user_id"],
                    memory["candidate_key"],
                    memory["source_type"],
                    memory["status"],
                    memory["kind"],
                    memory["title"],
                    memory["content"],
                    memory["sample_size"],
                    memory["comparable_outcome_count"],
                    memory["average_return_pct"],
                    memory["source_task_ids_json"],
                    memory["source_rule_snapshot_ids_json"],
                    memory["as_of"],
                    memory["observed_at"],
                    memory["created_at"],
                    memory["updated_at"],
                ),
            )
            event_type = "MEMORY_CANDIDATE_CREATED"
        result = self.fetchone(
            "SELECT * FROM memory_candidates WHERE id=? AND user_id=?",
            (memory["id"], user_id),
        )
        payload = self._memory_candidate_row(result) if result else memory
        self.audit(None, event_type, payload, user_id=user_id)
        return payload

    def list_memory_candidates(
        self,
        *,
        user_id: str = "default",
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["user_id=?"]
        params: list[Any] = [user_id]
        if status:
            clauses.append("status=?")
            params.append(status.strip().upper())
        rows = self.fetchall(
            "SELECT * FROM memory_candidates WHERE "
            + " AND ".join(clauses)
            + " ORDER BY updated_at DESC",
            tuple(params),
        )
        return [self._memory_candidate_row(row) for row in rows]

    def review_memory_candidate(
        self,
        candidate_id: str,
        *,
        action: str,
        user_id: str = "default",
        title: str | None = None,
        content: str | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        normalized_action = str(action or "").strip().upper()
        allowed_actions = {"CONFIRM", "EDIT_AND_CONFIRM", "REJECT", "ARCHIVE"}
        if normalized_action not in allowed_actions:
            raise ValueError("unsupported memory candidate review action")
        row = self.fetchone(
            "SELECT * FROM memory_candidates WHERE id=? AND user_id=?",
            (candidate_id, user_id),
        )
        if not row:
            raise KeyError(candidate_id)
        current_status = str(row["status"])
        if current_status != "CANDIDATE" and not (
            current_status == "CONFIRMED" and normalized_action == "ARCHIVE"
        ):
            raise ValueError("memory candidate is no longer reviewable")
        next_title = str(row["title"])
        next_content = str(row["content"])
        if normalized_action == "EDIT_AND_CONFIRM":
            if title is not None:
                next_title = title.strip()
            if content is not None:
                next_content = content.strip()
            if not next_title or not next_content:
                raise ValueError("confirmed memory title and content are required")
        status = {
            "CONFIRM": "CONFIRMED",
            "EDIT_AND_CONFIRM": "CONFIRMED",
            "REJECT": "REJECTED",
            "ARCHIVE": "ARCHIVED",
        }[normalized_action]
        now = now_iso()
        updated_cursor = self.execute(
            """UPDATE memory_candidates
               SET status=?, title=?, content=?, reviewed_at=?, reviewed_by=?,
                   review_action=?, review_notes=?, updated_at=?
               WHERE id=? AND user_id=? AND status=?""",
            (
                status,
                next_title,
                next_content,
                now,
                user_id,
                normalized_action,
                notes.strip(),
                now,
                candidate_id,
                user_id,
                current_status,
            ),
        )
        if getattr(updated_cursor, "rowcount", 1) != 1:
            raise ValueError("memory candidate is no longer reviewable")
        updated = self.fetchone(
            "SELECT * FROM memory_candidates WHERE id=? AND user_id=?",
            (candidate_id, user_id),
        )
        payload = self._memory_candidate_row(updated) if updated else {}
        self.audit(
            None,
            "MEMORY_CANDIDATE_REVIEWED",
            {
                **payload,
                "review_action": normalized_action,
                "review_notes": notes.strip(),
            },
            user_id=user_id,
        )
        return payload

    def record_memory_candidate_usage(
        self,
        candidate_id: str,
        task_id: str,
        *,
        user_id: str = "default",
        usage_type: str = "TASK_CONTEXT_INJECTED",
    ) -> dict[str, Any]:
        candidate = self.fetchone(
            "SELECT id, user_id, status FROM memory_candidates WHERE id=? AND user_id=?",
            (candidate_id, user_id),
        )
        if not candidate:
            raise KeyError(candidate_id)
        if str(candidate["status"]) != "CONFIRMED":
            raise ValueError("only confirmed memory candidates can be used")
        task = self.get_task(task_id)
        if not task or task.user_id != user_id:
            raise KeyError(task_id)
        normalized_type = str(usage_type or "").strip().upper()
        if not normalized_type:
            raise ValueError("memory usage type is required")
        usage = {
            "id": new_id("memory_usage"),
            "memory_candidate_id": candidate_id,
            "task_id": task_id,
            "user_id": user_id,
            "usage_type": normalized_type,
            "used_at": now_iso(),
        }
        cursor = self.execute(
            """INSERT OR IGNORE INTO memory_candidate_usages
               (id, memory_candidate_id, task_id, user_id, usage_type, used_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                usage["id"],
                usage["memory_candidate_id"],
                usage["task_id"],
                usage["user_id"],
                usage["usage_type"],
                usage["used_at"],
            ),
        )
        row = self.fetchone(
            """SELECT * FROM memory_candidate_usages
               WHERE memory_candidate_id=? AND task_id=? AND usage_type=? AND user_id=?""",
            (candidate_id, task_id, normalized_type, user_id),
        )
        payload = dict(row) if row else usage
        if getattr(cursor, "rowcount", 1) == 1:
            self.audit(
                task_id,
                "MEMORY_CANDIDATE_USED",
                payload,
                user_id=user_id,
            )
        return payload

    def list_memory_candidate_usages(
        self,
        candidate_id: str,
        *,
        user_id: str = "default",
    ) -> list[dict[str, Any]]:
        rows = self.fetchall(
            """SELECT u.*, t.created_at AS task_created_at, t.status AS task_status
               FROM memory_candidate_usages u
               JOIN research_tasks t ON t.id=u.task_id AND t.user_id=u.user_id
               WHERE u.memory_candidate_id=? AND u.user_id=?
               ORDER BY u.used_at DESC""",
            (candidate_id, user_id),
        )
        return [dict(row) for row in rows]

    def record_memory_candidate_feedback(
        self,
        candidate_id: str,
        *,
        rating: str,
        user_id: str = "default",
        usage_id: str | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        normalized_rating = str(rating or "").strip().upper()
        if normalized_rating not in {"HELPFUL", "NOT_HELPFUL", "UNCERTAIN"}:
            raise ValueError("unsupported memory candidate feedback rating")
        candidate = self.fetchone(
            "SELECT id, status FROM memory_candidates WHERE id=? AND user_id=?",
            (candidate_id, user_id),
        )
        if not candidate:
            raise KeyError(candidate_id)
        if str(candidate["status"]) != "CONFIRMED":
            raise ValueError("only confirmed memory candidates can receive feedback")
        if usage_id:
            usage = self.fetchone(
                """SELECT * FROM memory_candidate_usages
                   WHERE id=? AND memory_candidate_id=? AND user_id=?""",
                (usage_id, candidate_id, user_id),
            )
        else:
            usage = self.fetchone(
                """SELECT * FROM memory_candidate_usages
                   WHERE memory_candidate_id=? AND user_id=?
                   ORDER BY used_at DESC LIMIT 1""",
                (candidate_id, user_id),
            )
        if not usage:
            raise ValueError("memory candidate has no recorded usage")
        existing = self.fetchone(
            """SELECT * FROM memory_candidate_feedback
               WHERE memory_candidate_usage_id=? AND user_id=?""",
            (usage["id"], user_id),
        )
        now = now_iso()
        feedback = {
            "id": str(existing["id"]) if existing else new_id("memory_feedback"),
            "memory_candidate_id": candidate_id,
            "memory_candidate_usage_id": str(usage["id"]),
            "task_id": str(usage["task_id"]),
            "user_id": user_id,
            "rating": normalized_rating,
            "notes": notes.strip(),
            "created_at": str(existing["created_at"]) if existing else now,
            "updated_at": now,
        }
        if existing:
            self.execute(
                """UPDATE memory_candidate_feedback
                   SET rating=?, notes=?, updated_at=?
                   WHERE id=? AND user_id=?""",
                (
                    feedback["rating"],
                    feedback["notes"],
                    feedback["updated_at"],
                    feedback["id"],
                    user_id,
                ),
            )
            event_type = "MEMORY_CANDIDATE_FEEDBACK_UPDATED"
        else:
            self.execute(
                """INSERT INTO memory_candidate_feedback
                   (id, memory_candidate_id, memory_candidate_usage_id, task_id,
                    user_id, rating, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    feedback["id"],
                    feedback["memory_candidate_id"],
                    feedback["memory_candidate_usage_id"],
                    feedback["task_id"],
                    feedback["user_id"],
                    feedback["rating"],
                    feedback["notes"],
                    feedback["created_at"],
                    feedback["updated_at"],
                ),
            )
            event_type = "MEMORY_CANDIDATE_FEEDBACK_RECORDED"
        row = self.fetchone(
            "SELECT * FROM memory_candidate_feedback WHERE id=? AND user_id=?",
            (feedback["id"], user_id),
        )
        payload = dict(row) if row else feedback
        self.audit(
            str(usage["task_id"]),
            event_type,
            payload,
            user_id=user_id,
        )
        return payload

    def list_memory_candidate_feedback(
        self,
        candidate_id: str,
        *,
        user_id: str = "default",
    ) -> list[dict[str, Any]]:
        rows = self.fetchall(
            """SELECT * FROM memory_candidate_feedback
               WHERE memory_candidate_id=? AND user_id=?
               ORDER BY updated_at DESC""",
            (candidate_id, user_id),
        )
        return [dict(row) for row in rows]

    @staticmethod
    def _memory_candidate_row(row: Any) -> dict[str, Any]:
        if row is None:
            return {}
        result = dict(row)
        for key in ("source_task_ids_json", "source_rule_snapshot_ids_json"):
            raw = result.pop(key, "[]")
            try:
                result[key.removesuffix("_json")] = json.loads(raw or "[]")
            except (TypeError, json.JSONDecodeError):
                result[key.removesuffix("_json")] = []
        return result

    def save_retrospective(
        self,
        *,
        task_id: str,
        user_id: str,
        action_taken: str,
        outcome: dict[str, Any],
        notes: str = "",
        observed_at: str | None = None,
        rule_snapshot_id: str | None = None,
        data_snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist an immutable record of what happened after a recommendation."""
        task = self.get_task(task_id)
        if not task or task.user_id != user_id:
            raise KeyError(task_id)
        if not action_taken.strip():
            raise ValueError("action_taken is required")
        if not isinstance(outcome, dict):
            raise ValueError("outcome must be an object")
        normalized_outcome = dict(outcome)
        horizon = str(normalized_outcome.get("horizon") or "USER_RECORDED").strip().upper()
        if horizon not in self.RETROSPECTIVE_HORIZONS:
            raise ValueError("outcome.horizon must be T+5, T+20 or USER_RECORDED")
        normalized_outcome["horizon"] = horizon
        for field in ("return_pct", "benchmark_return_pct", "position_size_pct"):
            if field not in normalized_outcome or normalized_outcome[field] is None:
                continue
            try:
                value = float(normalized_outcome[field])
            except (TypeError, ValueError) as error:
                raise ValueError(f"outcome.{field} must be numeric") from error
            if not math.isfinite(value):
                raise ValueError(f"outcome.{field} must be finite")
            if field == "position_size_pct" and not 0 <= value <= 100:
                raise ValueError("outcome.position_size_pct must be between 0 and 100")
            normalized_outcome[field] = value
        if (
            normalized_outcome.get("return_pct") is not None
            and normalized_outcome.get("benchmark_return_pct") is not None
        ):
            normalized_outcome["excess_return_pct"] = round(
                normalized_outcome["return_pct"]
                - normalized_outcome["benchmark_return_pct"],
                6,
            )
        if observed_at:
            try:
                parsed_observed_at = datetime.fromisoformat(
                    observed_at.replace("Z", "+00:00")
                )
            except ValueError as error:
                raise ValueError("observed_at must be an ISO-8601 timestamp") from error
            if parsed_observed_at.tzinfo is None:
                parsed_observed_at = parsed_observed_at.replace(tzinfo=timezone.utc)
            if parsed_observed_at > datetime.now(timezone.utc):
                raise ValueError("observed_at cannot be in the future")
        retrospective = {
            "id": new_id("retrospective"),
            "task_id": task_id,
            "user_id": user_id,
            "action_taken": action_taken.strip().upper(),
            "outcome": normalized_outcome,
            "notes": notes.strip(),
            "observed_at": observed_at or now_iso(),
            "rule_snapshot_id": rule_snapshot_id or task.rule_snapshot_id,
            "data_snapshot_id": data_snapshot_id or task.data_snapshot_id,
            "created_at": now_iso(),
        }
        self.execute(
            """INSERT INTO task_retrospectives
               (id, task_id, user_id, action_taken, outcome_json, notes,
                observed_at, rule_snapshot_id, data_snapshot_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                retrospective["id"],
                retrospective["task_id"],
                retrospective["user_id"],
                retrospective["action_taken"],
                json.dumps(normalized_outcome, ensure_ascii=False, sort_keys=True),
                retrospective["notes"],
                retrospective["observed_at"],
                retrospective["rule_snapshot_id"],
                retrospective["data_snapshot_id"],
                retrospective["created_at"],
            ),
        )
        return retrospective

    def list_retrospectives(
        self,
        task_id: str,
        user_id: str = "default",
    ) -> list[dict[str, Any]]:
        task = self.get_task(task_id)
        if not task or task.user_id != user_id:
            return []
        rows = self.fetchall(
            """SELECT * FROM task_retrospectives
               WHERE task_id=? AND user_id=?
               ORDER BY observed_at DESC, created_at DESC""",
            (task_id, user_id),
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            value = dict(row)
            value["outcome"] = json.loads(value.pop("outcome_json") or "{}")
            results.append(value)
        return results

    def recover_incomplete_tasks(self) -> int:
        rows = self.fetchall(
            """SELECT * FROM research_tasks
               WHERE status IN ('PLANNING', 'RUNNING', 'REVIEWING', 'PAUSED')"""
        )
        for row in rows:
            task = self._task_from_row(row)
            task.status = TaskStatus.RETRYABLE
            task.finished_at = now_iso()
            task.error = {
                "code": "RUNTIME_RESTARTED",
                "message": "Task was recovered after the local runtime restarted.",
            }
            self.update_task(task)
        return len(rows)

    def backup_to(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup = sqlite3.connect(destination)
        try:
            with self.lock:
                self.connection.backup(backup)
        finally:
            backup.close()

    def acquire_lease(self, task_id: str, worker_id: str, ttl_seconds: int = 60) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl_seconds)
        lease_id = f"lease_{task_id}_{worker_id}"
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM task_leases WHERE task_id=? AND status='ACTIVE'",
                (task_id,),
            ).fetchone()
            if row:
                expires_at = datetime.fromisoformat(row["expires_at"])
                if expires_at > now:
                    raise ValueError("task lease is already held")
                self.connection.execute(
                    "UPDATE task_leases SET status='EXPIRED' WHERE lease_id=?",
                    (row["lease_id"],),
                )
                self.audit(task_id, "TASK_LEASE_EXPIRED", {
                    "lease_id": row["lease_id"],
                    "worker_id": row["worker_id"],
                })
            task = self.connection.execute(
                "SELECT status FROM research_tasks WHERE id=?",
                (task_id,),
            ).fetchone()
            if not task:
                raise KeyError(task_id)
            if task["status"] != TaskStatus.QUEUED.value:
                raise ValueError(f"task is not queued from {task['status']}")
            self.connection.execute(
                """INSERT OR REPLACE INTO task_leases
                   (task_id, lease_id, worker_id, acquired_at, heartbeat_at, expires_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE')""",
                (task_id, lease_id, worker_id, now.isoformat(), now.isoformat(), expires.isoformat()),
            )
            self.connection.commit()
        self.audit(task_id, "TASK_LEASE_ACQUIRED", {"lease_id": lease_id, "worker_id": worker_id, "expires_at": expires.isoformat()})
        return {"task_id": task_id, "lease_id": lease_id, "worker_id": worker_id, "expires_at": expires.isoformat()}

    def list_queued_tasks(self) -> list[Task]:
        rows = self.fetchall(
            "SELECT * FROM research_tasks WHERE status=? ORDER BY created_at",
            (TaskStatus.QUEUED.value,),
        )
        tasks = [self._task_from_row(row) for row in rows]
        tasks.sort(
            key=lambda task: (
                -int(task.target.get("_priority", 0)),
                task.target.get("_next_retry_at", ""),
                task.created_at,
            )
        )
        return tasks

    def heartbeat_lease(
        self,
        lease_id: str,
        worker_id: str,
        ttl_seconds: int = 60,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl_seconds)
        lease = self.fetchone(
            """SELECT l.task_id, t.user_id
               FROM task_leases l
               JOIN research_tasks t ON t.id=l.task_id
               WHERE l.lease_id=? AND l.worker_id=? AND l.status='ACTIVE'""",
            (lease_id, worker_id),
        )
        if not lease or (user_id is not None and str(lease["user_id"]) != user_id):
            raise KeyError(lease_id)
        cursor = self.execute(
            """UPDATE task_leases SET heartbeat_at=?, expires_at=?
               WHERE lease_id=? AND worker_id=? AND status='ACTIVE'""",
            (now.isoformat(), expires.isoformat(), lease_id, worker_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(lease_id)
        return {"lease_id": lease_id, "worker_id": worker_id, "expires_at": expires.isoformat()}

    def release_lease(
        self,
        lease_id: str,
        worker_id: str,
        user_id: str | None = None,
    ) -> None:
        lease = self.fetchone(
            """SELECT l.task_id, t.user_id
               FROM task_leases l
               JOIN research_tasks t ON t.id=l.task_id
               WHERE l.lease_id=? AND l.worker_id=? AND l.status='ACTIVE'""",
            (lease_id, worker_id),
        )
        if not lease:
            raise KeyError(lease_id)
        lease_user_id = str(lease["user_id"])
        if user_id is not None and lease_user_id != user_id:
            raise KeyError(lease_id)
        cursor = self.execute(
            "UPDATE task_leases SET status='RELEASED' WHERE lease_id=? AND worker_id=? AND status='ACTIVE'",
            (lease_id, worker_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(lease_id)
        self.audit(
            lease["task_id"],
            "TASK_LEASE_RELEASED",
            {"lease_id": lease_id, "worker_id": worker_id},
            user_id=lease_user_id,
        )

    def create_notification(
        self,
        event_type: str,
        title: str,
        body: str,
        task_id: str | None = None,
        user_id: str = "default",
    ) -> dict[str, Any]:
        notification = {
            "id": new_id("notification"),
            "user_id": user_id,
            "task_id": task_id,
            "event_type": event_type,
            "title": title,
            "body": body,
            "created_at": now_iso(),
            "read_at": None,
        }
        self.execute(
            """INSERT INTO notifications
               (id, user_id, task_id, event_type, title, body, created_at, read_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
            (
                notification["id"],
                notification["user_id"],
                task_id,
                event_type,
                title,
                body,
                notification["created_at"],
            ),
        )
        return notification

    def save_price_volume_digest(self, data: dict[str, Any], user_id: str) -> None:
        key = hashlib.sha256(f"{data['as_of']}:{user_id}".encode()).hexdigest()
        items = data["items"]
        reasons = [
            label.format(count) for label, count in (
                ("{} 个涨跌幅达阈值", sum(item["price_triggered"] for item in items)),
                ("{} 个放量", sum(item["volume_triggered"] for item in items)),
            ) if count
        ]
        self.execute(
            """INSERT INTO notifications (id, user_id, event_type, title, body, created_at, data_json)
               VALUES (?, ?, 'PriceVolumeDigest', ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET title=excluded.title, body=excluded.body, data_json=excluded.data_json""",
            (f"price-volume-digest-{key}", user_id, f"你关注的 {len(items)} 个标的出现异动",
             " · ".join(reasons), now_iso(), json.dumps(data, ensure_ascii=False)),
        )

    @staticmethod
    def _notification_task_json(key: str) -> str:
        return f"json_extract(t.target_json, '$.{key}')"

    def _legacy_anomaly_query(self) -> str:
        as_of = self._notification_task_json("as_of")
        event_id = self._notification_task_json("_event_id")
        return f"""SELECT n.id, n.task_id, n.created_at, n.read_at, {as_of} AS as_of,
                          t.target_json, t.status, t.error_json
                   FROM notifications n
                   JOIN research_tasks t ON t.id=n.task_id AND t.user_id=n.user_id
                   JOIN events e ON e.id={event_id} AND e.user_id=n.user_id
                   WHERE n.user_id=? AND n.event_type='PriceVolumeAnomaly'
                     AND substr(e.dedupe_key, length(n.user_id)+2, 13)='price-volume:'
                     AND {as_of} IS NOT NULL"""

    def list_notifications(self, unread_only: bool = False, user_id: str = "default") -> list[dict[str, Any]]:
        unread_filter = "WHERE read_at IS NULL" if unread_only else ""
        rows = self.fetchall(
            f"""WITH legacy AS ({self._legacy_anomaly_query()}), inbox AS (
                   SELECT n.id, n.user_id, n.task_id, n.event_type, n.title, n.body,
                          n.created_at, n.read_at, n.data_json, NULL AS as_of, NULL AS count
                   FROM notifications n LEFT JOIN legacy ON legacy.id=n.id
                   WHERE n.user_id=? AND legacy.id IS NULL
                     AND substr(n.id, 1, length(?))<>?
                   UNION ALL
                   SELECT ? || as_of, ?, NULL, 'PriceVolumeHistory', '', '', MAX(created_at),
                          CASE WHEN COUNT(read_at)=COUNT(*) THEN MAX(read_at) END, NULL, as_of, COUNT(*)
                   FROM legacy GROUP BY as_of
                   UNION ALL
                   SELECT ? || t.id, t.user_id, t.id, 'TaskWaitingApproval',
                          CASE WHEN t.trigger_type='MarketClose' THEN '收盘复盘等待确认'
                               ELSE COALESCE({self._notification_task_json("symbol")} || ' 研究等待确认', '研究等待确认') END,
                          '查看研究结论并提交你的决定。', COALESCE(t.started_at, t.created_at),
                          n.read_at, NULL, NULL, NULL
                   FROM research_tasks t
                   LEFT JOIN notifications n ON n.id=? || t.id AND n.user_id=t.user_id
                   WHERE t.user_id=? AND t.status='WAITING_APPROVAL'
               )
               SELECT * FROM inbox {unread_filter}
               ORDER BY CASE WHEN event_type='TaskWaitingApproval' OR (read_at IS NULL AND event_type IN (
                   'PortfolioRiskChanged', 'DataQualityDegraded', 'TaskFailed', 'EventDeliveryFailed'
               )) THEN 0 ELSE 1 END, created_at DESC, id DESC LIMIT 100""",
            (user_id, user_id, self.APPROVAL_NOTIFICATION_PREFIX, self.APPROVAL_NOTIFICATION_PREFIX,
             self.LEGACY_ANOMALY_PREFIX, user_id, self.APPROVAL_NOTIFICATION_PREFIX,
             self.APPROVAL_NOTIFICATION_PREFIX, user_id),
        )
        notifications = []
        for row in rows:
            notification = dict(row)
            encoded = notification.pop("data_json")
            count = notification.pop("count")
            as_of = notification.pop("as_of")
            if encoded:
                notification["data"] = json.loads(encoded)
            if count:
                notification["title"] = f"{as_of} · {count} 条历史异动研究"
                notification["body"] = "查看这批自动研究的状态和失败原因。"
                notification["data"] = {"as_of": as_of, "count": count}
            notifications.append(notification)
        return notifications

    def legacy_anomaly_notifications(self, notification_id: str, user_id: str) -> list[dict[str, Any]]:
        if not notification_id.startswith(self.LEGACY_ANOMALY_PREFIX):
            raise KeyError(notification_id)
        rows = self.fetchall(
            f"""SELECT * FROM ({self._legacy_anomaly_query()}) legacy
                WHERE as_of=? ORDER BY created_at DESC, id DESC""",
            (user_id, notification_id.removeprefix(self.LEGACY_ANOMALY_PREFIX)),
        )
        if not rows:
            raise KeyError(notification_id)
        return [
            {"task_id": row["task_id"], "symbol": json.loads(row["target_json"]).get("symbol"),
             "status": row["status"], "error": json.loads(row["error_json"]) if row["error_json"] else None}
            for row in rows
        ]

    def record_notification_delivery(
        self,
        notification_id: str,
        user_id: str,
        provider_id: str,
        status: str,
        detail: str | None = None,
    ) -> dict[str, Any]:
        delivery = {
            "id": new_id("notification_delivery"),
            "notification_id": notification_id,
            "user_id": user_id,
            "provider_id": provider_id,
            "status": status,
            "detail": detail,
            "created_at": now_iso(),
        }
        self.execute(
            """INSERT INTO notification_deliveries
               (id, notification_id, user_id, provider_id, status, detail, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                delivery["id"],
                delivery["notification_id"],
                delivery["user_id"],
                delivery["provider_id"],
                delivery["status"],
                delivery["detail"],
                delivery["created_at"],
            ),
        )
        return delivery

    def list_notification_deliveries(
        self,
        notification_id: str | None = None,
        user_id: str = "default",
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT d.* FROM notification_deliveries d "
            "JOIN notifications n ON n.id=d.notification_id "
            "WHERE d.user_id=? AND n.user_id=?"
        )
        params: list[Any] = [user_id, user_id]
        if notification_id:
            query += " AND d.notification_id=?"
            params.append(notification_id)
        query += " ORDER BY d.created_at DESC LIMIT 100"
        return [
            dict(row)
            for row in self.fetchall(query, tuple(params))
        ]

    def register_device(
        self,
        device_id: str,
        platform: str,
        device_name: str | None = None,
        push_token: str | None = None,
        user_id: str = "default",
    ) -> dict[str, Any]:
        now = now_iso()
        with self.lock:
            existing = self.connection.execute(
                "SELECT user_id FROM devices WHERE device_id=?",
                (device_id,),
            ).fetchone()
            if existing and existing["user_id"] != user_id:
                raise ValueError("device is already registered to another user")
            self.connection.execute(
                """INSERT INTO devices
                   (device_id, user_id, platform, device_name, push_token, created_at, last_seen_at, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                   ON CONFLICT(device_id) DO UPDATE SET
                     platform=excluded.platform,
                     device_name=excluded.device_name,
                     push_token=excluded.push_token,
                     last_seen_at=excluded.last_seen_at,
                     active=1""",
                (device_id, user_id, platform, device_name, push_token, now, now),
            )
            self.connection.commit()
        self.audit(None, "DEVICE_REGISTERED", {
            "device_id": device_id,
            "user_id": user_id,
            "platform": platform,
        })
        row = self.fetchone(
            "SELECT * FROM devices WHERE device_id=? AND user_id=?",
            (device_id, user_id),
        )
        return dict(row) if row else {}

    def list_devices(self, user_id: str = "default") -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.fetchall(
                "SELECT * FROM devices WHERE user_id=? AND active=1 ORDER BY last_seen_at DESC",
                (user_id,),
            )
        ]

    def unregister_device(self, device_id: str, user_id: str = "default") -> None:
        """Deactivate one device without deleting its audit history."""
        cursor = self.execute(
            "UPDATE devices SET active=0, last_seen_at=? WHERE device_id=? AND user_id=? AND active=1",
            (now_iso(), device_id, user_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(device_id)
        self.audit(None, "DEVICE_UNREGISTERED", {
            "device_id": device_id,
            "user_id": user_id,
        })

    def get_idempotent_response(
        self,
        user_id: str,
        operation: str,
        key: str,
        request_hash: str | None = None,
    ) -> dict[str, Any] | None:
        row = self.fetchone(
            """SELECT response_json, request_hash FROM idempotency_keys
               WHERE user_id=? AND operation=? AND key=?""",
            (user_id, operation, key),
        )
        if (
            row
            and request_hash
            and row["request_hash"]
            and row["request_hash"] != request_hash
        ):
            raise ValueError("idempotency key was reused with a different request")
        return json.loads(row["response_json"]) if row else None

    def save_idempotent_response(
        self,
        user_id: str,
        operation: str,
        key: str,
        response: dict[str, Any],
        request_hash: str = "",
    ) -> dict[str, Any]:
        self.execute(
            """INSERT INTO idempotency_keys
               (user_id, operation, key, response_json, created_at, request_hash)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, operation, key) DO NOTHING""",
            (
                user_id,
                operation,
                key,
                json.dumps(response, ensure_ascii=False),
                now_iso(),
                request_hash,
            ),
        )
        return self.get_idempotent_response(user_id, operation, key, request_hash) or response

    def sync_changes(
        self,
        cursor: int = 0,
        limit: int = 100,
        user_id: str = "default",
    ) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit), 500))
        rows = self.fetchall(
            """SELECT id, task_id, user_id, event_type, payload_json, created_at
               FROM audit_log
               WHERE id > ? AND user_id=?
               ORDER BY id
               LIMIT ?""",
            (max(0, int(cursor)), user_id, bounded_limit),
        )
        changes: list[dict[str, Any]] = []
        max_cursor = max(int(cursor), *(int(row["id"]) for row in rows)) if rows else int(cursor)
        has_more = False
        if rows:
            has_more = bool(
                self.fetchone(
                    "SELECT 1 FROM audit_log WHERE id > ? AND user_id=? LIMIT 1",
                    (max_cursor, user_id),
                )
            )
        for row in rows:
            payload = json.loads(row["payload_json"])
            if row["task_id"]:
                task = self.get_task(row["task_id"])
                if not task or task.user_id != user_id:
                    continue
            changes.append({
                "cursor": int(row["id"]),
                "task_id": row["task_id"],
                "event_type": row["event_type"],
                "payload": payload,
                "created_at": row["created_at"],
            })
        return {
            "cursor": int(cursor),
            "next_cursor": max_cursor,
            "has_more": has_more,
            "changes": changes,
        }

    def mark_notification_read(self, notification_id: str, user_id: str = "default") -> None:
        if notification_id.startswith(self.APPROVAL_NOTIFICATION_PREFIX):
            now = now_iso()
            cursor = self.execute(
                """INSERT INTO notifications (id, user_id, task_id, event_type, title, body, created_at, read_at)
                   SELECT ?, user_id, id, 'TaskWaitingApproval', '', '', ?, ?
                   FROM research_tasks WHERE id=? AND user_id=? AND status='WAITING_APPROVAL'
                   ON CONFLICT(id) DO UPDATE SET read_at=COALESCE(notifications.read_at, excluded.read_at)""",
                (notification_id, now, now, notification_id.removeprefix(self.APPROVAL_NOTIFICATION_PREFIX), user_id),
            )
            if not cursor.rowcount:
                raise KeyError(notification_id)
            return
        if notification_id.startswith(self.LEGACY_ANOMALY_PREFIX):
            cursor = self.execute(
                f"""UPDATE notifications SET read_at=COALESCE(read_at, ?)
                    WHERE id IN (SELECT id FROM ({self._legacy_anomaly_query()}) legacy WHERE as_of=?)""",
                (now_iso(), user_id, notification_id.removeprefix(self.LEGACY_ANOMALY_PREFIX)),
            )
            if not cursor.rowcount:
                raise KeyError(notification_id)
            return
        cursor = self.execute(
            "UPDATE notifications SET read_at=? WHERE id=? AND user_id=?",
            (now_iso(), notification_id, user_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(notification_id)

    @staticmethod
    def restore_from(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_db = sqlite3.connect(source)
        destination_db = sqlite3.connect(destination)
        try:
            source_db.backup(destination_db)
        finally:
            destination_db.close()
            source_db.close()

    def save_ruleset(self, rules: dict[str, Any], user_id: str = "default") -> str:
        version = str(rules["version"])
        ruleset_id = (
            f"ruleset_{version}"
            if user_id == "default"
            else f"ruleset_{hashlib.sha256(user_id.encode()).hexdigest()[:12]}_{version}"
        )
        payload = json.dumps(rules, ensure_ascii=False, sort_keys=True)
        self.execute(
            """INSERT OR IGNORE INTO rulesets
               (id, user_id, version, definition_json, created_at, active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (ruleset_id, user_id, version, payload, now_iso()),
        )
        self.execute(
            """INSERT OR IGNORE INTO rule_snapshots
               (id, ruleset_id, version, definition_hash, definition_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ruleset_id, ruleset_id, version, hashlib.sha256(payload.encode()).hexdigest(), payload, now_iso()),
        )
        self.execute(
            "UPDATE rulesets SET active=CASE WHEN id=? THEN 1 ELSE 0 END WHERE user_id=?",
            (ruleset_id, user_id),
        )
        return ruleset_id

    def get_ruleset(self, user_id: str = "default") -> dict[str, Any] | None:
        row = self.fetchone(
            """SELECT id, user_id, version, definition_json, created_at
               FROM rulesets
               WHERE user_id=? AND active=1
               ORDER BY created_at DESC LIMIT 1""",
            (user_id,),
        )
        if not row:
            return None
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "version": row["version"],
            "rules": json.loads(row["definition_json"]),
            "created_at": row["created_at"],
        }

    def get_rule_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        row = self.fetchone(
            """SELECT id, ruleset_id, version, definition_json, created_at
               FROM rule_snapshots WHERE id=?""",
            (snapshot_id,),
        )
        if not row:
            return None
        return {
            "id": row["id"],
            "ruleset_id": row["ruleset_id"],
            "version": row["version"],
            "rules": json.loads(row["definition_json"]),
            "created_at": row["created_at"],
        }

    def save_market_snapshot(self, snapshot: dict[str, Any]) -> str:
        snapshot_id = snapshot["snapshot_id"]
        self.execute(
            """INSERT OR REPLACE INTO market_snapshots
               (id, as_of, observed_at, source, quality, payload_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                snapshot["as_of"],
                snapshot["observed_at"],
                snapshot["source"],
                snapshot["quality"],
                json.dumps(snapshot, ensure_ascii=False),
            ),
        )
        return snapshot_id

    def get_market_snapshot_for_as_of(
        self,
        as_of: str,
        *,
        sources: list[str] | None = None,
        reusable_qualities: tuple[str, ...] = ("verified", "partial"),
    ) -> dict[str, Any] | None:
        """Return the newest reusable market snapshot for a requested date."""
        qualities = tuple(str(value) for value in reusable_qualities if str(value).strip())
        if not qualities:
            return None
        quality_placeholders = ",".join("?" for _ in qualities)
        params: list[Any] = [as_of, *qualities]
        source_clause = ""
        if sources:
            normalized_sources = [str(value).strip() for value in sources if str(value).strip()]
            if normalized_sources:
                source_placeholders = ",".join("?" for _ in normalized_sources)
                source_clause = f" AND source IN ({source_placeholders})"
                params.extend(normalized_sources)
        row = self.fetchone(
            f"""SELECT payload_json
                FROM market_snapshots
                WHERE as_of=?
                  AND quality IN ({quality_placeholders})
                  {source_clause}
                ORDER BY observed_at DESC, id DESC
                LIMIT 1""",
            tuple(params),
        )
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        return payload if isinstance(payload, dict) else None

    def save_portfolio_snapshot(self, snapshot: dict[str, Any]) -> str:
        snapshot_id = snapshot["snapshot_id"]
        self.execute(
            """INSERT OR REPLACE INTO portfolio_snapshots
               (id, user_id, as_of, cash, total_value, source, payload_json, observed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                snapshot["user_id"],
                snapshot["as_of"],
                snapshot["cash"],
                snapshot["total_value"],
                snapshot["source"],
                json.dumps(snapshot, ensure_ascii=False),
                snapshot.get("observed_at"),
            ),
        )
        return snapshot_id

    def get_latest_portfolio_snapshot(
        self, user_id: str = "default", *, as_of: str | None = None, include_fixture: bool = True,
    ) -> dict[str, Any] | None:
        filters = ["user_id=?"]
        params: list[Any] = [user_id]
        if as_of is not None:
            filters.append("as_of<=?")
            params.append(as_of)
        if not include_fixture:
            filters.append("source <> 'fixture'")
        row = self.fetchone(
            f"""SELECT payload_json FROM portfolio_snapshots
               WHERE {' AND '.join(filters)}
               ORDER BY as_of DESC, observed_at DESC NULLS LAST, id DESC
               LIMIT 1""",
            tuple(params),
        )
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        return payload if isinstance(payload, dict) else None

    def create_task(self, task: Task) -> None:
        self.execute(
            """INSERT INTO research_tasks
               (id, user_id, trigger_type, target_json, status, created_at,
                started_at, finished_at, data_snapshot_id, rule_snapshot_id, error_json, parent_task_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id,
                task.user_id,
                task.trigger_type,
                json.dumps(task.target, ensure_ascii=False),
                task.status.value,
                task.created_at,
                task.started_at,
                task.finished_at,
                task.data_snapshot_id,
                task.rule_snapshot_id,
                json.dumps(task.error) if task.error else None,
                task.parent_task_id,
            ),
        )
        self.audit(task.id, "TASK_CREATED", task.to_dict())

    def update_task(self, task: Task) -> None:
        self.execute(
            """UPDATE research_tasks SET target_json=?, status=?, started_at=?, finished_at=?,
               data_snapshot_id=?, rule_snapshot_id=?, error_json=?,
               pause_requested=CASE
                 WHEN ? = 1 THEN 1
                 WHEN ? IN ('CANCELLED', 'FAILED', 'RETRYABLE', 'TIMEOUT', 'EXPIRED',
                            'DONE', 'APPROVED', 'REJECTED', 'BLOCKED', 'NO_ACTION') THEN 0
                 ELSE pause_requested
               END WHERE id=?""",
            (
                json.dumps(task.target, ensure_ascii=False),
                task.status.value,
                task.started_at,
                task.finished_at,
                task.data_snapshot_id,
                task.rule_snapshot_id,
                json.dumps(task.error) if task.error else None,
                int(task.status == TaskStatus.PAUSED),
                task.status.value,
                task.id,
            ),
        )
        self.audit(task.id, "TASK_STATE_CHANGED", task.to_dict())

    def set_task_pause_requested(self, task_id: str, requested: bool) -> None:
        """Persist a control request without relying on the caller's process memory."""
        self.execute(
            "UPDATE research_tasks SET pause_requested=? WHERE id=?",
            (int(requested), task_id),
        )

    def get_task_control(self, task_id: str) -> tuple[str, bool] | None:
        row = self.fetchone(
            "SELECT status, pause_requested FROM research_tasks WHERE id=?",
            (task_id,),
        )
        if not row:
            return None
        return str(row["status"]), bool(row["pause_requested"])

    def get_task(self, task_id: str) -> Task | None:
        row = self.fetchone(
            "SELECT * FROM research_tasks WHERE id=?", (task_id,)
        )
        return self._task_from_row(row) if row else None

    def list_tasks(self, user_id: str | None = "default") -> list[Task]:
        if user_id is None:
            rows = self.fetchall(
                "SELECT * FROM research_tasks ORDER BY created_at DESC"
            )
        else:
            rows = self.fetchall(
                "SELECT * FROM research_tasks WHERE user_id=? ORDER BY created_at DESC",
                (user_id,),
            )
        return [self._task_from_row(row) for row in rows]

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            user_id=row["user_id"],
            trigger_type=row["trigger_type"],
            target=json.loads(row["target_json"]),
            status=TaskStatus(row["status"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            data_snapshot_id=row["data_snapshot_id"],
            rule_snapshot_id=row["rule_snapshot_id"],
            error=json.loads(row["error_json"]) if row["error_json"] else None,
            parent_task_id=row["parent_task_id"],
        )

    def save_agent_run(
        self,
        task_id: str,
        agent_name: str,
        status: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any] | None,
        started_at: str,
        finished_at: str | None,
        model: str | None = None,
        token_usage: int | None = None,
    ) -> str:
        run_id = f"run_{task_id}_{agent_name.lower().replace(' ', '_')}"
        self.execute(
            """INSERT OR REPLACE INTO agent_runs
               (id, task_id, agent_name, status, input_json, output_json,
                started_at, finished_at, model, token_usage)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                task_id,
                agent_name,
                status,
                json.dumps(input_data, ensure_ascii=False),
                json.dumps(output_data, ensure_ascii=False) if output_data else None,
                started_at,
                finished_at,
                model,
                token_usage,
            ),
        )
        self.append_event(task_id, "AGENT_TRACE", {
            "agent_name": agent_name,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "output": output_data,
        })
        return run_id

    def save_llm_usage(
        self,
        *,
        task_id: str,
        user_id: str,
        provider_id: str,
        model: str,
        usage: dict[str, Any],
        cost_usd: float = 0.0,
        cost_estimated: bool = False,
        request_count: int = 1,
    ) -> dict[str, Any]:
        prompt_tokens = _usage_int(usage, "prompt_tokens")
        completion_tokens = _usage_int(usage, "completion_tokens")
        total_tokens = _usage_int(usage, "total_tokens") or (
            prompt_tokens + completion_tokens
        )
        record = {
            "id": new_id("llm_usage"),
            "task_id": task_id,
            "user_id": user_id,
            "provider_id": provider_id,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": round(max(0.0, float(cost_usd)), 8),
            "cost_estimated": bool(cost_estimated),
            "request_count": max(1, int(request_count)),
            "created_at": now_iso(),
        }
        self.execute(
            """INSERT INTO llm_usage
               (id, task_id, user_id, provider_id, model, prompt_tokens,
                completion_tokens, total_tokens, cost_usd, cost_estimated,
                request_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["id"],
                record["task_id"],
                record["user_id"],
                record["provider_id"],
                record["model"],
                record["prompt_tokens"],
                record["completion_tokens"],
                record["total_tokens"],
                record["cost_usd"],
                int(record["cost_estimated"]),
                record["request_count"],
                record["created_at"],
            ),
        )
        self.audit(
            task_id,
            "LLM_USAGE_RECORDED",
            {
                key: value
                for key, value in record.items()
                if key not in {"id", "task_id", "user_id"}
            },
            user_id=user_id,
        )
        return record

    def llm_usage_summary(
        self,
        user_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if user_id is not None:
            clauses.append("user_id=?")
            params.append(user_id)
        if task_id is not None:
            clauses.append("task_id=?")
            params.append(task_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        row = self.fetchone(
            f"""SELECT COUNT(*) AS records,
                       COALESCE(SUM(request_count), 0) AS request_count,
                       COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                       COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                       COALESCE(SUM(total_tokens), 0) AS total_tokens,
                       COALESCE(SUM(cost_usd), 0) AS cost_usd
                FROM llm_usage{where}""",
            tuple(params),
        )
        if not row:
            return {
                "records": 0,
                "request_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
            }
        return {
            "records": int(row["records"] or 0),
            "request_count": int(row["request_count"] or 0),
            "prompt_tokens": int(row["prompt_tokens"] or 0),
            "completion_tokens": int(row["completion_tokens"] or 0),
            "total_tokens": int(row["total_tokens"] or 0),
            "cost_usd": round(float(row["cost_usd"] or 0), 8),
        }

    def save_tool_call(
        self,
        task_id: str,
        agent_run_id: str,
        tool_name: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any] | None,
        status: str = "DONE",
    ) -> str:
        call_id = new_id("tool")
        self.execute(
            """INSERT INTO tool_calls
               (id, task_id, agent_run_id, tool_name, input_json, output_json, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                call_id,
                task_id,
                agent_run_id,
                tool_name,
                json.dumps(input_data, ensure_ascii=False),
                json.dumps(output_data, ensure_ascii=False) if output_data is not None else None,
                status,
                now_iso(),
            ),
        )
        return call_id

    def save_evidence(self, task_id: str, evidence: Evidence) -> None:
        self.execute(
            """INSERT OR REPLACE INTO evidence
               (id, task_id, source, provider_id, source_type, source_uri, title,
                observed_at, as_of, expires_at, quality, excerpt, content_hash,
                snapshot_id, provenance_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evidence.id,
                task_id,
                evidence.source,
                evidence.provider_id,
                evidence.source_type,
                evidence.source_uri,
                evidence.title,
                evidence.observed_at,
                evidence.as_of,
                evidence.expires_at,
                evidence.quality,
                evidence.excerpt,
                hashlib.sha256(evidence.excerpt.encode()).hexdigest(),
                evidence.snapshot_id,
                json.dumps(evidence.provenance),
            ),
        )
        self.append_event(task_id, "EVIDENCE_SAVED", evidence.to_dict())

    def save_decision(self, task_id: str, decision: Decision) -> None:
        self.execute(
            """INSERT OR REPLACE INTO decisions
               (id, task_id, status, confidence, rationale_json, invalidation_json,
                risk_level, next_action, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision.id,
                task_id,
                decision.status.value,
                decision.confidence,
                json.dumps({"items": decision.rationale, "rules": decision.rule_result.to_dict(),
                            "synthesis": decision.synthesis}, ensure_ascii=False),
                json.dumps(decision.invalidation, ensure_ascii=False),
                decision.risk_level,
                decision.next_action,
                decision.created_at,
            ),
        )
        self.append_event(task_id, "DECISION_CREATED", decision.to_dict())

    def get_task_detail(self, task_id: str, user_id: str | None = "default") -> dict[str, Any] | None:
        with self.lock:
            task = self.get_task(task_id)
            if not task:
                return None
            if user_id is not None and task.user_id != user_id:
                return None
            decision = self.connection.execute(
                "SELECT * FROM decisions WHERE task_id=?", (task_id,)
            ).fetchone()
            evidence = self.connection.execute(
                "SELECT * FROM evidence WHERE task_id=? ORDER BY observed_at DESC", (task_id,)
            ).fetchall()
            trace = self.connection.execute(
                "SELECT * FROM agent_runs WHERE task_id=? ORDER BY started_at", (task_id,)
            ).fetchall()
            approvals = self.connection.execute(
                "SELECT * FROM approvals WHERE task_id=? ORDER BY created_at", (task_id,)
            ).fetchall()
            tool_calls = self.connection.execute(
                "SELECT * FROM tool_calls WHERE task_id=? ORDER BY created_at", (task_id,)
            ).fetchall()
            usage = self.connection.execute(
                """SELECT COUNT(*) AS records,
                          COALESCE(SUM(request_count), 0) AS request_count,
                          COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                          COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                          COALESCE(SUM(total_tokens), 0) AS total_tokens,
                          COALESCE(SUM(cost_usd), 0) AS cost_usd
                   FROM llm_usage WHERE task_id=?""",
                (task_id,),
            ).fetchone()
            events = self.connection.execute(
                "SELECT event_type, payload_json, created_at FROM task_events WHERE task_id=? ORDER BY id",
                (task_id,),
            ).fetchall()
            retrospectives = self.connection.execute(
                """SELECT * FROM task_retrospectives
                   WHERE task_id=? AND user_id=?
                   ORDER BY observed_at DESC, created_at DESC""",
                (task_id, task.user_id),
            ).fetchall()
        trace_rows = [dict(row) for row in trace]
        evidence_rows = [dict(row) for row in evidence]
        for row in evidence_rows:
            row["provenance"] = json.loads(row.pop("provenance_json", "{}"))
        if not evidence_rows:
            pack = self.get_context_pack(task_id, task.user_id)
            if pack and pack["execution_mode"] == "replay":
                evidence_rows = [{**item, "task_id": task_id} for item in pack["evidence"]]
        evidence_usage: dict[str, set[str]] = {
            str(row["id"]): set() for row in evidence_rows
        }
        for trace_row in trace_rows:
            referenced_ids: set[str] = set()
            for field_name in ("input_json", "output_json"):
                raw_payload = trace_row.get(field_name)
                if not raw_payload:
                    continue
                try:
                    payload = json.loads(raw_payload)
                except (TypeError, ValueError):
                    continue
                ids = payload.get("evidence_ids", []) if isinstance(payload, dict) else []
                if isinstance(ids, list):
                    referenced_ids.update(str(item) for item in ids)
            for evidence_id in referenced_ids.intersection(evidence_usage):
                evidence_usage[evidence_id].add(str(trace_row["agent_name"]))
        if decision:
            for evidence_id, users in evidence_usage.items():
                if users:
                    users.add("Final decision")
        for evidence_row in evidence_rows:
            evidence_row["used_by"] = sorted(evidence_usage.get(str(evidence_row["id"]), set()))
        debate: dict[str, Any] = {}
        for row in trace_rows:
            if row["agent_name"] in {"Bull Case Analyst", "Bear Case Analyst", "Debate Chair"}:
                debate[row["agent_name"]] = json.loads(row["output_json"]) if row["output_json"] else {}
        return {
            "result_metadata": self.result_metadata(task.id, task.user_id),
            "task": {**task.to_dict(), "result_metadata": self.result_metadata(task.id, task.user_id)},
            "decision": {**self._decision_row(decision), "result_metadata": self.result_metadata(task.id, task.user_id)} if decision else None,
            "evidence": evidence_rows,
            "trace": trace_rows,
            "tool_calls": [dict(row) for row in tool_calls],
            "llm_usage": {
                "records": int(usage["records"] or 0),
                "request_count": int(usage["request_count"] or 0),
                "prompt_tokens": int(usage["prompt_tokens"] or 0),
                "completion_tokens": int(usage["completion_tokens"] or 0),
                "total_tokens": int(usage["total_tokens"] or 0),
                "cost_usd": round(float(usage["cost_usd"] or 0), 8),
            } if usage else {
                "records": 0,
                "request_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
            },
            "debate": debate,
            "approvals": [dict(row) for row in approvals],
            "retrospectives": [
                {
                    **{
                        key: value
                        for key, value in dict(row).items()
                        if key != "outcome_json"
                    },
                    "outcome": json.loads(row["outcome_json"] or "{}"),
                }
                for row in retrospectives
            ],
            "events": [
                {"event_type": row["event_type"], "payload": json.loads(row["payload_json"]), "created_at": row["created_at"]}
                for row in events
            ],
        }

    @staticmethod
    def _decision_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["rationale"] = json.loads(value.pop("rationale_json"))
        value["synthesis"] = value["rationale"].get("synthesis", {})
        value["invalidation"] = json.loads(value.pop("invalidation_json"))
        return value

    def append_event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.execute(
            "INSERT INTO task_events(task_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (task_id, event_type, json.dumps(payload, ensure_ascii=False), now_iso()),
        )

    def result_metadata(self, task_id, user_id):
        from .result_metadata import legacy_metadata
        row = self.fetchone("SELECT payload_json FROM task_result_metadata WHERE task_id=? AND user_id=?", (task_id, user_id))
        return json.loads(row["payload_json"]) if row else legacy_metadata()

    def save_result_metadata(self, task_id, user_id, metadata):
        from .result_metadata import ResultMetadata
        payload = ResultMetadata.model_validate(metadata).model_dump()
        self.execute(
            """INSERT INTO task_result_metadata VALUES (?, ?, ?)
               ON CONFLICT(task_id) DO UPDATE SET payload_json=excluded.payload_json""",
            (task_id, user_id, json.dumps(payload, ensure_ascii=False)),
        )
        self.append_event(task_id, "RESULT_METADATA", payload)

    def task_events(self, task_id: str) -> list[dict[str, Any]]:
        rows = self.fetchall(
            "SELECT event_type, payload_json, created_at FROM task_events WHERE task_id=? ORDER BY id",
            (task_id,),
        )
        return [
            {"event_type": row["event_type"], "payload": json.loads(row["payload_json"]), "created_at": row["created_at"]}
            for row in rows
        ]

    def audit(
        self,
        task_id: str | None,
        event_type: str,
        payload: dict[str, Any],
        user_id: str | None = None,
    ) -> None:
        if user_id is None and task_id:
            task_row = self.fetchone(
                "SELECT user_id FROM research_tasks WHERE id=?",
                (task_id,),
            )
            user_id = task_row["user_id"] if task_row else None
        user_id = str(user_id or payload.get("user_id") or "default")
        self.execute(
            "INSERT INTO audit_log(task_id, user_id, event_type, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                task_id,
                user_id,
                event_type,
                json.dumps(payload, ensure_ascii=False),
                now_iso(),
            ),
        )

    def approve(self, task_id: str, action: str, notes: str, user_id: str = "default") -> dict[str, Any]:
        task = self.get_task(task_id)
        if not task:
            raise KeyError(task_id)
        if task.user_id != user_id:
            raise KeyError(task_id)
        allowed_actions = {
            "APPROVE",
            "REJECT",
            "NO_ACTION",
            "REQUEST_MORE_RESEARCH",
            "MARK_AS_WATCH",
        }
        if action not in allowed_actions:
            raise ValueError(f"unsupported approval action: {action}")
        if task.status not in {TaskStatus.WAITING_APPROVAL, TaskStatus.NO_ACTION, TaskStatus.BLOCKED}:
            raise ValueError(f"task is not approvable from {task.status}")
        decision = self.fetchone(
            "SELECT status FROM decisions WHERE task_id=?", (task_id,)
        )
        if decision and decision["status"] in {"BLOCKED", "NO_ACTION"} and action == "APPROVE":
            raise ValueError(f"{decision['status'].lower()} decision cannot be approved")
        if action == "APPROVE":
            next_status = TaskStatus.APPROVED
        elif action in {"REQUEST_MORE_RESEARCH", "MARK_AS_WATCH", "NO_ACTION"}:
            next_status = TaskStatus.NO_ACTION
        else:
            next_status = TaskStatus.REJECTED
        task.status = next_status
        task.finished_at = now_iso()
        self.update_task(task)
        approval_id = f"approval_{task_id}_{len(self.task_events(task_id))}"
        self.execute(
            """INSERT INTO approvals
               (id, task_id, user_id, action, created_at, rule_snapshot_id, data_snapshot_id, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (approval_id, task_id, user_id, action, now_iso(), task.rule_snapshot_id, task.data_snapshot_id, notes),
        )
        self.audit(
            task_id,
            "APPROVAL_RECORDED",
            {"action": action, "notes": notes, "user_id": user_id},
            user_id=user_id,
        )
        return {"approval_id": approval_id, "task": task.to_dict()}


def _watchlist_row(row: Any) -> dict[str, Any]:
    value = dict(row)
    value["symbols"] = json.loads(value.pop("symbols_json") or "[]")
    return value


def _usage_int(usage: dict[str, Any], key: str) -> int:
    value = usage.get(key, 0)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
