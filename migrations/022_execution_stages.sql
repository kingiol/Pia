CREATE TABLE IF NOT EXISTS task_stage_runs (
    user_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES research_tasks(id),
    stage_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    policy_version TEXT NOT NULL,
    required INTEGER NOT NULL,
    allocated_ms INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    outcome TEXT NOT NULL,
    reason_code TEXT,
    artifact_ids TEXT NOT NULL,
    PRIMARY KEY(task_id, stage_id, attempt)
);
ALTER TABLE evidence ADD COLUMN provenance_json TEXT NOT NULL DEFAULT '{}';
