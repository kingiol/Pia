CREATE TABLE IF NOT EXISTS holdings_review_attempts (
    task_id TEXT PRIMARY KEY REFERENCES research_tasks(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    as_of TEXT NOT NULL,
    portfolio_snapshot_id TEXT REFERENCES portfolio_snapshots(id),
    cash REAL,
    confirmed_at TEXT
);

CREATE INDEX IF NOT EXISTS holdings_review_user_session_idx
    ON holdings_review_attempts(user_id, as_of);
