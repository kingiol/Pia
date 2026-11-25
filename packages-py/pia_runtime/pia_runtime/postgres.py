from __future__ import annotations

import re
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .db import Database
from .models import now_iso


class PostgresDatabase(Database):
    """PostgreSQL transactional repository with the same surface as Database."""

    @staticmethod
    def _notification_task_json(key: str) -> str:
        return f"(CAST(t.target_json AS jsonb)->>'{key}')"

    def __init__(self, dsn: str, migrations_dir: Path) -> None:
        try:
            import psycopg  # type: ignore
            from psycopg.rows import dict_row  # type: ignore
        except ImportError as error:
            raise RuntimeError(
                "CAPABILITY_DISABLED: install psycopg[binary] for PostgreSQL cloud mode"
            ) from error

        self.path = Path("<postgres>")
        self.migrations_dir = migrations_dir
        self.lock = threading.RLock()
        self._transaction_depth = 0
        self.connection = _ConnectionProxy(psycopg.connect(dsn, row_factory=dict_row))
        try:
            self.apply_migrations()
        except BaseException:
            self.connection.close()
            raise

    def apply_migrations(self) -> None:
        # API and worker may start together against a new database.
        with self.lock:
            self.connection.execute(
                "SELECT pg_advisory_lock(hashtext('pia_schema_migrations'), hashtext(current_schema()))"
            )
            self.connection.commit()
            try:
                self._apply_migrations()
            finally:
                self.connection.rollback()
                self.connection.execute(
                    "SELECT pg_advisory_unlock(hashtext('pia_schema_migrations'), hashtext(current_schema()))"
                )
                self.connection.commit()

    def _apply_migrations(self) -> None:
        postgres_dir = self.migrations_dir / "postgres"
        with self.lock:
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version TEXT PRIMARY KEY,
                   applied_at TEXT NOT NULL
                )"""
            )
            self.connection.commit()
            for migration in sorted(postgres_dir.glob("*.sql")):
                applied = self.connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=%s",
                    (migration.name,),
                ).fetchone()
                if applied:
                    continue
                self.connection.execute(migration.read_text())
                self.connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (migration.name, now_iso()),
                )
                self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        translated = _translate_sql(query)
        with self.lock:
            try:
                cursor = self.connection.execute(translated, params)
                if not self._transaction_depth:
                    self.connection.commit()
                return cursor
            except Exception:
                self.connection.rollback()
                raise

    @contextmanager
    def transaction(self):
        with self.lock:
            outermost = self._transaction_depth == 0
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

    def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        with self.lock:
            return self.connection.execute(_translate_sql(query), params).fetchone()

    def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[Any]:
        with self.lock:
            return list(self.connection.execute(_translate_sql(query), params).fetchall())

    def backup_to(self, destination: Path) -> None:
        raise RuntimeError(
            "CAPABILITY_DISABLED: use pg_dump/pg_restore for PostgreSQL backups"
        )


class _ConnectionProxy:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        return self._connection.execute(_translate_sql(query), params)

    def executescript(self, script: str) -> Any:
        return self._connection.execute(script)

    def cursor(self, **kwargs: Any) -> Any:
        return self._connection.cursor(**kwargs)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def _translate_sql(query: str) -> str:
    """Translate the small SQLite SQL subset used by the shared repository."""
    translated = query
    replace_match = re.search(
        r"INSERT\s+OR\s+REPLACE\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\s*"
        r"\(([^)]+)\)\s*VALUES\s*(\([^;]+\))",
        translated,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if replace_match:
        table = replace_match.group(1)
        columns = [
            item.strip()
            for item in replace_match.group(2).split(",")
        ]
        values = replace_match.group(3)
        updates = [
            f"{column}=EXCLUDED.{column}"
            for column in columns
            if column not in {"id", "task_id"}
        ]
        conflict_target = {
            "market_snapshots": "id",
            "portfolio_snapshots": "id",
            "task_leases": "task_id",
            "agent_runs": "id",
            "evidence": "id",
            "decisions": "task_id",
        }.get(table)
        suffix = " ON CONFLICT DO NOTHING"
        if updates and conflict_target:
            suffix = (
                f" ON CONFLICT ({conflict_target}) DO UPDATE SET "
                + ", ".join(updates)
            )
        translated = (
            translated[:replace_match.start()]
            + f"INSERT INTO {table} ({', '.join(columns)}) VALUES {values}{suffix}"
            + translated[replace_match.end():]
        )
    ignore_match = re.search(
        r"INSERT\s+OR\s+IGNORE\s+INTO",
        translated,
        flags=re.IGNORECASE,
    )
    if ignore_match:
        translated = re.sub(
            r"INSERT\s+OR\s+IGNORE\s+INTO",
            "INSERT INTO",
            translated,
            count=1,
            flags=re.IGNORECASE,
        )
        stripped = translated.rstrip()
        semicolon = ";" if stripped.endswith(";") else ""
        if semicolon:
            stripped = stripped[:-1].rstrip()
        translated = f"{stripped} ON CONFLICT DO NOTHING{semicolon}"
    return translated.replace("?", "%s")
