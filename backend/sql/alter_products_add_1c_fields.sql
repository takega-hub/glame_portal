-- Idempotent patch: add 1C integration columns to existing `products` table
-- Run (docker): docker exec -i glame_postgres psql -U glame_user -d glame_db -f - < backend/sql/alter_products_add_1c_fields.sql

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS external_id VARCHAR(255);

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS external_code VARCHAR(100);

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS sync_status VARCHAR(50);

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS sync_metadata JSONB;

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS article VARCHAR(100);

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS vendor_code VARCHAR(100);

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS barcode VARCHAR(100);

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS unit VARCHAR(50);

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS weight FLOAT;

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS volume FLOAT;

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS country VARCHAR(100);

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS warranty VARCHAR(100);

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS full_description TEXT;

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS specifications JSONB;

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS onec_data JSONB;

CREATE INDEX IF NOT EXISTS ix_products_external_id ON products(external_id);
CREATE INDEX IF NOT EXISTS ix_products_external_code ON products(external_code);
CREATE INDEX IF NOT EXISTS ix_products_article ON products(article);
CREATE INDEX IF NOT EXISTS ix_products_is_active ON products(is_active);

