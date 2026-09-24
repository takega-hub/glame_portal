CREATE TABLE IF NOT EXISTS product_stock_arrival_events (
    id UUID PRIMARY KEY,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    store_id VARCHAR(255) NOT NULL,
    previous_available_quantity DOUBLE PRECISION NOT NULL DEFAULT 0,
    available_quantity DOUBLE PRECISION NOT NULL DEFAULT 0,
    delta_quantity DOUBLE PRECISION NOT NULL DEFAULT 0,
    event_type VARCHAR(64) NOT NULL DEFAULT 'RESTOCK',
    source VARCHAR(64) NOT NULL DEFAULT 'onec_stock_sync',
    source_sync_id VARCHAR(128) NOT NULL,
    source_idempotency_key VARCHAR(255) NOT NULL UNIQUE,
    source_payload JSONB,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_product_stock_arrival_events_idempotency
    ON product_stock_arrival_events(source_idempotency_key);
CREATE INDEX IF NOT EXISTS ix_stock_arrival_events_product
    ON product_stock_arrival_events(product_id);
CREATE INDEX IF NOT EXISTS ix_stock_arrival_events_store_received
    ON product_stock_arrival_events(store_id, received_at);
CREATE INDEX IF NOT EXISTS ix_stock_arrival_events_processed_received
    ON product_stock_arrival_events(processed_at, received_at);
CREATE INDEX IF NOT EXISTS ix_stock_arrival_events_event_type
    ON product_stock_arrival_events(event_type);
