CREATE TABLE IF NOT EXISTS memory_candidate_feedback (
  id TEXT PRIMARY KEY,
  memory_candidate_id TEXT NOT NULL,
  memory_candidate_usage_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  rating TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(memory_candidate_usage_id)
);

CREATE INDEX IF NOT EXISTS idx_memory_candidate_feedback_candidate
  ON memory_candidate_feedback(user_id, memory_candidate_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_candidate_feedback_task
  ON memory_candidate_feedback(user_id, task_id, updated_at DESC);
