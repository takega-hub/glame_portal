import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.connection import Base


class GlameTokenAccount(Base):
    __tablename__ = "glame_token_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    referral_member_id = Column(
        UUID(as_uuid=True),
        ForeignKey("referral_program_members.id"),
        nullable=True,
        index=True,
    )

    token_code = Column(String(16), nullable=False, default="GLM", index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    balance = Column(Integer, nullable=False, default=0)
    hold_balance = Column(Integer, nullable=False, default=0)
    lifetime_earned = Column(Integer, nullable=False, default=0)
    lifetime_burned = Column(Integer, nullable=False, default=0)

    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])
    referral_member = relationship("ReferralProgramMember", foreign_keys=[referral_member_id])

    __table_args__ = (
        UniqueConstraint("referral_member_id", "token_code", name="uq_glame_token_accounts_referral_member_token"),
        Index("ix_glame_token_accounts_user_token", "user_id", "token_code"),
    )


class GlameTokenTransaction(Base):
    __tablename__ = "glame_token_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("glame_token_accounts.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    referral_member_id = Column(UUID(as_uuid=True), ForeignKey("referral_program_members.id"), nullable=True, index=True)
    referral_commission_id = Column(UUID(as_uuid=True), ForeignKey("referral_commissions.id"), nullable=True, index=True)

    token_code = Column(String(16), nullable=False, default="GLM", index=True)
    transaction_type = Column(String(50), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="hold", index=True)
    amount = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False, default=0)
    hold_balance_after = Column(Integer, nullable=False, default=0)

    reason = Column(String(100), nullable=True, index=True)
    description = Column(Text, nullable=True)
    source = Column(String(50), nullable=True, index=True)
    source_id = Column(String(255), nullable=True, unique=True, index=True)
    available_at = Column(DateTime(timezone=True), nullable=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    account = relationship("GlameTokenAccount", foreign_keys=[account_id])
    user = relationship("User", foreign_keys=[user_id])
    referral_member = relationship("ReferralProgramMember", foreign_keys=[referral_member_id])
    referral_commission = relationship("ReferralCommission", foreign_keys=[referral_commission_id])

    __table_args__ = (
        Index("ix_glame_token_transactions_account_date", "account_id", "created_at"),
        Index("ix_glame_token_transactions_member_status", "referral_member_id", "status"),
        Index("ix_glame_token_transactions_commission", "referral_commission_id", "transaction_type"),
    )


class GlameTokenDailyAuditHash(Base):
    __tablename__ = "glame_token_daily_audit_hashes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_date = Column(Date, nullable=False, unique=True, index=True)
    token_code = Column(String(16), nullable=False, default="GLM", index=True)
    root_hash = Column(String(64), nullable=False)
    previous_root_hash = Column(String(64), nullable=True)
    transactions_count = Column(Integer, nullable=False, default=0)
    accounts_count = Column(Integer, nullable=False, default=0)
    balance_total = Column(Integer, nullable=False, default=0)
    hold_total = Column(Integer, nullable=False, default=0)
    lifetime_earned_total = Column(Integer, nullable=False, default=0)
    lifetime_burned_total = Column(Integer, nullable=False, default=0)
    payload = Column(JSON, nullable=False, default=dict)
    public_status = Column(String(32), nullable=False, default="internal", index=True)
    public_reference = Column(Text, nullable=True)
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    user = relationship("User", foreign_keys=[generated_by])


class GlameTokenBridgeOperation(Base):
    __tablename__ = "glame_token_bridge_operations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("glame_token_transactions.id"), nullable=False, unique=True, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("glame_token_accounts.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    referral_member_id = Column(UUID(as_uuid=True), ForeignKey("referral_program_members.id"), nullable=True, index=True)

    token_code = Column(String(16), nullable=False, default="GLM", index=True)
    direction = Column(String(32), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    idempotency_key = Column(String(255), nullable=False, unique=True, index=True)

    points_amount = Column(Integer, nullable=False, default=0)
    glm_amount = Column(Integer, nullable=False, default=0)
    rate_basis = Column(String(64), nullable=True)

    ton_network = Column(String(32), nullable=True, index=True)
    ton_sender_address = Column(String(128), nullable=True, index=True)
    ton_recipient_address = Column(String(128), nullable=True, index=True)
    ton_treasury_address = Column(String(128), nullable=True, index=True)
    ton_tx_hash = Column(String(128), nullable=True, index=True)
    ton_status = Column(String(64), nullable=True, index=True)

    onec_document_id = Column(String(128), nullable=True, index=True)
    onec_status = Column(String(64), nullable=True, index=True)
    onec_error = Column(Text, nullable=True)

    source = Column(String(64), nullable=True, index=True)
    source_id = Column(String(255), nullable=True, index=True)
    meta = Column(JSON, nullable=True)
    requested_at = Column(DateTime(timezone=True), nullable=True, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    transaction = relationship("GlameTokenTransaction", foreign_keys=[transaction_id])
    account = relationship("GlameTokenAccount", foreign_keys=[account_id])
    user = relationship("User", foreign_keys=[user_id])
    referral_member = relationship("ReferralProgramMember", foreign_keys=[referral_member_id])

    __table_args__ = (
        Index("ix_glame_token_bridge_ops_direction_status", "direction", "status"),
        Index("ix_glame_token_bridge_ops_member_direction", "referral_member_id", "direction"),
        Index("ix_glame_token_bridge_ops_onec", "onec_status", "onec_document_id"),
        Index("ix_glame_token_bridge_ops_ton", "ton_status", "ton_tx_hash"),
    )


class GlameTreasuryRefillCheck(Base):
    __tablename__ = "glame_treasury_refill_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(32), nullable=False, default="balance_check", index=True)
    status = Column(String(32), nullable=False, index=True)
    reason = Column(String(64), nullable=True, index=True)
    network = Column(String(32), nullable=True, index=True)

    treasury_address = Column(String(128), nullable=True, index=True)
    hot_wallet_address = Column(String(128), nullable=True, index=True)
    ton_tx_hash = Column(String(128), nullable=True, index=True)

    refill_glm_amount = Column(Numeric(20, 9), nullable=True)
    refill_ton_amount = Column(Numeric(20, 9), nullable=True)
    manual_glm_amount = Column(Numeric(20, 9), nullable=True)
    manual_ton_amount = Column(Numeric(20, 9), nullable=True)

    hot_wallet_glm_balance = Column(Numeric(20, 9), nullable=True)
    hot_wallet_ton_balance = Column(Numeric(20, 9), nullable=True)
    treasury_glm_balance = Column(Numeric(20, 9), nullable=True)
    treasury_ton_balance = Column(Numeric(20, 9), nullable=True)
    target_glm = Column(Numeric(20, 9), nullable=True)
    target_ton = Column(Numeric(20, 9), nullable=True)
    threshold_glm = Column(Numeric(20, 9), nullable=True)
    threshold_ton = Column(Numeric(20, 9), nullable=True)

    errors = Column(JSON, nullable=True)
    payload = Column(JSON, nullable=True)
    comment = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("ix_glame_treasury_refill_checks_event_created", "event_type", "created_at"),
        Index("ix_glame_treasury_refill_checks_status_created", "status", "created_at"),
    )
