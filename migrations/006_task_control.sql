ALTER TABLE research_tasks ADD COLUMN pause_requested INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_research_tasks_pause_requested
  ON research_tasks(pause_requested);
