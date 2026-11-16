CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE,
  priority INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  expires_at TEXT,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_deliveries (
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  task_id TEXT,
  attempt INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL,
  next_retry_at TEXT,
  last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON events(occurred_at DESC);
