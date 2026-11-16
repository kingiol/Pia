CREATE TABLE IF NOT EXISTS task_retrospectives (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  action_taken TEXT NOT NULL,
  outcome_json TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  observed_at TEXT NOT NULL,
  rule_snapshot_id TEXT,
  data_snapshot_id TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_retrospectives_task
  ON task_retrospectives(task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_task_retrospectives_user
  ON task_retrospectives(user_id, created_at DESC);
