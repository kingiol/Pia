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
CREATE TRIGGER IF NOT EXISTS task_input_bindings_immutable_update
BEFORE UPDATE ON task_input_bindings BEGIN
    SELECT RAISE(ABORT, 'task inputs are immutable');
END;
CREATE TRIGGER IF NOT EXISTS decision_context_packs_immutable_update
BEFORE UPDATE ON decision_context_packs BEGIN
    SELECT RAISE(ABORT, 'context packs are immutable');
END;
CREATE TRIGGER IF NOT EXISTS task_input_bindings_immutable_delete
BEFORE DELETE ON task_input_bindings BEGIN
    SELECT RAISE(ABORT, 'task inputs are immutable');
END;
CREATE TRIGGER IF NOT EXISTS decision_context_packs_immutable_delete
BEFORE DELETE ON decision_context_packs BEGIN
    SELECT RAISE(ABORT, 'context packs are immutable');
END;
