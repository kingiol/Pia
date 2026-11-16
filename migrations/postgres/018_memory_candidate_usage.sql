CREATE TABLE IF NOT EXISTS memory_candidate_usages (
  id TEXT PRIMARY KEY,
  memory_candidate_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  usage_type TEXT NOT NULL,
  used_at TEXT NOT NULL,
  UNIQUE(memory_candidate_id, task_id, usage_type)
);

CREATE INDEX IF NOT EXISTS idx_memory_candidate_usages_candidate
  ON memory_candidate_usages(user_id, memory_candidate_id, used_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_candidate_usages_task
  ON memory_candidate_usages(user_id, task_id, used_at DESC);
