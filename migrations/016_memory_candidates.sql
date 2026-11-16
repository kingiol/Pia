CREATE TABLE IF NOT EXISTS memory_candidates (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  candidate_key TEXT NOT NULL,
  source_type TEXT NOT NULL,
  status TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  sample_size INTEGER NOT NULL,
  comparable_outcome_count INTEGER NOT NULL,
  average_return_pct REAL,
  source_task_ids_json TEXT NOT NULL,
  source_rule_snapshot_ids_json TEXT NOT NULL,
  as_of TEXT,
  observed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(user_id, candidate_key)
);

CREATE INDEX IF NOT EXISTS idx_memory_candidates_user
  ON memory_candidates(user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_candidates_status
  ON memory_candidates(user_id, status, updated_at DESC);
