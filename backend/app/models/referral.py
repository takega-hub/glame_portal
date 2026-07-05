import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.connection import Base


class ReferralProgramMember(Base):
    __tablename__ = "referral_program_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)

    status = Column(String(32), nullable=False, default="active", index=True)
    reward_mode = Column(String(16), nullable=False, default="points", index=True)
    program_level = Column(String(32), nullable=False, default="starter", index=True)

    points_rate_percent = Column(Numeric(5, 2), nullable=False, default=5)
    cash_rate_percent = Column(Numeric(5, 2), nullable=False, default=5)
    cash_eligible = Column(Boolean, nullable=False, default=False, index=True)
    cash_eligible_at = Column(DateTime(timezone=True), nullable=True)
    cash_eligibility_reason = Column(Text, nullable=True)
    cash_status = Column(String(32), nullable=False, default="unavailable", index=True)

    legal_status = Column(String(32), nullable=True)
    inn = Column(String(32), nullable=True, index=True)
    passport_data = Column(JSON, nullable=True)
    payout_details = Column(JSON, nullable=True)
    tax_responsibility_confirmed_at = Column(DateTime(timezone=True), nullable=True)

    onec_counterparty_id = Column(String(255), nullable=True, index=True)
    onec_agency_contract_id = Column(String(255), nullable=True, index=True)
    onec_sync_status = Column(String(32), nullable=True, index=True)
    onec_last_error = Column(Text, nullable=True)

    approved_at = Column(DateTime(timezone=True), nullable=True)
    blocked_at = Column(DateTime(timezone=True), nullable=True)
    block_reason = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id], backref="referral_program_member")
    codes = relationship("ReferralCode", back_populates="member")

    __table_args__ = (
        Index("ix_referral_members_status_reward", "status", "reward_mode"),
        Index("ix_referral_members_cash", "cash_eligible", "cash_status"),
    )


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(UUID(as_uuid=True), ForeignKey("referral_program_members.id"), nullable=False, index=True)
    code = Column(String(32), nullable=False, unique=True, index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    source = Column(String(32), nullable=False, default="portal")
    usage_count = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    member = relationship("ReferralProgramMember", back_populates="codes")

    __table_args__ = (
        Index("ix_referral_codes_member_status", "member_id", "status"),
    )


class ReferralAttribution(Base):
    __tablename__ = "referral_attributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_member_id = Column(UUID(as_uuid=True), ForeignKey("referral_program_members.id"), nullable=False, index=True)
    referral_code_id = Column(UUID(as_uuid=True), ForeignKey("referral_codes.id"), nullable=True, index=True)
    referee_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    referee_phone_hash = Column(String(128), nullable=True, index=True)

    status = Column(String(32), nullable=False, default="pending", index=True)
    source = Column(String(32), nullable=False, default="web", index=True)
    first_purchase_order_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    first_purchase_id = Column(UUID(as_uuid=True), ForeignKey("purchase_history.id"), nullable=True, index=True)
    first_purchase_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    referrer = relationship("ReferralProgramMember", foreign_keys=[referrer_member_id])
    code = relationship("ReferralCode", foreign_keys=[referral_code_id])
    referee = relationship("User", foreign_keys=[referee_user_id])
    first_purchase = relationship("PurchaseHistory", foreign_keys=[first_purchase_id])

    __table_args__ = (
        Index("ix_referral_attributions_referrer_status", "referrer_member_id", "status"),
        Index("ix_referral_attributions_referee_status", "referee_user_id", "status"),
    )


class ReferralCommission(Base):
    __tablename__ = "referral_commissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attribution_id = Column(UUID(as_uuid=True), ForeignKey("referral_attributions.id"), nullable=False, index=True)
    referrer_member_id = Column(UUID(as_uuid=True), ForeignKey("referral_program_members.id"), nullable=False, index=True)
    referee_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)

    order_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    purchase_id = Column(UUID(as_uuid=True), ForeignKey("purchase_history.id"), nullable=True, index=True)
    reward_mode = Column(String(16), nullable=False, default="points", index=True)
    commission_base = Column(Integer, nullable=False, default=0)
    rate_percent = Column(Numeric(5, 2), nullable=False, default=5)
    amount_kopecks = Column(Integer, nullable=False, default=0)
    points = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="hold", index=True)
    hold_until = Column(DateTime(timezone=True), nullable=True, index=True)

    loyalty_transaction_id = Column(UUID(as_uuid=True), ForeignKey("loyalty_transactions.id"), nullable=True, index=True)
    onec_document_id = Column(String(255), nullable=True, index=True)
    onec_sync_status = Column(String(32), nullable=True, index=True)
    onec_last_error = Column(Text, nullable=True)

    calculated_at = Column(DateTime(timezone=True), server_default=func.now())
    approved_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    attribution = relationship("ReferralAttribution", foreign_keys=[attribution_id])
    referrer = relationship("ReferralProgramMember", foreign_keys=[referrer_member_id])
    referee = relationship("User", foreign_keys=[referee_user_id])
    purchase = relationship("PurchaseHistory", foreign_keys=[purchase_id])
    loyalty_transaction = relationship("LoyaltyTransaction", foreign_keys=[loyalty_transaction_id])

    __table_args__ = (
        Index("ix_referral_commissions_referrer_status", "referrer_member_id", "status"),
        Index("ix_referral_commissions_reward_status", "reward_mode", "status"),
        Index("ix_referral_commissions_purchase_mode", "purchase_id", "reward_mode"),
    )


class ReferralPayout(Base):
    __tablename__ = "referral_payouts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(UUID(as_uuid=True), ForeignKey("referral_program_members.id"), nullable=False, index=True)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    amount_kopecks = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="pending", index=True)
    onec_payment_document_id = Column(String(255), nullable=True, index=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    approved_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    member = relationship("ReferralProgramMember", foreign_keys=[member_id])

    __table_args__ = (
        Index("ix_referral_payouts_member_status", "member_id", "status"),
    )


class ReferralCashUpgradeRequest(Base):
    __tablename__ = "referral_cash_upgrade_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(UUID(as_uuid=True), ForeignKey("referral_program_members.id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    legal_status = Column(String(32), nullable=False)
    inn = Column(String(32), nullable=False, index=True)
    passport_data = Column(JSON, nullable=True)
    payout_details = Column(JSON, nullable=True)
    tax_responsibility_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    reviewer_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_comment = Column(Text, nullable=True)
    onec_sync_status = Column(String(32), nullable=True, index=True)
    onec_last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    member = relationship("ReferralProgramMember", foreign_keys=[member_id])
    reviewer = relationship("User", foreign_keys=[reviewer_user_id])

    __table_args__ = (
        Index("ix_referral_cash_requests_member_status", "member_id", "status"),
    )
