-- SQL скрипт для создания таблиц напрямую в PostgreSQL
-- Запуск: psql -U glame_user -d glame_db -f create_tables.sql

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    persona VARCHAR(50),
    preferences JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);

CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    brand VARCHAR(100),
    price INTEGER NOT NULL,
    category VARCHAR(100),
    images JSONB,
    tags JSONB,
    description TEXT,
    article VARCHAR(100),
    vendor_code VARCHAR(100),
    barcode VARCHAR(100),
    unit VARCHAR(50),
    weight FLOAT,
    volume FLOAT,
    country VARCHAR(100),
    warranty VARCHAR(100),
    full_description TEXT,
    specifications JSONB,
    onec_data JSONB,
    -- 1C integration fields (added later; keep for new DBs)
    external_id VARCHAR(255),
    external_code VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sync_status VARCHAR(50),
    sync_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for 1C integration fields
CREATE INDEX IF NOT EXISTS ix_products_external_id ON products(external_id);
CREATE INDEX IF NOT EXISTS ix_products_external_code ON products(external_code);
CREATE INDEX IF NOT EXISTS ix_products_article ON products(article);
CREATE INDEX IF NOT EXISTS ix_products_is_active ON products(is_active);

CREATE TABLE IF NOT EXISTS product_stocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    store_id VARCHAR(255) NOT NULL,
    quantity FLOAT NOT NULL DEFAULT 0,
    reserved_quantity FLOAT NOT NULL DEFAULT 0,
    available_quantity FLOAT NOT NULL DEFAULT 0,
    last_synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_product_stocks_product_id ON product_stocks(product_id);
CREATE INDEX IF NOT EXISTS ix_product_stocks_store_id ON product_stocks(store_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_product_stocks_product_store ON product_stocks(product_id, store_id);

CREATE TABLE IF NOT EXISTS looks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    product_ids JSONB NOT NULL,
    style VARCHAR(100),
    mood VARCHAR(100),
    description TEXT,
    image_url VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    interactions JSONB,
    persona_detected VARCHAR(50),
    cjm_stage VARCHAR(50),
    city VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS analytics_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =========================
-- Content Calendar / Plans
-- =========================

CREATE TABLE IF NOT EXISTS content_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    end_date TIMESTAMP WITH TIME ZONE NOT NULL,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Moscow',
    inputs JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_content_plans_status ON content_plans(status);
CREATE INDEX IF NOT EXISTS ix_content_plans_start_date ON content_plans(start_date);
CREATE INDEX IF NOT EXISTS ix_content_plans_end_date ON content_plans(end_date);

CREATE TABLE IF NOT EXISTS content_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL REFERENCES content_plans(id),
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Moscow',
    channel VARCHAR(64) NOT NULL,
    content_type VARCHAR(64) NOT NULL DEFAULT 'post',
    topic VARCHAR(500),
    hook VARCHAR(500),
    cta VARCHAR(500),
    persona VARCHAR(500),
    cjm_stage VARCHAR(64),
    goal VARCHAR(500),
    spec JSONB,
    generated JSONB,
    generated_text TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'planned',
    published_at TIMESTAMP WITH TIME ZONE,
    publication_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_content_items_plan_id ON content_items(plan_id);
CREATE INDEX IF NOT EXISTS ix_content_items_scheduled_at ON content_items(scheduled_at);
CREATE INDEX IF NOT EXISTS ix_content_items_status ON content_items(status);
CREATE INDEX IF NOT EXISTS ix_content_items_channel ON content_items(channel);

CREATE TABLE IF NOT EXISTS content_publications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id UUID NOT NULL REFERENCES content_items(id),
    provider VARCHAR(64) NOT NULL DEFAULT 'glame',
    status VARCHAR(50) NOT NULL DEFAULT 'created',
    external_id VARCHAR(255),
    request_payload JSONB,
    response_payload JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_content_publications_item_id ON content_publications(item_id);
CREATE INDEX IF NOT EXISTS ix_content_publications_status ON content_publications(status);