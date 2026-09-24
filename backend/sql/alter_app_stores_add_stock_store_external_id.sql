ALTER TABLE app_stores
ADD COLUMN IF NOT EXISTS stock_store_external_id varchar(255);

CREATE INDEX IF NOT EXISTS ix_app_stores_stock_store_external_id
ON app_stores(stock_store_external_id);
