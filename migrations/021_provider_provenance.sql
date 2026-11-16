CREATE TABLE IF NOT EXISTS provider_attempts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    task_id TEXT REFERENCES research_tasks(id),
    call_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(call_id, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_provider_attempts_task ON provider_attempts(user_id, task_id);
CREATE TABLE IF NOT EXISTS provider_last_good (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    capability TEXT NOT NULL,
    subject TEXT NOT NULL,
    as_of TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_provider_last_good_lookup
ON provider_last_good(user_id, capability, subject, as_of);
