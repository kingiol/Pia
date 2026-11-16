CREATE TABLE IF NOT EXISTS screening_strategy_versions (
    strategy_id TEXT NOT NULL,
    version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    PRIMARY KEY(strategy_id, version)
);
CREATE TABLE IF NOT EXISTS candidate_scans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    version TEXT NOT NULL,
    strategy_hash TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    as_of TEXT NOT NULL,
    input_json TEXT NOT NULL,
    output_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_candidate_scans_user ON candidate_scans(user_id, created_at);
