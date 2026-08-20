ALTER TABLE catalog_products
    DROP CONSTRAINT IF EXISTS catalog_products_status_check;

ALTER TABLE catalog_products
    ADD CONSTRAINT catalog_products_status_check
    CHECK (lower(btrim(status)) IN ('active', 'inactive'));

ALTER TABLE catalog_products
    ADD COLUMN IF NOT EXISTS last_seen_sync_id UUID;

CREATE INDEX IF NOT EXISTS idx_catalog_products_last_seen_sync
    ON catalog_products (last_seen_sync_id);

CREATE TABLE IF NOT EXISTS catalog_sync_runs (
    run_id UUID PRIMARY KEY,
    source_name TEXT NOT NULL,
    authoritative_snapshot BOOLEAN NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    source_records INTEGER,
    upserted_records INTEGER,
    deactivated_records INTEGER,
    embedded_records INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_catalog_sync_runs_started
    ON catalog_sync_runs (started_at DESC);
