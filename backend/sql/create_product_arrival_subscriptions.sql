CREATE TABLE IF NOT EXISTS product_arrival_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    variant_product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    email VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    source VARCHAR(64) NULL,
    variant_label VARCHAR(255) NULL,
    product_snapshot JSONB NULL DEFAULT '{}'::jsonb,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    notified_at TIMESTAMPTZ NULL,
    last_checked_at TIMESTAMPTZ NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NULL
);

CREATE INDEX IF NOT EXISTS ix_product_arrival_subscriptions_product_id
    ON product_arrival_subscriptions(product_id);

CREATE INDEX IF NOT EXISTS ix_product_arrival_subscriptions_variant_product_id
    ON product_arrival_subscriptions(variant_product_id);

CREATE INDEX IF NOT EXISTS ix_product_arrival_subscriptions_user_id
    ON product_arrival_subscriptions(user_id);

CREATE INDEX IF NOT EXISTS ix_product_arrival_subscriptions_email
    ON product_arrival_subscriptions(email);

CREATE INDEX IF NOT EXISTS ix_product_arrival_subscriptions_status
    ON product_arrival_subscriptions(status);

CREATE INDEX IF NOT EXISTS ix_product_arrival_pending_variant
    ON product_arrival_subscriptions(status, variant_product_id);

CREATE INDEX IF NOT EXISTS ix_product_arrival_email_variant_status
    ON product_arrival_subscriptions(email, variant_product_id, status);
