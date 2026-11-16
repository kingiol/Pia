PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rulesets (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  version TEXT NOT NULL,
  definition_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE(user_id, version)
);

CREATE TABLE IF NOT EXISTS rule_snapshots (
  id TEXT PRIMARY KEY,
  ruleset_id TEXT NOT NULL,
  version TEXT NOT NULL,
  definition_hash TEXT NOT NULL,
  definition_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_snapshots (
  id TEXT PRIMARY KEY,
  as_of TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  source TEXT NOT NULL,
  quality TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  as_of TEXT NOT NULL,
  cash REAL NOT NULL,
  total_value REAL NOT NULL,
  source TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_tasks (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  trigger_type TEXT NOT NULL,
  target_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  data_snapshot_id TEXT,
  rule_snapshot_id TEXT,
  parent_task_id TEXT,
  error_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_research_tasks_created_at ON research_tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_tasks_status ON research_tasks(status);

CREATE TABLE IF NOT EXISTS agent_runs (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  agent_name TEXT NOT NULL,
  status TEXT NOT NULL,
  input_json TEXT NOT NULL,
  output_json TEXT,
  error_json TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  model TEXT,
  token_usage INTEGER
);

CREATE TABLE IF NOT EXISTS tool_calls (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  agent_run_id TEXT,
  tool_name TEXT NOT NULL,
  input_json TEXT NOT NULL,
  output_json TEXT,
  status TEXT NOT NULL,
  latency_ms INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_uri TEXT,
  title TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  as_of TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  quality TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  snapshot_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  confidence TEXT NOT NULL,
  rationale_json TEXT NOT NULL,
  invalidation_json TEXT NOT NULL,
  risk_level TEXT NOT NULL,
  next_action TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  action TEXT NOT NULL,
  created_at TEXT NOT NULL,
  rule_snapshot_id TEXT,
  data_snapshot_id TEXT,
  notes TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
