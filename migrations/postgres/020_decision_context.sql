CREATE TABLE IF NOT EXISTS task_input_bindings (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    task_id TEXT NOT NULL UNIQUE REFERENCES research_tasks(id),
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decision_context_packs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    task_id TEXT NOT NULL UNIQUE REFERENCES research_tasks(id),
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE OR REPLACE FUNCTION reject_context_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'context inputs are immutable';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER task_input_bindings_immutable_update
BEFORE UPDATE OR DELETE ON task_input_bindings
FOR EACH ROW EXECUTE FUNCTION reject_context_update();
CREATE TRIGGER decision_context_packs_immutable_update
BEFORE UPDATE OR DELETE ON decision_context_packs
FOR EACH ROW EXECUTE FUNCTION reject_context_update();
