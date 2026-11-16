CREATE TABLE raw_provider_payloads (
    id VARCHAR PRIMARY KEY,
    provider_id VARCHAR NOT NULL,
    provider_version VARCHAR NOT NULL,
    adapter_version VARCHAR NOT NULL,
    as_of DATE,
    observed_at TIMESTAMP,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX raw_provider_snapshot_lookup
    ON raw_provider_payloads (as_of, provider_id, created_at DESC);

CREATE TABLE normalized_daily_bars (
    snapshot_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    trade_date DATE NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    amount DOUBLE PRECISION,
    provider_id VARCHAR NOT NULL,
    provider_version VARCHAR NOT NULL,
    adapter_version VARCHAR NOT NULL,
    as_of DATE,
    observed_at TIMESTAMP,
    quality VARCHAR NOT NULL,
    normalization_warnings_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, symbol, trade_date)
);

CREATE TABLE analytical_snapshots (
    snapshot_id VARCHAR PRIMARY KEY,
    kind VARCHAR NOT NULL,
    as_of DATE,
    observed_at TIMESTAMP,
    source VARCHAR NOT NULL,
    quality VARCHAR NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE normalized_universe (
    snapshot_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    name VARCHAR,
    asset_type VARCHAR,
    board VARCHAR,
    exchange VARCHAR,
    listed_at DATE,
    is_st BOOLEAN,
    is_delisting BOOLEAN,
    suspended BOOLEAN,
    active BOOLEAN,
    listed_days INTEGER,
    provider_id VARCHAR NOT NULL,
    provider_version VARCHAR NOT NULL,
    adapter_version VARCHAR NOT NULL,
    as_of DATE,
    observed_at TIMESTAMP,
    quality VARCHAR NOT NULL,
    PRIMARY KEY (snapshot_id, symbol)
);

CREATE TABLE normalized_fundamentals (
    snapshot_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    as_of DATE,
    metrics_json TEXT NOT NULL,
    provider_id VARCHAR NOT NULL,
    provider_version VARCHAR NOT NULL,
    adapter_version VARCHAR NOT NULL,
    observed_at TIMESTAMP,
    quality VARCHAR NOT NULL,
    PRIMARY KEY (snapshot_id, symbol)
);

CREATE TABLE normalized_research_sources (
    snapshot_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    source_type VARCHAR NOT NULL,
    external_id VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    published_at TIMESTAMP,
    source_uri VARCHAR,
    excerpt VARCHAR,
    content_hash VARCHAR NOT NULL,
    provider_id VARCHAR NOT NULL,
    provider_version VARCHAR NOT NULL,
    adapter_version VARCHAR NOT NULL,
    as_of DATE,
    observed_at TIMESTAMP,
    quality VARCHAR NOT NULL,
    PRIMARY KEY (snapshot_id, symbol, source_type, external_id)
);

CREATE TABLE normalized_trading_calendar (
    snapshot_id VARCHAR NOT NULL,
    trade_date DATE NOT NULL,
    is_open BOOLEAN NOT NULL,
    provider_id VARCHAR NOT NULL,
    provider_version VARCHAR NOT NULL,
    adapter_version VARCHAR NOT NULL,
    as_of DATE,
    observed_at TIMESTAMP,
    quality VARCHAR NOT NULL,
    PRIMARY KEY (snapshot_id, trade_date)
);
