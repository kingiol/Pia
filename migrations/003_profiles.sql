CREATE TABLE IF NOT EXISTS investor_profiles (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE(user_id, version)
);

CREATE INDEX IF NOT EXISTS idx_investor_profiles_user_version
  ON investor_profiles(user_id, version DESC);

CREATE TABLE IF NOT EXISTS task_leases (
  task_id TEXT PRIMARY KEY,
  lease_id TEXT NOT NULL UNIQUE,
  worker_id TEXT NOT NULL,
  acquired_at TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_leases_expiry
  ON task_leases(expires_at);
