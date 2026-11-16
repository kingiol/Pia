ALTER TABLE evidence ADD COLUMN source TEXT NOT NULL DEFAULT 'unknown';

CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source);
