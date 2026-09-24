CREATE TABLE IF NOT EXISTS crm_service_cases (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    case_type VARCHAR(64),
    title VARCHAR(255),
    description TEXT,
    source VARCHAR(64) NOT NULL DEFAULT 'manual',
    source_payload JSONB,
    opened_at TIMESTAMPTZ DEFAULT now(),
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_crm_service_cases_customer ON crm_service_cases(customer_id);
CREATE INDEX IF NOT EXISTS ix_crm_service_cases_status ON crm_service_cases(status);
CREATE INDEX IF NOT EXISTS ix_crm_service_cases_type ON crm_service_cases(case_type);
CREATE INDEX IF NOT EXISTS ix_crm_service_cases_customer_status ON crm_service_cases(customer_id, status);
