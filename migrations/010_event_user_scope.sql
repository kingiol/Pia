ALTER TABLE events ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';

CREATE INDEX IF NOT EXISTS idx_events_user_occurred_at
  ON events(user_id, occurred_at DESC);
