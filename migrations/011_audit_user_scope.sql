ALTER TABLE audit_log ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';

CREATE INDEX IF NOT EXISTS idx_audit_user_created_at
  ON audit_log(user_id, created_at DESC);
