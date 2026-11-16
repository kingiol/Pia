ALTER TABLE memory_candidates ADD COLUMN reviewed_at TEXT;
ALTER TABLE memory_candidates ADD COLUMN reviewed_by TEXT;
ALTER TABLE memory_candidates ADD COLUMN review_action TEXT;
ALTER TABLE memory_candidates ADD COLUMN review_notes TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_memory_candidates_review
  ON memory_candidates(user_id, status, reviewed_at DESC);
