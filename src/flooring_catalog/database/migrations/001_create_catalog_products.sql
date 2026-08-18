-- pgvector is prepared now; embedding storage and search belong to Step 3.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS catalog_products (
    sku TEXT PRIMARY KEY,
    name TEXT,
    z_prod_type TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (lower(btrim(status)) = 'active'),
    swatch TEXT NOT NULL CHECK (btrim(swatch) <> ''),
    price NUMERIC(12, 2) CHECK (price > 0),
    brand TEXT,
    material TEXT,
    color TEXT,
    style TEXT,
    description TEXT,
    gallery_images TEXT,
    waterproof TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(metadata) = 'object'),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_catalog_products_type
    ON catalog_products (z_prod_type);
CREATE INDEX IF NOT EXISTS idx_catalog_products_brand
    ON catalog_products (brand);
CREATE INDEX IF NOT EXISTS idx_catalog_products_material
    ON catalog_products (material);
CREATE INDEX IF NOT EXISTS idx_catalog_products_color
    ON catalog_products (color);
CREATE INDEX IF NOT EXISTS idx_catalog_products_style
    ON catalog_products (style);
CREATE INDEX IF NOT EXISTS idx_catalog_products_price
    ON catalog_products (price) WHERE price IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_catalog_products_waterproof
    ON catalog_products (waterproof);
CREATE INDEX IF NOT EXISTS idx_catalog_products_metadata
    ON catalog_products USING GIN (metadata);

