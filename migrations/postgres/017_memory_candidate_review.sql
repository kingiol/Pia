ALTER TABLE memory_candidates ADD COLUMN IF NOT EXISTS reviewed_at TEXT;
ALTER TABLE memory_candidates ADD COLUMN IF NOT EXISTS reviewed_by TEXT;
ALTER TABLE memory_candidates ADD COLUMN IF NOT EXISTS review_action TEXT;
ALTER TABLE memory_candidates ADD COLUMN IF NOT EXISTS review_notes TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_memory_candidates_review
  ON memory_candidates(user_id, status, reviewed_at DESC);
