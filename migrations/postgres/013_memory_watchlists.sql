CREATE TABLE IF NOT EXISTS watchlists (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  symbols_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_watchlists_user
  ON watchlists(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS semantic_memories (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  symbol TEXT,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  source TEXT NOT NULL,
  as_of TEXT,
  observed_at TEXT,
  quality TEXT NOT NULL,
  task_id TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_semantic_memories_user
  ON semantic_memories(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_semantic_memories_symbol
  ON semantic_memories(user_id, symbol, created_at DESC);
