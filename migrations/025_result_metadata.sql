CREATE TABLE IF NOT EXISTS task_result_metadata (
    task_id TEXT PRIMARY KEY REFERENCES research_tasks(id),
    user_id TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
