ALTER TABLE catalog_products
    ADD COLUMN IF NOT EXISTS embedding vector(1536),
    ADD COLUMN IF NOT EXISTS embedding_model TEXT,
    ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ;

-- HNSW provides approximate cosine nearest-neighbor lookup without a training phase.
CREATE INDEX IF NOT EXISTS idx_catalog_products_embedding_hnsw
    ON catalog_products USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

-- Any change to searchable catalog facts invalidates the old vector. The embedding
-- worker will regenerate it without relying on ingestion code to detect every change.
CREATE OR REPLACE FUNCTION invalidate_catalog_product_embedding()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF ROW(
        OLD.name, OLD.z_prod_type, OLD.brand, OLD.material, OLD.color,
        OLD.style, OLD.description, OLD.waterproof, OLD.metadata
    ) IS DISTINCT FROM ROW(
        NEW.name, NEW.z_prod_type, NEW.brand, NEW.material, NEW.color,
        NEW.style, NEW.description, NEW.waterproof, NEW.metadata
    ) THEN
        NEW.embedding := NULL;
        NEW.embedding_model := NULL;
        NEW.embedding_updated_at := NULL;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_invalidate_catalog_product_embedding ON catalog_products;
CREATE TRIGGER trg_invalidate_catalog_product_embedding
BEFORE UPDATE ON catalog_products
FOR EACH ROW
EXECUTE FUNCTION invalidate_catalog_product_embedding();

