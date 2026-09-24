CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS crm_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_seller_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    assigned_seller_external_id VARCHAR(255) NULL,
    assigned_seller_name VARCHAR(255) NULL,
    store_id VARCHAR(255) NULL,
    store_name VARCHAR(255) NULL,
    work_date DATE NOT NULL,
    due_date TIMESTAMPTZ NULL,
    priority INTEGER NOT NULL DEFAULT 3,
    crm_group VARCHAR(64) NOT NULL,
    reason TEXT NULL,
    seller_action TEXT NULL,
    script_key VARCHAR(128) NULL,
    script_text TEXT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'new',
    seller_outcome VARCHAR(64) NULL,
    seller_comment TEXT NULL,
    next_action_date DATE NULL,
    campaign_id VARCHAR(255) NULL,
    campaign_name VARCHAR(255) NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'manual',
    source_row_id VARCHAR(255) NULL,
    source_idempotency_key VARCHAR(255) NULL UNIQUE,
    source_payload JSONB NULL DEFAULT '{}'::jsonb,
    last_contacted_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    attributed_purchase_count INTEGER NOT NULL DEFAULT 0,
    attributed_revenue_kopecks INTEGER NOT NULL DEFAULT 0,
    attributed_purchase_ids JSONB NULL DEFAULT '[]'::jsonb,
    attributed_at TIMESTAMPTZ NULL,
    created_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS crm_task_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES crm_tasks(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    actor_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    actor_name VARCHAR(255) NULL,
    previous_status VARCHAR(32) NULL,
    next_status VARCHAR(32) NULL,
    payload JSONB NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_crm_tasks_customer ON crm_tasks(customer_id);
CREATE INDEX IF NOT EXISTS ix_crm_tasks_seller_date ON crm_tasks(assigned_seller_external_id, work_date);
CREATE INDEX IF NOT EXISTS ix_crm_tasks_seller_user_date ON crm_tasks(assigned_seller_user_id, work_date);
CREATE INDEX IF NOT EXISTS ix_crm_tasks_store_date ON crm_tasks(store_name, work_date);
CREATE INDEX IF NOT EXISTS ix_crm_tasks_status ON crm_tasks(status);
CREATE INDEX IF NOT EXISTS ix_crm_tasks_campaign ON crm_tasks(campaign_id);
CREATE INDEX IF NOT EXISTS ix_crm_tasks_source_idempotency_key ON crm_tasks(source_idempotency_key);
CREATE INDEX IF NOT EXISTS ix_crm_task_events_task_created ON crm_task_events(task_id, created_at);
CREATE INDEX IF NOT EXISTS ix_crm_task_events_type_created ON crm_task_events(event_type, created_at);
