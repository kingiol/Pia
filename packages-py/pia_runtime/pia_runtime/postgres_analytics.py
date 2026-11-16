from __future__ import annotations

from contextlib import contextmanager

from .analytics import AnalyticsStore
from .postgres import PostgresDatabase


class PostgresAnalyticsStore(AnalyticsStore):
    """Analytical data on the same connection and transactions as Cloud records."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db

    @contextmanager
    def _connection(self):
        from psycopg.rows import tuple_row

        with self.db.transaction():
            with self.db.connection.cursor(row_factory=tuple_row) as cursor:
                yield _AnalyticsCursor(cursor)

    def checkpoint(self) -> None:
        # PostgreSQL durability and backup are managed by the database server.
        return


class _AnalyticsCursor:
    def __init__(self, cursor) -> None:
        self.cursor = cursor

    def execute(self, query, params=()):
        self.cursor.execute(query.replace("?", "%s"), params)
        return self.cursor

    def executemany(self, query, params):
        self.cursor.executemany(query.replace("?", "%s"), params)
