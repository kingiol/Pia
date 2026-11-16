ALTER TABLE evidence ADD COLUMN IF NOT EXISTS provider_id TEXT;

CREATE INDEX IF NOT EXISTS idx_evidence_provider
  ON evidence(provider_id);
