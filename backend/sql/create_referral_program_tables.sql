CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS referral_program_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    reward_mode VARCHAR(16) NOT NULL DEFAULT 'points',
    program_level VARCHAR(32) NOT NULL DEFAULT 'stylish_start',
    points_rate_percent NUMERIC(5, 2) NOT NULL DEFAULT 3,
    cash_rate_percent NUMERIC(5, 2) NOT NULL DEFAULT 3,
    cash_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    cash_eligible_at TIMESTAMPTZ NULL,
    cash_eligibility_reason TEXT NULL,
    cash_status VARCHAR(32) NOT NULL DEFAULT 'unavailable',
    legal_status VARCHAR(32) NULL,
    inn VARCHAR(32) NULL,
    passport_data JSONB NULL,
    payout_details JSONB NULL,
    tax_responsibility_confirmed_at TIMESTAMPTZ NULL,
    onec_counterparty_id VARCHAR(255) NULL,
    onec_agency_contract_id VARCHAR(255) NULL,
    onec_sync_status VARCHAR(32) NULL,
    onec_last_error TEXT NULL,
    approved_at TIMESTAMPTZ NULL,
    blocked_at TIMESTAMPTZ NULL,
    block_reason TEXT NULL,
    meta JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_referral_members_reward_mode CHECK (reward_mode IN ('points', 'cash')),
    CONSTRAINT ck_referral_members_status CHECK (status IN ('pending', 'active', 'blocked', 'archived')),
    CONSTRAINT ck_referral_members_cash_status CHECK (cash_status IN ('unavailable', 'eligible', 'pending', 'active', 'rejected'))
);

CREATE TABLE IF NOT EXISTS referral_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL REFERENCES referral_program_members(id) ON DELETE CASCADE,
    code VARCHAR(32) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    source VARCHAR(32) NOT NULL DEFAULT 'portal',
    usage_count INTEGER NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_referral_codes_status CHECK (status IN ('active', 'paused', 'expired', 'archived'))
);

CREATE TABLE IF NOT EXISTS referral_attributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_member_id UUID NOT NULL REFERENCES referral_program_members(id) ON DELETE CASCADE,
    referral_code_id UUID NULL REFERENCES referral_codes(id) ON DELETE SET NULL,
    referee_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    referee_phone_hash VARCHAR(128) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    source VARCHAR(32) NOT NULL DEFAULT 'web',
    first_purchase_order_id UUID NULL,
    first_purchase_id UUID NULL REFERENCES purchase_history(id) ON DELETE SET NULL,
    first_purchase_at TIMESTAMPTZ NULL,
    activated_at TIMESTAMPTZ NULL,
    canceled_at TIMESTAMPTZ NULL,
    cancel_reason TEXT NULL,
    meta JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_referral_attributions_status CHECK (status IN ('pending', 'active', 'canceled', 'expired'))
);

CREATE TABLE IF NOT EXISTS referral_commissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attribution_id UUID NOT NULL REFERENCES referral_attributions(id) ON DELETE CASCADE,
    referrer_member_id UUID NOT NULL REFERENCES referral_program_members(id) ON DELETE CASCADE,
    referee_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    order_id UUID NULL,
    purchase_id UUID NULL REFERENCES purchase_history(id) ON DELETE SET NULL,
    reward_mode VARCHAR(16) NOT NULL DEFAULT 'points',
    commission_base INTEGER NOT NULL DEFAULT 0,
    rate_percent NUMERIC(5, 2) NOT NULL DEFAULT 5,
    amount_kopecks INTEGER NOT NULL DEFAULT 0,
    points INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'hold',
    hold_until TIMESTAMPTZ NULL,
    loyalty_transaction_id UUID NULL REFERENCES loyalty_transactions(id) ON DELETE SET NULL,
    onec_document_id VARCHAR(255) NULL,
    onec_sync_status VARCHAR(32) NULL,
    onec_last_error TEXT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ NULL,
    paid_at TIMESTAMPTZ NULL,
    meta JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_referral_commissions_reward_mode CHECK (reward_mode IN ('points', 'cash')),
    CONSTRAINT ck_referral_commissions_status CHECK (status IN ('pending', 'hold', 'approved', 'accrued_in_1c', 'paid', 'canceled'))
);

