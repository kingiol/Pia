CREATE TABLE IF NOT EXISTS llm_budget_locks (id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS llm_attempts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    route_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    model TEXT NOT NULL,
    day_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    cost_status TEXT NOT NULL,
    usage_json TEXT,
    reason_code TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_budget_reservations (
    attempt_id TEXT PRIMARY KEY REFERENCES llm_attempts(id),
    user_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    day_utc TEXT NOT NULL,
    reserved_usd TEXT NOT NULL,
    accounted_usd TEXT NOT NULL,
    price_json TEXT NOT NULL,
    settled INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_llm_budget_user_day ON llm_budget_reservations(user_id, day_utc);
