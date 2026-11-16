import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from pia_runtime.analytics import ANALYTICAL_KEYS, AnalyticsStore
from pia_runtime.config import ROOT, Settings
from pia_runtime.models import new_id
from pia_runtime.postgres import PostgresDatabase
from pia_runtime.postgres_analytics import PostgresAnalyticsStore
from pia_runtime.runtime import PiaRuntime


def seed_analytics(store):
    common = {
        "snapshot_id": "test-market", "symbol": "600000.SH",
        "provider_id": "fixture", "provider_version": "1", "adapter_version": "1",
        "as_of": "2026-11-05", "observed_at": "2026-11-05T16:00:00+08:00",
        "quality": "verified",
    }
    store.save_raw_payload(payload_id="raw-test", payload={"marker": "original"},
                           **{key: common[key] for key in (
                               "provider_id", "provider_version", "adapter_version", "as_of", "observed_at",
                           )})
    store.save_snapshot(
        snapshot_id=common["snapshot_id"], kind="market", as_of=common["as_of"],
        observed_at=common["observed_at"], source="fixture", quality="verified",
        payload={"marker": "snapshot"},
    )
    store.save_daily_bars([{**common, "trade_date": common["as_of"], "close": 10.5}])
    store.save_universe([{**common, "name": "Test", "listed_at": "2000-01-01", "is_st": False}])
    store.save_fundamentals([{**common, "metrics": {"pe": 12.3}}])
    store.save_research_sources([{
        **common, "source_type": "filing", "external_id": "filing-1", "title": "Test filing",
        "content_hash": "hash", "published_at": common["observed_at"],
    }])
    store.save_trading_calendar([{**common, "trade_date": common["as_of"], "is_open": True}])
    return common


class LocalAnalyticsContractTest(unittest.TestCase):
    def test_shared_upserts_preserve_local_analytics(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "local.duckdb")
            common = seed_analytics(store)
            seed_analytics(store)
            store.save_daily_bars([{**common, "trade_date": common["as_of"], "close": 20}])
            for table in ANALYTICAL_KEYS:
                self.assertEqual(store.count(table), 1, table)
            self.assertEqual(store.snapshot_bundle("test-market")["raw_payloads"][0]["payload"],
                             {"marker": "original"})


@unittest.skipUnless(os.getenv("PIA_TEST_POSTGRES_DSN"), "requires isolated PostgreSQL integration database")
class PostgresAnalyticsTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo

        self.schema = new_id("analytics_test")
        self.admin = psycopg.connect(os.environ["PIA_TEST_POSTGRES_DSN"], autocommit=True)
        self.admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.admin.close)
        self.addCleanup(lambda: self.admin.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)),
        ))
        self.dsn = make_conninfo(os.environ["PIA_TEST_POSTGRES_DSN"], options=f"-csearch_path={self.schema}")
        self.db = PostgresDatabase(self.dsn, ROOT / "migrations")
        self.addCleanup(self.db.close)
        self.store = PostgresAnalyticsStore(self.db)

    def test_simultaneous_startup_serializes_schema_migrations(self):
        from psycopg import sql
        from psycopg.conninfo import make_conninfo

        schema = self.schema + "_fresh"
        self.admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        self.addCleanup(lambda: self.admin.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)),
        ))
        dsn = make_conninfo(self.dsn, options=f"-csearch_path={schema}")
        barrier = threading.Barrier(2)
        errors = []

        def connect():
            barrier.wait()
            try:
                database = PostgresDatabase(dsn, ROOT / "migrations")
                self.assertEqual(PostgresAnalyticsStore(database).count("normalized_daily_bars"), 0)
                database.close()
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=connect) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(15)
            self.assertFalse(thread.is_alive(), "Migration lock did not release")
        self.assertEqual(errors, [])

    def test_all_tables_upsert_and_independent_connections_read_the_same_data(self):
        common = seed_analytics(self.store)
        seed_analytics(self.store)
        self.store.save_daily_bars([{**common, "trade_date": common["as_of"], "close": 20}])
        self.store.save_universe([{**common, "name": "Updated", "is_st": True}])
        other = PostgresDatabase(self.dsn, ROOT / "migrations")
        self.addCleanup(other.close)
        for table in ANALYTICAL_KEYS:
            self.assertEqual(PostgresAnalyticsStore(other).count(table), 1, table)
        self.assertEqual(other.fetchone("SELECT close FROM normalized_daily_bars")["close"], 20)
        self.assertTrue(other.fetchone("SELECT is_st FROM normalized_universe")["is_st"])
        self.assertEqual(PostgresAnalyticsStore(other).snapshot_bundle("test-market")["snapshot"]["payload"],
                         {"marker": "snapshot"})
        self.assertIsNone(self.store.snapshot_bundle("missing"))
        with self.assertRaises(ValueError):
            self.store.count("users")

    def test_business_and_analytics_share_rollback(self):
        with self.assertRaisesRegex(RuntimeError, "abort"):
            with self.db.transaction():
                self.db.user_seed("rolled-back")
                seed_analytics(self.store)
                raise RuntimeError("abort")
        self.assertIsNone(self.db.fetchone("SELECT id FROM users WHERE id=?", ("rolled-back",)))
        for table in ANALYTICAL_KEYS:
            self.assertEqual(self.store.count(table), 0)

    def test_invalid_batch_rolls_back_successful_rows_and_connection_recovers(self):
        import psycopg

        common = {"snapshot_id": "batch", "provider_id": "fixture", "trade_date": "2026-11-05"}
        with self.assertRaises(psycopg.Error):
            self.store.save_daily_bars([
                {**common, "symbol": "600000.SH", "close": 10},
                {**common, "symbol": "600001.SH", "close": "invalid"},
            ])
        self.assertEqual(self.store.count("normalized_daily_bars"), 0)
        self.store.save_daily_bars([{**common, "symbol": "600000.SH", "close": 10}])
        self.assertEqual(self.store.count("normalized_daily_bars"), 1)

    def test_cloud_runtime_never_opens_file_databases(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("sqlite3.connect", side_effect=AssertionError("SQLite opened")),
            patch("duckdb.connect", side_effect=AssertionError("DuckDB opened")),
        ):
            root = Path(directory)
            runtime = PiaRuntime(Settings(
                mode="cloud", postgres_dsn=self.dsn, db_path=root / "unused.sqlite3",
                analytics_db_path=root / "unused.duckdb", autostart_tasks=False,
            ))
            try:
                task = runtime.create_task("MarketClose", {"as_of": "2026-11-05"})
                runtime.run_task(task.id)
                detail = runtime.wait_for_task(task.id)
                self.assertEqual(detail["task"]["status"], "BLOCKED")
                self.assertTrue(runtime.task_data(task.id)["bundles"])
                self.assertEqual(runtime.health()["analytics_database"], "postgres")
                self.assertEqual(list(root.iterdir()), [])
            finally:
                runtime.close()