CREATE TABLE IF NOT EXISTS referral_payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL REFERENCES referral_program_members(id) ON DELETE CASCADE,
    period_start TIMESTAMPTZ NULL,
    period_end TIMESTAMPTZ NULL,
    amount_kopecks INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    onec_payment_document_id VARCHAR(255) NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ NULL,
    paid_at TIMESTAMPTZ NULL,
    meta JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_referral_payouts_status CHECK (status IN ('pending', 'approved', 'paid', 'rejected', 'canceled'))
);

CREATE TABLE IF NOT EXISTS referral_cash_upgrade_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL REFERENCES referral_program_members(id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    legal_status VARCHAR(32) NOT NULL,
    inn VARCHAR(32) NOT NULL,
    passport_data JSONB NULL,
    payout_details JSONB NULL,
    tax_responsibility_confirmed_at TIMESTAMPTZ NULL,
    reviewer_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ NULL,
    review_comment TEXT NULL,
    onec_sync_status VARCHAR(32) NULL,
    onec_last_error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_referral_cash_requests_status CHECK (status IN ('pending', 'approved', 'rejected', 'canceled')),
    CONSTRAINT ck_referral_cash_requests_legal_status CHECK (legal_status IN ('self_employed', 'ip'))
);

CREATE INDEX IF NOT EXISTS ix_referral_members_status_reward ON referral_program_members(status, reward_mode);
CREATE INDEX IF NOT EXISTS ix_referral_members_cash ON referral_program_members(cash_eligible, cash_status);
CREATE INDEX IF NOT EXISTS ix_referral_members_inn ON referral_program_members(inn);
CREATE INDEX IF NOT EXISTS ix_referral_members_onec_counterparty ON referral_program_members(onec_counterparty_id);
CREATE INDEX IF NOT EXISTS ix_referral_members_onec_contract ON referral_program_members(onec_agency_contract_id);

CREATE INDEX IF NOT EXISTS ix_referral_codes_member_status ON referral_codes(member_id, status);
CREATE INDEX IF NOT EXISTS ix_referral_codes_code_lower ON referral_codes(LOWER(code));

CREATE INDEX IF NOT EXISTS ix_referral_attributions_referrer_status ON referral_attributions(referrer_member_id, status);
CREATE INDEX IF NOT EXISTS ix_referral_attributions_referee_status ON referral_attributions(referee_user_id, status);
CREATE INDEX IF NOT EXISTS ix_referral_attributions_code_status ON referral_attributions(referral_code_id, status);
CREATE INDEX IF NOT EXISTS ix_referral_attributions_phone_hash ON referral_attributions(referee_phone_hash);
CREATE UNIQUE INDEX IF NOT EXISTS ux_referral_attributions_one_active_referee
    ON referral_attributions(referee_user_id)
    WHERE referee_user_id IS NOT NULL AND status IN ('pending', 'active');

CREATE INDEX IF NOT EXISTS ix_referral_commissions_referrer_status ON referral_commissions(referrer_member_id, status);
CREATE INDEX IF NOT EXISTS ix_referral_commissions_reward_status ON referral_commissions(reward_mode, status);
CREATE INDEX IF NOT EXISTS ix_referral_commissions_purchase_mode ON referral_commissions(purchase_id, reward_mode);
CREATE INDEX IF NOT EXISTS ix_referral_commissions_order_mode ON referral_commissions(order_id, reward_mode);
CREATE INDEX IF NOT EXISTS ix_referral_commissions_onec_document ON referral_commissions(onec_document_id);

CREATE INDEX IF NOT EXISTS ix_referral_payouts_member_status ON referral_payouts(member_id, status);
CREATE INDEX IF NOT EXISTS ix_referral_cash_requests_member_status ON referral_cash_upgrade_requests(member_id, status);
