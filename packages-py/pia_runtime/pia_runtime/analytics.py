from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


ANALYTICAL_KEYS = {
    "raw_provider_payloads": ("id",),
    "normalized_daily_bars": ("snapshot_id", "symbol", "trade_date"),
    "analytical_snapshots": ("snapshot_id",),
    "normalized_universe": ("snapshot_id", "symbol"),
    "normalized_fundamentals": ("snapshot_id", "symbol"),
    "normalized_research_sources": ("snapshot_id", "symbol", "source_type", "external_id"),
    "normalized_trading_calendar": ("snapshot_id", "trade_date"),
}


class AnalyticsStore:
    """DuckDB-backed analytical storage for raw, normalized and snapshot data."""

    def __init__(self, path: Path) -> None:
        try:
            import duckdb  # type: ignore
        except ImportError as error:
            raise RuntimeError(
                "DuckDB is required for Pia analytical storage. Install the project dependencies first."
            ) from error
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._duckdb = duckdb
        self._lock = threading.RLock()
        self._apply_schema()

    def _connect(self) -> Any:
        return self._duckdb.connect(str(self.path))

    @contextmanager
    def _connection(self):
        with self._lock:
            connection = self._connect()
            try:
                yield connection
            finally:
                connection.close()

    def _save_rows(self, table: str, columns: tuple[str, ...], values: list) -> int:
        keys = ANALYTICAL_KEYS[table]
        updates = ", ".join(f"{name}=excluded.{name}" for name in columns if name not in keys)
        query = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)}) "
            f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET {updates}"
        )
        if values:
            with self._connection() as connection:
                connection.executemany(query, values)
        return len(values)

    def _apply_schema(self) -> None:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS raw_provider_payloads (
                        id VARCHAR PRIMARY KEY,
                        provider_id VARCHAR NOT NULL,
                        provider_version VARCHAR NOT NULL,
                        adapter_version VARCHAR NOT NULL,
                        as_of DATE,
                        observed_at TIMESTAMP,
                        payload_json VARCHAR NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS normalized_daily_bars (
                        snapshot_id VARCHAR NOT NULL,
                        symbol VARCHAR NOT NULL,
                        trade_date DATE,
                        open DOUBLE,
                        high DOUBLE,
                        low DOUBLE,
                        close DOUBLE,
                        volume DOUBLE,
                        amount DOUBLE,
                        provider_id VARCHAR NOT NULL,
                        provider_version VARCHAR NOT NULL,
                        adapter_version VARCHAR NOT NULL,
                        as_of DATE,
                        observed_at TIMESTAMP,
                        quality VARCHAR NOT NULL,
                        normalization_warnings_json VARCHAR NOT NULL,
                        PRIMARY KEY (snapshot_id, symbol, trade_date)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS analytical_snapshots (
                        snapshot_id VARCHAR PRIMARY KEY,
                        kind VARCHAR NOT NULL,
                        as_of DATE,
                        observed_at TIMESTAMP,
                        source VARCHAR NOT NULL,
                        quality VARCHAR NOT NULL,
                        payload_json VARCHAR NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS normalized_universe (
                        snapshot_id VARCHAR NOT NULL,
                        symbol VARCHAR NOT NULL,
                        name VARCHAR,
                        asset_type VARCHAR,
                        board VARCHAR,
                        exchange VARCHAR,
                        listed_at DATE,
                        is_st BOOLEAN,
                        is_delisting BOOLEAN,
                        suspended BOOLEAN,
                        active BOOLEAN,
                        listed_days INTEGER,
                        provider_id VARCHAR NOT NULL,
                        provider_version VARCHAR NOT NULL,
                        adapter_version VARCHAR NOT NULL,
                        as_of DATE,
                        observed_at TIMESTAMP,
                        quality VARCHAR NOT NULL,
                        PRIMARY KEY (snapshot_id, symbol)
                    )
                    """
                )
                connection.execute(
                    "ALTER TABLE normalized_universe ADD COLUMN IF NOT EXISTS is_delisting BOOLEAN DEFAULT FALSE"
                )
                connection.execute(
                    "ALTER TABLE normalized_universe ADD COLUMN IF NOT EXISTS exchange VARCHAR"
                )
                connection.execute(
                    "ALTER TABLE normalized_universe ADD COLUMN IF NOT EXISTS listed_at DATE"
                )
                connection.execute(
                    "ALTER TABLE normalized_universe ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE"
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS normalized_fundamentals (
                        snapshot_id VARCHAR NOT NULL,
                        symbol VARCHAR NOT NULL,
                        as_of DATE,
                        metrics_json VARCHAR NOT NULL,
                        provider_id VARCHAR NOT NULL,
                        provider_version VARCHAR NOT NULL,
                        adapter_version VARCHAR NOT NULL,
                        observed_at TIMESTAMP,
                        quality VARCHAR NOT NULL,
                        PRIMARY KEY (snapshot_id, symbol)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS normalized_research_sources (
                        snapshot_id VARCHAR NOT NULL,
                        symbol VARCHAR NOT NULL,
                        source_type VARCHAR NOT NULL,
                        external_id VARCHAR NOT NULL,
                        title VARCHAR NOT NULL,
                        published_at TIMESTAMP,
                        source_uri VARCHAR,
                        excerpt VARCHAR,
                        content_hash VARCHAR NOT NULL,
                        provider_id VARCHAR NOT NULL,
                        provider_version VARCHAR NOT NULL,
                        adapter_version VARCHAR NOT NULL,
                        as_of DATE,
                        observed_at TIMESTAMP,
                        quality VARCHAR NOT NULL,
                        PRIMARY KEY (snapshot_id, symbol, source_type, external_id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS normalized_trading_calendar (
                        snapshot_id VARCHAR NOT NULL,
                        trade_date DATE NOT NULL,
                        is_open BOOLEAN NOT NULL,
                        provider_id VARCHAR NOT NULL,
                        provider_version VARCHAR NOT NULL,
                        adapter_version VARCHAR NOT NULL,
                        as_of DATE,
                        observed_at TIMESTAMP,
                        quality VARCHAR NOT NULL,
                        PRIMARY KEY (snapshot_id, trade_date)
                    )
                    """
                )
            finally:
                connection.close()

    def save_raw_payload(
        self,
        *,
        payload_id: str,
        provider_id: str,
        provider_version: str,
        adapter_version: str,
        as_of: str | None,
        observed_at: str | None,
        payload: dict[str, Any],
    ) -> None:
        self._save_rows(
            "raw_provider_payloads",
            ("id", "provider_id", "provider_version", "adapter_version", "as_of", "observed_at", "payload_json"),
            [[
                payload_id, provider_id, provider_version, adapter_version,
                as_of, observed_at, json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ]],
        )

    def save_daily_bars(self, rows: Iterable[dict[str, Any]]) -> int:
        values = [
            [
                row["snapshot_id"],
                row["symbol"],
                row.get("trade_date"),
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row.get("volume"),
                row.get("amount"),
                row["provider_id"],
                row.get("provider_version", "unknown"),
                row.get("adapter_version", "unknown"),
                row.get("as_of"),
                row.get("observed_at"),
                row.get("quality", "unavailable"),
                json.dumps(row.get("normalization_warnings", []), ensure_ascii=False),
            ]
            for row in rows
        ]
        return self._save_rows(
            "normalized_daily_bars",
            ("snapshot_id", "symbol", "trade_date", "open", "high", "low", "close", "volume", "amount",
             "provider_id", "provider_version", "adapter_version", "as_of", "observed_at",
             "quality", "normalization_warnings_json"),
            values,
        )

    def save_snapshot(
        self,
        *,
        snapshot_id: str,
        kind: str,
        as_of: str | None,
        observed_at: str | None,
        source: str,
        quality: str,
        payload: dict[str, Any],
    ) -> None:
        self._save_rows(
            "analytical_snapshots",
            ("snapshot_id", "kind", "as_of", "observed_at", "source", "quality", "payload_json"),
            [[
                snapshot_id, kind, as_of, observed_at, source, quality,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ]],
        )

    def save_universe(self, rows: Iterable[dict[str, Any]]) -> int:
        values = [
            [
                row["snapshot_id"],
                row["symbol"],
                row.get("name"),
                row.get("asset_type", "stock"),
                row.get("board"),
                row.get("exchange"),
                row.get("listed_at"),
                bool(row.get("is_st", False)),
                bool(row.get("is_delisting", False)),
                bool(row.get("suspended", False)),
                bool(row.get("active", True)),
                row.get("listed_days"),
                row["provider_id"],
                row.get("provider_version", "unknown"),
                row.get("adapter_version", "unknown"),
                row.get("as_of"),
                row.get("observed_at"),
                row.get("quality", "unavailable"),
            ]
            for row in rows
        ]
        return self._save_rows(
            "normalized_universe",
            ("snapshot_id", "symbol", "name", "asset_type", "board", "exchange", "listed_at",
             "is_st", "is_delisting", "suspended", "active", "listed_days",
             "provider_id", "provider_version", "adapter_version", "as_of", "observed_at", "quality"),
            values,
        )

    def save_fundamentals(self, rows: Iterable[dict[str, Any]]) -> int:
        values = [
            [
                row["snapshot_id"],
                row["symbol"],
                row.get("as_of"),
                json.dumps(row.get("metrics", {}), ensure_ascii=False, sort_keys=True),
                row["provider_id"],
                row.get("provider_version", "unknown"),
                row.get("adapter_version", "unknown"),
                row.get("observed_at"),
                row.get("quality", "unavailable"),
            ]
            for row in rows
        ]
        return self._save_rows(
            "normalized_fundamentals",
            ("snapshot_id", "symbol", "as_of", "metrics_json", "provider_id",
             "provider_version", "adapter_version", "observed_at", "quality"),
            values,
        )

    def save_research_sources(self, rows: Iterable[dict[str, Any]]) -> int:
        values = [
            [
                row["snapshot_id"],
                row["symbol"],
                row["source_type"],
                row["external_id"],
                row["title"],
                row.get("published_at"),
                row.get("source_uri"),
                row.get("excerpt"),
                row["content_hash"],
                row["provider_id"],
                row.get("provider_version", "unknown"),
                row.get("adapter_version", "unknown"),
                row.get("as_of"),
                row.get("observed_at"),
                row.get("quality", "unavailable"),
            ]
            for row in rows
        ]
        return self._save_rows(
            "normalized_research_sources",
            ("snapshot_id", "symbol", "source_type", "external_id", "title", "published_at",
             "source_uri", "excerpt", "content_hash", "provider_id", "provider_version",
             "adapter_version", "as_of", "observed_at", "quality"),
            values,
        )

    def save_trading_calendar(self, rows: Iterable[dict[str, Any]]) -> int:
        values = [
            [
                row["snapshot_id"],
                row["trade_date"],
                bool(row.get("is_open", False)),
                row["provider_id"],
                row.get("provider_version", "unknown"),
                row.get("adapter_version", "unknown"),
                row.get("as_of"),
                row.get("observed_at"),
                row.get("quality", "unavailable"),
            ]
            for row in rows
        ]
        return self._save_rows(
            "normalized_trading_calendar",
            ("snapshot_id", "trade_date", "is_open", "provider_id", "provider_version",
             "adapter_version", "as_of", "observed_at", "quality"),
            values,
        )

    def snapshot_bundle(
        self,
        snapshot_id: str,
        *,
        raw_limit: int = 20,
    ) -> dict[str, Any] | None:
        """Return an analytical snapshot and the raw payloads for its point in time."""
        bounded_limit = max(1, min(int(raw_limit), 100))
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT snapshot_id, kind, CAST(as_of AS VARCHAR), CAST(observed_at AS VARCHAR),
                       source, quality, payload_json
                FROM analytical_snapshots
                WHERE snapshot_id=?
                """,
                [snapshot_id],
            ).fetchone()
            if not row:
                return None
            snapshot = {
                "snapshot_id": row[0],
                "kind": row[1],
                "as_of": row[2],
                "observed_at": row[3],
                "source": row[4],
                "quality": row[5],
                "payload": json.loads(row[6]),
            }
            raw_rows = connection.execute(
                """
                SELECT id, provider_id, provider_version, adapter_version,
                       CAST(as_of AS VARCHAR), CAST(observed_at AS VARCHAR), payload_json
                FROM raw_provider_payloads
                WHERE as_of=CAST(? AS DATE) AND provider_id=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                [row[2], row[4], bounded_limit],
            ).fetchall()
        return {
            "snapshot": snapshot,
            "raw_payloads": [
                {
                    "id": raw[0],
                    "provider_id": raw[1],
                    "provider_version": raw[2],
                    "adapter_version": raw[3],
                    "as_of": raw[4],
                    "observed_at": raw[5],
                    "payload": json.loads(raw[6]),
                }
                for raw in raw_rows
            ],
        }

    def count(self, table: str) -> int:
        if table not in ANALYTICAL_KEYS:
            raise ValueError(f"unsupported analytics table: {table}")
        with self._connection() as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def checkpoint(self) -> None:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("CHECKPOINT")
            finally:
                connection.close()

    def close(self) -> None:
        return
