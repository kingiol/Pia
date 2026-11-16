import unittest

from pia_runtime.postgres import _translate_sql


class PostgresContractTest(unittest.TestCase):
    def test_ignore_insert_uses_postgres_conflict_clause(self):
        translated = _translate_sql(
            "INSERT OR IGNORE INTO users(id, created_at) VALUES (?, ?)"
        )
        self.assertIn("INSERT INTO users", translated)
        self.assertIn("ON CONFLICT DO NOTHING", translated)
        self.assertIn("%s", translated)
        self.assertNotIn("OR IGNORE", translated)

    def test_replace_insert_updates_non_key_columns(self):
        translated = _translate_sql(
            "INSERT OR REPLACE INTO market_snapshots "
            "(id, as_of, quality) VALUES (?, ?, ?)"
        )
        self.assertIn("ON CONFLICT (id) DO UPDATE SET", translated)
        self.assertIn("as_of=EXCLUDED.as_of", translated)
        self.assertIn("quality=EXCLUDED.quality", translated)
        self.assertNotIn("id=EXCLUDED.id", translated)


if __name__ == "__main__":
    unittest.main()
