from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import html
import io
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from tonsdk.boc import Cell

from app.api.auth import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_current_user_optional,
    hash_password,
    normalize_phone,
    verify_password,
)
from app.api.dependencies import require_admin
from app.services.upload_security import validate_image_upload
from app.database.connection import get_db
from app.models.referral import ReferralAttribution, ReferralCashUpgradeRequest, ReferralCode, ReferralCommission, ReferralPayout, ReferralProgramMember
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.glame_token import GlameTokenAccount, GlameTokenBridgeOperation, GlameTokenDailyAuditHash, GlameTokenTransaction, GlameTreasuryRefillCheck
from app.models.reward_store import RewardStoreItem
from app.models.customer_message import CustomerMessage
from app.models.onec_user_sync_job import OneCUserSyncJob
from app.models.order import Order
from app.models.purchase_history import PurchaseHistory
from app.models.user import User
from app.services.loyalty_service import LoyaltyService
from app.services.glame_token_service import GlameTokenService, GLAME_TOKEN_MONTHLY_REFERRAL_EMISSION_LIMIT
from app.services.glame_token_scheduler import glm_token_scheduler_status, run_glm_telegram_alerts
from app.services.glm_telegram_alert_service import GlmTelegramAlertService
from app.services.ton_glm_auto_transfer_service import TonGlmAutoTransferService
from app.services.ton_glm_settlement_service import TonGlmSettlementService
from app.services.onec_customers_service import OneCCustomersService
from app.services.onec_user_registration_payload import OneCUserRegistrationPayload
from app.services.onec_user_sync_service import OneCUserSyncService
from app.services.referral_service import ReferralService, REFERRED_CLIENT_WELCOME_BONUS_POINTS
from app.services.customer_sync_service import CustomerSyncService
from app.services.telegram_service import TelegramService
from app.services.telegram_notification_service import TelegramNotificationService
from app.services.ton_glm_treasury_balance_service import TonGlmTreasuryBalanceService
from app.services.onec_outbound_service import OneCOutboundService
from app.services.gift_certificate_email_service import GiftCertificateEmailService, load_smtp_settings


router = APIRouter()
REFERRAL_CLIENT_CUSTOMER_GROUP_KEY = os.getenv(
    "ONEC_REFERRAL_CLIENT_CUSTOMER_GROUP_KEY",
    "bca461ae-7396-11f1-876b-fa163e4cc04e",
)
REFERRAL_MEDIA_DIR = Path(__file__).resolve().parents[2] / "static" / "referral_media"
REFERRAL_MEDIA_INDEX = REFERRAL_MEDIA_DIR / "materials.json"
REFERRAL_MEDIA_CATEGORIES = {"logos", "patterns", "phrases", "signs", "other"}
REWARD_STORE_MEDIA_DIR = Path(__file__).resolve().parents[2] / "static" / "reward_store"
REWARD_STORE_MEDIA_PUBLIC_PATH = "/static/reward_store"
GLM_AUDIT_JOURNAL_DIR = Path(__file__).resolve().parents[2] / "static" / "glm_audit_journal"
GLM_AUDIT_JOURNAL_PUBLIC_PATH = "/static/glm_audit_journal"
PROJECT_ROOT_DIR = Path(__file__).resolve().parents[3]
GLM_TON_TESTNET_ARTIFACT = PROJECT_ROOT_DIR / "contracts" / "ton" / "glm-jetton" / "glm-jetton.testnet.json"
GLM_TON_REFERENCE_LOCK = PROJECT_ROOT_DIR / "contracts" / "ton" / "glm-jetton" / "reference.jetton-contract.lock.json"
logger = logging.getLogger(__name__)
SUPPORT_ADMIN_URL = os.getenv("TELEGRAM_ADMIN_PORTAL_URL", "https://portal.glamejewelry.ru/admin/referrals")
SUPPORT_TICKET_PREFIX = "GLSUP"


def _glm_operational_stats_start_at() -> datetime | None:
    raw = (os.getenv("TON_GLM_OPERATIONAL_STATS_START_AT") or "").strip()
    if not raw:
        return None
    try:
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        value = datetime.fromisoformat(normalized)
    except ValueError:
        logger.warning("Invalid TON_GLM_OPERATIONAL_STATS_START_AT=%s", raw)
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _glm_operational_network() -> str:
    return (os.getenv("TON_NETWORK", "testnet") or "testnet").strip() or "testnet"


def _glm_tx_meta_network(meta: Any) -> str | None:
    if not isinstance(meta, dict):
        return None
    value = meta.get("ton_network") or meta.get("network")
    return str(value).strip().lower() if value else None


def _normalize_ton_tx_hash(value: Any) -> str:
    return str(value or "").strip()


def _collect_meta_ton_hashes(meta: Any) -> list[tuple[str, str]]:
    if not isinstance(meta, dict):
        return []
    auto_transfer = meta.get("ton_auto_transfer") if isinstance(meta.get("ton_auto_transfer"), dict) else {}
    items = [
        ("meta.tx_hash", meta.get("tx_hash")),
        ("meta.operator_tx_hash", meta.get("operator_tx_hash")),
        ("meta.deposit_tx_hash", meta.get("deposit_tx_hash")),
        ("meta.ton_tx_hash", meta.get("ton_tx_hash")),
        ("meta.ton_refund_tx_hash", meta.get("ton_refund_tx_hash")),
        ("meta.ton_auto_transfer.tx_hash", auto_transfer.get("tx_hash")),
    ]
    return [(field, tx_hash) for field, raw in items if (tx_hash := _normalize_ton_tx_hash(raw))]


async def _glm_replay_idempotency_audit_payload(db: AsyncSession) -> dict[str, Any]:
    bridge_operations = (
        await db.execute(
            select(GlameTokenBridgeOperation)
            .where(GlameTokenBridgeOperation.token_code == "GLM")
            .order_by(desc(GlameTokenBridgeOperation.created_at))
        )
    ).scalars().all()
    operations_by_transaction_id = {
        str(operation.transaction_id): str(operation.id)
        for operation in bridge_operations
        if operation.transaction_id
    }
    tx_hash_sources: dict[str, list[dict[str, Any]]] = {}

    def add_hash_source(tx_hash: str, source: dict[str, Any]) -> None:
        normalized = _normalize_ton_tx_hash(tx_hash)
        if not normalized:
            return
        tx_hash_sources.setdefault(normalized, []).append(source)

    for operation in bridge_operations:
        add_hash_source(
            str(operation.ton_tx_hash or ""),
            {
                "entity_key": f"bridge_operation:{operation.id}",
                "kind": "bridge_operation",
                "id": str(operation.id),
                "transaction_id": str(operation.transaction_id),
                "direction": operation.direction,
                "status": operation.status,
                "field": "ton_tx_hash",
            },
        )

    transactions = (
        await db.execute(
            select(GlameTokenTransaction)
            .where(
                GlameTokenTransaction.token_code == "GLM",
                GlameTokenTransaction.transaction_type.in_(("claim", "bridge", "redemption")),
            )
            .order_by(desc(GlameTokenTransaction.created_at))
        )
    ).scalars().all()
    for tx in transactions:
        meta = tx.meta if isinstance(tx.meta, dict) else {}
        entity_key = (
            f"bridge_operation:{operations_by_transaction_id[str(tx.id)]}"
            if str(tx.id) in operations_by_transaction_id
            else f"transaction:{tx.id}"
        )
        for field, tx_hash in _collect_meta_ton_hashes(meta):
            add_hash_source(
                tx_hash,
                {
                    "entity_key": entity_key,
                    "kind": "transaction",
                    "id": str(tx.id),
                    "transaction_type": tx.transaction_type,
                    "status": tx.status,
                    "reason": tx.reason,
                    "field": field,
                },
            )

    duplicate_hash_issues = []
    for tx_hash, sources in tx_hash_sources.items():
        distinct_entities = sorted({str(source.get("entity_key")) for source in sources})
        if len(distinct_entities) <= 1:
            continue
        duplicate_hash_issues.append({
            "code": "duplicate_ton_tx_hash",
            "severity": "critical",
            "tx_hash": tx_hash,
            "entities": distinct_entities,
            "sources": sources[:10],
        })

    processed_without_ton: list[dict[str, Any]] = []
    for operation in bridge_operations:
        if operation.status != "processed":
            continue
        if _normalize_ton_tx_hash(operation.ton_tx_hash):
            continue
        if str(operation.ton_status or "").lower() in {"legacy_manual", "manual_reviewed"}:
            continue
        processed_without_ton.append({
            "code": "bridge_processed_without_ton_tx",
            "severity": "critical",
            "operation_id": str(operation.id),
            "transaction_id": str(operation.transaction_id),
            "direction": operation.direction,
            "status": operation.status,
            "ton_status": operation.ton_status,
            "glm_amount": int(operation.glm_amount or 0),
        })

    store_payment_issues: list[dict[str, Any]] = []
    refund_issues: list[dict[str, Any]] = []
    for tx in transactions:
        if tx.transaction_type != "redemption":
            continue
        meta = tx.meta if isinstance(tx.meta, dict) else {}
        payment_method = str(meta.get("payment_method") or "")
        if tx.reason == "glm_store_item" and payment_method == "ton_glm" and tx.status in {"pending_fulfillment", "fulfilled"}:
            if not (_normalize_ton_tx_hash(meta.get("deposit_tx_hash")) or _normalize_ton_tx_hash(meta.get("tx_hash"))):
                store_payment_issues.append({
                    "code": "store_paid_without_ton_tx",
                    "severity": "critical",
                    "transaction_id": str(tx.id),
                    "status": tx.status,
                    "amount_glm": abs(int(tx.amount or 0)),
                })
        refund_status = str(meta.get("ton_refund_status") or "")
        if refund_status in {"sent", "verified", "settled"} and not _normalize_ton_tx_hash(meta.get("ton_refund_tx_hash")):
            refund_issues.append({
                "code": "refund_marked_sent_without_ton_tx",
                "severity": "critical",
                "transaction_id": str(tx.id),
                "status": tx.status,
                "refund_status": refund_status,
                "amount_glm": abs(int(tx.amount or 0)),
            })

    issues = duplicate_hash_issues + processed_without_ton + store_payment_issues + refund_issues
    checks = [
        {
            "code": "ton_tx_hash_uniqueness",
            "status": "ok" if not duplicate_hash_issues else "failed",
            "message": f"{len(duplicate_hash_issues)} duplicated TON tx hash groups across bridge/store/refund.",
        },
        {
            "code": "processed_bridge_has_ton_tx",
            "status": "ok" if not processed_without_ton else "failed",
            "message": f"{len(processed_without_ton)} processed bridge operations do not have TON tx hash.",
        },
        {
            "code": "store_paid_has_ton_tx",
            "status": "ok" if not store_payment_issues else "failed",
            "message": f"{len(store_payment_issues)} GLM Store paid orders do not have TON tx hash.",
        },
        {
            "code": "refund_sent_has_ton_tx",
            "status": "ok" if not refund_issues else "failed",
            "message": f"{len(refund_issues)} TON refunds marked sent/verified without TON tx hash.",
        },
    ]
    return {
        "schema": "glame_replay_idempotency_audit_v1",
        "status": "ok" if not issues else "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checked": {
            "bridge_operations": len(bridge_operations),
            "transactions": len(transactions),
            "ton_tx_hashes": len(tx_hash_sources),
        },
        "checks": checks,
        "issues_count": len(issues),
        "issues": issues[:50],
    }


class ReferralMemberResponse(BaseModel):
    id: str
    user_id: str
    status: str
    reward_mode: str
    program_level: str
    rate_percent: float
    cash_eligible: bool
    cash_status: str
    onec_counterparty_id: str | None = None
    onec_agency_contract_id: str | None = None
    onec_sync_status: str | None = None
    crypto_wallet: dict[str, Any] | None = None


class ReferralCodeResponse(BaseModel):
    id: str
    code: str
    status: str
    referral_url: str


class AdminPosReferralAttachRequest(BaseModel):
    phone: str
    code: str
    full_name: str | None = None


class AdminPosReferralAttachResponse(BaseModel):
    status: str
    message: str
    attribution_id: str
    user_id: str
    phone: str
    code: str
    welcome_points: int
    onec_sync_status: str | None = None
    onec_sync_job_id: str | None = None


class CashUpgradeStatus(BaseModel):
    eligible: bool
    active_referrals: int
    referral_revenue: int
    annual_referral_turnover: int
    current_level: dict[str, Any]
    levels: list[dict[str, Any]]
    thresholds: dict[str, Any]
    reason: str


class ReferralDashboardResponse(BaseModel):
    member: ReferralMemberResponse
    referral_code: ReferralCodeResponse
    profile: dict[str, Any]
    summary: dict[str, int]
    token: dict[str, Any]
    cash_upgrade: CashUpgradeStatus
    rate_promotion: dict[str, Any] | None = None
    referrals: list[dict[str, Any]] = []
    commissions: list[dict[str, Any]] = []
    payouts: list[dict[str, Any]] = []
    glm_transactions: list[dict[str, Any]] = []


class ReferralRegisterRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    full_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=120)
    first_name: str | None = Field(default=None, max_length=120)
    middle_name: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=6, max_length=128)
    email: str = Field(min_length=3, max_length=255)
    offer_accepted: bool = False


class ReferralRegisterResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    dashboard: ReferralDashboardResponse


class ValidateCodeRequest(BaseModel):
    code: str = Field(min_length=2, max_length=32)


class ValidateCodeResponse(BaseModel):
    valid: bool
    code: str | None = None
    partner_name: str | None = None
    reward_hint: str | None = None


class CreateAttributionRequest(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    referee_user_id: UUID | None = None
    referee_phone_hash: str | None = None
    source: str = "web"
    meta: dict[str, Any] | None = None


class AttributionResponse(BaseModel):
    id: str
    status: str
    source: str
    created_at: str | None = None


class CashUpgradeRequest(BaseModel):
    legal_status: str = Field(pattern="^(self_employed|ip)$")
    inn: str = Field(min_length=10, max_length=32)
    passport_data: dict[str, Any] | None = None
    payout_details: dict[str, Any] | None = None


class CashUpgradeRequestResponse(BaseModel):
    id: str
    status: str
    onec_sync_status: str | None = None


class CryptoWalletBindRequest(BaseModel):
    network: str = Field(default="ton", pattern="^(ton)$")
    address: str = Field(min_length=32, max_length=128)
    label: str | None = Field(default=None, max_length=80)


class CryptoWalletBindResponse(BaseModel):
    status: str
    crypto_wallet: dict[str, Any]


class CryptoWalletChallengeResponse(BaseModel):
    status: str
    payload: str
    expires_at: str


class CryptoWalletTonProofRequest(BaseModel):
    network: str = Field(default="ton", pattern="^(ton)$")
    address: str = Field(min_length=32, max_length=128)
    public_key: str = Field(min_length=64, max_length=64)
    wallet_state_init: str = Field(min_length=16, max_length=20000)
    proof: dict[str, Any]
    wallet_app: str | None = Field(default=None, max_length=80)


class GlmClaimResponse(BaseModel):
    status: str
    claim: dict[str, Any]
    token: dict[str, Any]


class GlmStoreRedeemRequest(BaseModel):
    sku: str = Field(min_length=2, max_length=120)
    delivery_note: str | None = Field(default=None, max_length=500)


class RewardStoreItemPayload(BaseModel):
    sku: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    category: str = Field(default="branded_goods", max_length=64)
    inventory_status: str = Field(default="pilot_batch", max_length=64)
    status: str = Field(default="available", pattern="^(available|draft|limited|sold_out|archived)$")
    price_glm: int | None = Field(default=None, ge=0, le=100000000)
    price_points: int | None = Field(default=None, ge=0, le=100000000)
    quantity_available: int | None = Field(default=None, ge=0, le=1000000)
    image_url: str | None = Field(default=None, max_length=1000)
    sort_order: int = Field(default=100, ge=0, le=1000000)
    is_active: bool = True
    meta: dict[str, Any] | None = None


class RewardStoreItemPatch(BaseModel):
    sku: str | None = Field(default=None, min_length=2, max_length=120)
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=64)
    inventory_status: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, pattern="^(available|draft|limited|sold_out|archived)$")
    price_glm: int | None = Field(default=None, ge=0, le=100000000)
    price_points: int | None = Field(default=None, ge=0, le=100000000)
    quantity_available: int | None = Field(default=None, ge=0, le=1000000)
    image_url: str | None = Field(default=None, max_length=1000)
    sort_order: int | None = Field(default=None, ge=0, le=1000000)
    is_active: bool | None = None
    meta: dict[str, Any] | None = None


class GlmBonusConvertRequest(BaseModel):
    points: int = Field(ge=1, le=100000)


class GlmToPointsBridgeRequest(BaseModel):
    amount: int = Field(ge=1, le=100000)
    target_points: int | None = Field(default=None, ge=1, le=100000)
    note: str | None = Field(default=None, max_length=500)


class BuyLoyaltyPointsRequest(BaseModel):
    points: int = Field(ge=1, le=100000)
    note: str | None = Field(default=None, max_length=500)


class BuyGlmWithTonRequest(BaseModel):
    amount_glm: int = Field(ge=1, le=100000)
    note: str | None = Field(default=None, max_length=500)


class SellGlmForTonRequest(BaseModel):
    amount_glm: int = Field(ge=1, le=100000)
    note: str | None = Field(default=None, max_length=500)


class AdminGlmTonSettlementRequest(BaseModel):
    tx_hash: str = Field(min_length=16, max_length=256)
    comment: str | None = Field(default=None, max_length=500)
    require_verified: bool = True


class AdminGlmExchangeDeskUpdateRequest(BaseModel):
    status: str = Field(pattern="^(processed|canceled|failed)$")
    payout_tx_hash: str | None = Field(default=None, min_length=16, max_length=256)
    comment: str | None = Field(default=None, max_length=500)


class AdminGlmTonSettlementRunRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=300)
    require_verified: bool = True


class AdminGlmTonAutoTransferRunRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


class AdminGlmTonAutoTransferOverrideRequest(BaseModel):
    enabled: bool
    reason: str | None = Field(default=None, max_length=500)


class AdminGlmProductionSignerEmergencyPauseRequest(BaseModel):
    paused: bool
    reason: str | None = Field(default=None, max_length=500)


class AdminGlmProductionApprovalsRequest(BaseModel):
    legal_approved: bool = False
    security_approved: bool = False
    treasury_approved: bool = False
    comment: str | None = Field(default=None, max_length=1000)
    legal_evidence_ref: str | None = Field(default=None, max_length=1000)
    security_evidence_ref: str | None = Field(default=None, max_length=1000)
    treasury_evidence_ref: str | None = Field(default=None, max_length=1000)
    public_wording_evidence_ref: str | None = Field(default=None, max_length=1000)


class AdminGlmHotWalletLimitsRequest(BaseModel):
    hot_wallet_refill_glm_threshold: Decimal = Field(ge=0, le=10_000_000)
    hot_wallet_refill_ton_threshold: Decimal = Field(ge=0, le=100)
    hot_wallet_refill_glm_target: Decimal = Field(ge=0, le=10_000_000)
    hot_wallet_refill_ton_target: Decimal = Field(ge=0, le=100)


class AdminGlmHotWalletRefillRecordRequest(BaseModel):
    manual_glm_amount: Decimal = Field(default=0, ge=0, le=10_000_000)
    manual_ton_amount: Decimal = Field(default=0, ge=0, le=100)
    ton_tx_hash: str | None = Field(default=None, max_length=160)
    comment: str | None = Field(default=None, max_length=500)


class AdminGlmHotWalletRefillApprovalRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=500)


class AdminGlmHotWalletRefillApprovalDecisionRequest(BaseModel):
    approved: bool
    comment: str | None = Field(default=None, max_length=500)


class BonusExpiryDraftRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=365)
    limit: int = Field(default=100, ge=1, le=300)


class ManualReferralSyncResponse(BaseModel):
    status: str
    code: str
    total_loaded: int
    matched: int
    created: int
    updated: int
    errors: int
    message: str


class AdminPartnerUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(active|blocked|paused)$")
    reward_mode: str | None = Field(default=None, pattern="^(points|cash)$")
    cash_status: str | None = Field(default=None, pattern="^(unavailable|eligible|pending|approved|rejected)$")
    program_level: str | None = None
    points_rate_percent: float | None = Field(default=None, ge=0, le=100)
    cash_rate_percent: float | None = Field(default=None, ge=0, le=100)
    onec_agency_contract_id: str | None = None
    block_reason: str | None = None


class AdminPayoutCreateRequest(BaseModel):
    amount_kopecks: int = Field(gt=0)
    period_start: datetime | None = None
    period_end: datetime | None = None
    status: str = Field(default="pending", pattern="^(pending|approved|paid|canceled)$")
    onec_payment_document_id: str | None = None
    comment: str | None = None


class AdminPayoutStatusRequest(BaseModel):
    status: str = Field(pattern="^(pending|approved|paid|canceled)$")
    onec_payment_document_id: str | None = None
    comment: str | None = None


class AdminGlmClaimRequest(BaseModel):
    enabled: bool = True
    comment: str | None = Field(default=None, max_length=500)


class AdminGlmReleaseRequest(BaseModel):
    amount: int | None = Field(default=None, gt=0)
    reason: str | None = Field(default="admin_release", max_length=120)


class AdminGlmReleaseDueRequest(BaseModel):
    limit: int = Field(default=500, ge=1, le=2000)


class AdminGlmAdjustmentRequest(BaseModel):
    amount: int = Field(gt=0)
    direction: str = Field(pattern="^(credit|debit)$")
    reason: str = Field(min_length=5, max_length=100)
    comment: str | None = Field(default=None, max_length=500)


class AdminCommissionCancelRequest(BaseModel):
    reason: str = Field(default="order_return_or_cancel", min_length=5, max_length=100)
    comment: str | None = Field(default=None, max_length=500)


class AdminGlmRefundAutoApplyRequest(BaseModel):
    dry_run: bool = True
    limit: int = Field(default=50, ge=1, le=200)
    comment: str | None = Field(default=None, max_length=500)


class AdminGlmClaimStatusRequest(BaseModel):
    status: str = Field(pattern="^(processed|failed|canceled)$")
    tx_hash: str | None = Field(default=None, max_length=255)
    comment: str | None = Field(default=None, max_length=500)


class AdminGlmRedemptionStatusRequest(BaseModel):
    status: str = Field(pattern="^(fulfilled|failed|canceled)$")
    comment: str | None = Field(default=None, max_length=500)


class AdminGlmRedemptionTonRefundRecordRequest(BaseModel):
    tx_hash: str | None = Field(default=None, max_length=255)
    comment: str | None = Field(default=None, max_length=500)


class AdminGlmRedemptionTonRefundSettlementRequest(BaseModel):
    tx_hash: str = Field(min_length=4, max_length=255)
    comment: str | None = Field(default=None, max_length=500)
    require_verified: bool = True


class AdminGlmToPointsBridgeStatusRequest(BaseModel):
    status: str = Field(pattern="^(processed|failed|canceled)$")
    points: int | None = Field(default=None, ge=1, le=100000)
    onec_document_id: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=500)


class AdminGlmBridgeRepairRequest(BaseModel):
    action: str = Field(pattern="^(retry_onec|record_manual_document|mark_reviewed)$")
    onec_document_id: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=500)


class AdminPointsToGlmSpendRepairRequest(BaseModel):
    action: str = Field(pattern="^(retry_onec_spend|record_manual_spend_document|mark_reviewed)$")
    onec_document_id: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=500)


class AdminGlmBridgeIssueActionRequest(BaseModel):
    action: str = Field(pattern="^(settle_ton_transfer|cancel_onec_spend|mark_legacy_manual|mark_reviewed)$")
    issue_code: str | None = Field(default=None, max_length=120)
    tx_hash: str | None = Field(default=None, max_length=256)
    comment: str | None = Field(default=None, max_length=500)


class AdminTelegramNotificationTestRequest(BaseModel):
    message: str | None = Field(default=None, max_length=1000)


class AdminTelegramBroadcastRequest(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=3, max_length=3000)
    audience: str = Field(default="active_connected", pattern="^(active_connected|all_connected)$")
    dry_run: bool = False


class AdminTelegramAlertsRunRequest(BaseModel):
    force: bool = False


class PartnerTelegramBindRequest(BaseModel):
    chat_id: str = Field(min_length=3, max_length=64)


class PartnerTelegramPreferencesRequest(BaseModel):
    notifications_enabled: bool | None = None
    partner_updates: bool | None = None
    referrals: bool | None = None
    crypto: bool | None = None
    marketing: bool | None = None


class TelegramWebhookUpdate(BaseModel):
    update_id: int | None = None
    message: dict[str, Any] | None = None


class PartnerSupportMessageRequest(BaseModel):
    subject: str | None = Field(default=None, max_length=120)
    message: str = Field(min_length=3, max_length=2000)
    category: str | None = Field(default="partner", max_length=32)


class PublicSupportMessageRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    contact: str | None = Field(default=None, max_length=255)
    subject: str | None = Field(default=None, max_length=120)
    message: str = Field(min_length=3, max_length=2000)
    page: str | None = Field(default="glm", max_length=32)


class AdminGlmAuditHashGenerateRequest(BaseModel):
    audit_date: date | None = None


class AdminGlmAuditHashPublishRequest(BaseModel):
    audit_date: date | None = None


class AdminCashReviewRequest(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")
    review_comment: str | None = None
    onec_agency_contract_id: str | None = None


class ReferralMediaMaterialResponse(BaseModel):
    id: str
    title: str
    category: str
    description: str | None = None
    file_url: str
    preview_url: str | None = None
    file_name: str
    original_file_name: str
    content_type: str | None = None
    size: int = 0
    is_active: bool = True
    sort_order: int = 100
    created_at: str | None = None
    updated_at: str | None = None


class ReferralMediaMaterialUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)


class ReferralRatePromotionResponse(BaseModel):
    id: str
    title: str
    rate_percent: float
    starts_at: str
    ends_at: str
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    status: str = "scheduled"


class ReferralRatePromotionCreateRequest(BaseModel):
    title: str = Field(default="Акция по баллам", max_length=255)
    rate_percent: float = Field(ge=0, le=100)
    starts_at: datetime
    ends_at: datetime
    is_active: bool = True


class ReferralRatePromotionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    rate_percent: float | None = Field(default=None, ge=0, le=100)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None


def _ensure_media_dir() -> None:
    REFERRAL_MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def _media_public_url(file_name: str) -> str:
    return f"/static/referral_media/{file_name}"


def _media_preview_url(file_name: str | None) -> str | None:
    return f"/static/referral_media/{file_name}" if file_name else None


def _ensure_reward_store_media_dir() -> None:
    REWARD_STORE_MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def _reward_store_media_public_url(file_name: str) -> str:
    return f"{REWARD_STORE_MEDIA_PUBLIC_PATH}/{file_name}"


def _media_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    return (
        int(item.get("sort_order") or 100),
        str(item.get("category") or "other"),
        str(item.get("title") or ""),
    )


def _read_media_materials() -> list[dict[str, Any]]:
    _ensure_media_dir()
    if not REFERRAL_MEDIA_INDEX.exists():
        return []
    try:
        data = json.loads(REFERRAL_MEDIA_INDEX.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    materials: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict) and item.get("id") and item.get("file_name"):
            item["file_url"] = _media_public_url(str(item["file_name"]))
            item["preview_url"] = _media_preview_url(item.get("preview_file_name"))
            materials.append(item)
    return sorted(materials, key=_media_sort_key)


def _write_media_materials(materials: list[dict[str, Any]]) -> None:
    _ensure_media_dir()
    normalized = sorted(materials, key=_media_sort_key)
    REFERRAL_MEDIA_INDEX.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_media_filename(name: str) -> str:
    raw = Path(name or "material").name
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(raw).stem).strip("._") or "material"
    suffix = re.sub(r"[^A-Za-z0-9.]+", "", Path(raw).suffix.lower())[:16]
    return f"{uuid4().hex[:10]}_{stem[:80]}{suffix}"


def _create_pdf_preview(pdf_path: Path) -> str | None:
    try:
        import pypdfium2 as pdfium

        preview_name = f"{pdf_path.stem}_preview.png"
        preview_path = pdf_path.with_name(preview_name)
        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            if len(pdf) < 1:
                return None
            page = pdf[0]
            bitmap = page.render(scale=1.6)
            image = bitmap.to_pil()
            image.thumbnail((1200, 900))
            image.save(preview_path, "PNG", optimize=True)
            return preview_name
        finally:
            pdf.close()
    except Exception as error:
        logger.warning("Не удалось создать превью PDF %s: %s", pdf_path, error)
        return None


def _normalize_media_category(value: str | None) -> str:
    category = (value or "other").strip().lower()
    return category if category in REFERRAL_MEDIA_CATEGORIES else "other"


def _media_response(item: dict[str, Any]) -> ReferralMediaMaterialResponse:
    payload = dict(item)
    payload["file_url"] = _media_public_url(str(payload.get("file_name") or ""))
    payload["preview_url"] = _media_preview_url(payload.get("preview_file_name"))
    return ReferralMediaMaterialResponse(**payload)


def _rate_promotion_status(item: dict[str, Any]) -> str:
    if not item.get("is_active", True):
        return "paused"
    now = datetime.now(timezone.utc)
    start = ReferralService._parse_promotion_datetime(item.get("starts_at"))
    end = ReferralService._parse_promotion_datetime(item.get("ends_at"))
    if start is None or end is None:
        return "invalid"
    if now < start:
        return "scheduled"
    if now >= end:
        return "finished"
    return "active"


def _rate_promotion_response(item: dict[str, Any]) -> ReferralRatePromotionResponse:
    payload = dict(item)
    payload["status"] = _rate_promotion_status(payload)
    return ReferralRatePromotionResponse(**payload)


def _public_rate_promotion_payload() -> dict[str, Any] | None:
    promotions = ReferralService.list_rate_promotions()
    active = ReferralService.active_points_rate_promotion()
    if active:
        payload = dict(active)
        payload["status"] = "active"
        return payload
    now = datetime.now(timezone.utc)
    scheduled: list[dict[str, Any]] = []
    for item in promotions:
        start = ReferralService._parse_promotion_datetime(item.get("starts_at"))
        if item.get("is_active", True) and start is not None and start > now:
            scheduled.append(item)
    if not scheduled:
        return None
    next_item = sorted(scheduled, key=lambda item: str(item.get("starts_at") or ""))[0]
    payload = dict(next_item)
    payload["status"] = "scheduled"
    return payload


def _member_response(member: ReferralProgramMember) -> ReferralMemberResponse:
    meta = member.meta or {}
    crypto_wallet = meta.get("crypto_wallet") if isinstance(meta, dict) else None
    return ReferralMemberResponse(
        id=str(member.id),
        user_id=str(member.user_id),
        status=member.status,
        reward_mode=member.reward_mode,
        program_level=member.program_level,
        rate_percent=float(member.cash_rate_percent if member.reward_mode == "cash" else member.points_rate_percent or 0),
        cash_eligible=bool(member.cash_eligible),
        cash_status=member.cash_status,
        onec_counterparty_id=member.onec_counterparty_id,
        onec_agency_contract_id=member.onec_agency_contract_id,
        onec_sync_status=member.onec_sync_status,
        crypto_wallet=crypto_wallet if isinstance(crypto_wallet, dict) else None,
    )


def _code_response(code: ReferralCode) -> ReferralCodeResponse:
    return ReferralCodeResponse(
        id=str(code.id),
        code=code.code,
        status=code.status,
        referral_url=f"https://partner.glamejewelry.ru/r/{code.code}",
    )


def _level_payload(level: dict[str, Any]) -> dict[str, Any]:
    payload = dict(level)
    if "rate_percent" in payload:
        payload["rate_percent"] = float(payload["rate_percent"])
    return payload


async def _ensure_reward_store_table(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS reward_store_items (
                id UUID PRIMARY KEY,
                sku VARCHAR(120) NOT NULL UNIQUE,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                category VARCHAR(64) NOT NULL DEFAULT 'branded_goods',
                inventory_status VARCHAR(64) NOT NULL DEFAULT 'pilot_batch',
                status VARCHAR(32) NOT NULL DEFAULT 'available',
                price_glm INTEGER,
                price_points INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 100,
                is_active BOOLEAN NOT NULL DEFAULT true,
                meta JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_reward_store_items_sku ON reward_store_items (sku)"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_reward_store_items_status ON reward_store_items (status)"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_reward_store_items_is_active ON reward_store_items (is_active)"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_reward_store_items_active_sort ON reward_store_items (is_active, sort_order, created_at)"))


def _reward_store_item_payload(item: RewardStoreItem) -> dict[str, Any]:
    meta = item.meta if isinstance(item.meta, dict) else {}
    quantity_available = meta.get("quantity_available")
    try:
        quantity_available = int(quantity_available) if quantity_available is not None and str(quantity_available).strip() != "" else None
    except (TypeError, ValueError):
        quantity_available = None
    image_url = str(meta.get("image_url") or "").strip() or None
    return {
        "id": str(item.id),
        "sku": item.sku,
        "title": item.title,
        "description": item.description or "",
        "category": item.category,
        "inventory_status": item.inventory_status,
        "status": item.status,
        "price_glm": int(item.price_glm or 0) if item.price_glm is not None else None,
        "price_points": int(item.price_points or 0) if item.price_points is not None else None,
        "quantity_available": quantity_available,
        "image_url": image_url,
        "sort_order": int(item.sort_order or 0),
        "is_active": bool(item.is_active),
        "meta": meta,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _reward_store_meta_from_payload(payload: RewardStoreItemPayload | RewardStoreItemPatch, base: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = dict(base or {})
    data = payload.model_dump(exclude_unset=True)
    incoming_meta = data.get("meta")
    if isinstance(incoming_meta, dict):
        meta.update(incoming_meta)
    if "quantity_available" in data:
        meta["quantity_available"] = data.get("quantity_available")
    if "image_url" in data:
        image_url = str(data.get("image_url") or "").strip()
        if image_url:
            meta["image_url"] = image_url
        else:
            meta.pop("image_url", None)
    return meta


async def _reward_store_items_for_portal(db: AsyncSession) -> list[dict[str, Any]]:
    await _ensure_reward_store_table(db)
    rows = (
        await db.execute(
            select(RewardStoreItem)
            .where(
                RewardStoreItem.is_active == True,
                RewardStoreItem.status.in_(["available", "limited"]),
            )
            .order_by(RewardStoreItem.sort_order.asc(), RewardStoreItem.created_at.asc())
        )
    ).scalars().all()
    return [_reward_store_item_payload(row) for row in rows]


async def _recent_referrals(db: AsyncSession, member_id: UUID, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(ReferralAttribution, User)
            .outerjoin(User, User.id == ReferralAttribution.referee_user_id)
            .where(ReferralAttribution.referrer_member_id == member_id)
            .order_by(desc(ReferralAttribution.created_at))
            .limit(limit)
        )
    ).all()
    result: list[dict[str, Any]] = []
    for attribution, user in rows:
        stats = (
            await db.execute(
                select(
                    func.count(ReferralCommission.id),
                    func.coalesce(func.sum(ReferralCommission.commission_base), 0),
                    func.coalesce(func.sum(ReferralCommission.amount_kopecks), 0),
                    func.coalesce(func.sum(ReferralCommission.points), 0),
                ).where(ReferralCommission.attribution_id == attribution.id)
            )
        ).one()
        result.append(
            {
                "id": str(attribution.id),
                "name": getattr(user, "full_name", None) or "Клиент GLAME",
                "phone": _mask_phone(getattr(user, "phone", None)),
                "source": attribution.source,
                "status": attribution.status,
                "purchases": int(stats[0] or 0),
                "spent": int(stats[1] or 0),
                "reward_amount": int(stats[2] or 0),
                "reward_points": int(stats[3] or 0),
                "created_at": attribution.created_at.isoformat() if attribution.created_at else None,
                "activated_at": attribution.activated_at.isoformat() if attribution.activated_at else None,
            }
        )
    return result


async def _recent_commissions(db: AsyncSession, member_id: UUID, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(ReferralCommission)
            .where(
                ReferralCommission.referrer_member_id == member_id,
                or_(
                    ReferralCommission.commission_base > 100,
                    ReferralCommission.points > 0,
                    ReferralCommission.amount_kopecks >= 100,
                ),
            )
            .order_by(desc(ReferralCommission.created_at))
            .limit(limit)
        )
    ).scalars().all()
    token_service = GlameTokenService(db)
    result: list[dict[str, Any]] = []
    for row in rows:
        glm = await token_service.commission_glm_payload(row.id)
        result.append(
            {
            "id": str(row.id),
            "date": row.created_at.isoformat() if row.created_at else None,
            "hold_until": row.hold_until.isoformat() if row.hold_until else None,
            "base": row.commission_base,
            "rate": float(row.rate_percent or 0),
            "amount": row.amount_kopecks,
            "points": row.points,
            "reward_mode": row.reward_mode,
            "status": row.status,
            "onec_document_id": row.onec_document_id,
            "onec_sync_status": row.onec_sync_status,
            "glm": glm,
        }
        )
    return result


async def _recent_payouts(db: AsyncSession, member_id: UUID, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(ReferralPayout)
            .where(ReferralPayout.member_id == member_id)
            .order_by(desc(ReferralPayout.created_at))
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(row.id),
            "period_start": row.period_start.isoformat() if row.period_start else None,
            "period_end": row.period_end.isoformat() if row.period_end else None,
            "amount": row.amount_kopecks,
            "status": row.status,
            "onec_payment_document_id": row.onec_payment_document_id,
            "requested_at": row.requested_at.isoformat() if row.requested_at else None,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "paid_at": row.paid_at.isoformat() if row.paid_at else None,
        }
        for row in rows
    ]


async def _recent_glm_transactions(db: AsyncSession, member: ReferralProgramMember, limit: int = 50) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(GlameTokenTransaction)
            .where(
                GlameTokenTransaction.referral_member_id == member.id,
                GlameTokenTransaction.token_code == "GLM",
                GlameTokenTransaction.status != "superseded",
            )
            .order_by(desc(GlameTokenTransaction.created_at))
            .limit(limit)
        )
    ).scalars().all()
    platform_rows = [_glm_transaction_payload(row) for row in rows]
    platform_hashes = {
        str(row.get("tx_hash") or row.get("deposit_tx_hash") or "").strip()
        for row in platform_rows
        if str(row.get("tx_hash") or row.get("deposit_tx_hash") or "").strip()
    }
    wallet = _crypto_wallet_meta(member) or {}
    onchain_rows: list[dict[str, Any]] = []
    if wallet.get("address"):
        try:
            onchain_rows = await GlameTokenService(db).ton_wallet_glm_transactions(wallet.get("address"), limit=limit)
        except Exception:
            onchain_rows = []
    rows_payload = [
        *platform_rows,
        *[row for row in onchain_rows if str(row.get("tx_hash") or "").strip() not in platform_hashes],
    ]
    return sorted(rows_payload, key=lambda item: item.get("created_at") or "", reverse=True)[:limit]


def _glm_claim_payload(
    tx: GlameTokenTransaction,
    member: ReferralProgramMember | None = None,
    user: User | None = None,
    operation: GlameTokenBridgeOperation | None = None,
) -> dict[str, Any]:
    meta = tx.meta if isinstance(tx.meta, dict) else {}
    return {
        "id": str(tx.id),
        "bridge_operation_id": str(operation.id) if operation else None,
        "member_id": str(tx.referral_member_id) if tx.referral_member_id else (str(member.id) if member else None),
        "partner_name": getattr(user, "full_name", None) or "Партнер GLAME",
        "partner_phone": getattr(user, "phone", None),
        "amount": int(tx.amount or 0),
        "status": tx.status,
        "wallet_address": meta.get("wallet_address"),
        "wallet_app": meta.get("wallet_app"),
        "tx_hash": meta.get("tx_hash"),
        "admin_comment": meta.get("admin_comment"),
        "sku": meta.get("sku"),
        "item_title": (meta.get("item") or {}).get("title") if isinstance(meta.get("item"), dict) else None,
        "fulfillment_status": meta.get("fulfillment_status"),
        "delivery_note": meta.get("delivery_note"),
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
        "processed_at": meta.get("processed_at"),
    }


def _glm_transaction_payload(
    tx: GlameTokenTransaction,
    member: ReferralProgramMember | None = None,
    user: User | None = None,
    operation: GlameTokenBridgeOperation | None = None,
) -> dict[str, Any]:
    meta = tx.meta if isinstance(tx.meta, dict) else {}
    return {
        "id": str(tx.id),
        "bridge_operation_id": str(operation.id) if operation else None,
        "member_id": str(tx.referral_member_id) if tx.referral_member_id else (str(member.id) if member else None),
        "partner_name": getattr(user, "full_name", None) or "Партнер GLAME",
        "partner_phone": getattr(user, "phone", None),
        "type": tx.transaction_type,
        "status": tx.status,
        "amount": int(tx.amount or 0),
        "balance_after": int(tx.balance_after or 0),
        "hold_balance_after": int(tx.hold_balance_after or 0),
        "reason": tx.reason,
        "source": tx.source,
        "source_id": tx.source_id,
        "description": tx.description,
        "available_at": tx.available_at.isoformat() if tx.available_at else None,
        "expires_at": tx.expires_at.isoformat() if tx.expires_at else None,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
        "tx_hash": meta.get("tx_hash"),
        "admin_comment": meta.get("admin_comment"),
        "bridge_type": meta.get("bridge_type"),
        "debit_source": meta.get("debit_source"),
        "expected_ton_sender_address": meta.get("expected_ton_sender_address"),
        "treasury_address": meta.get("treasury_address"),
        "deposit_tx_hash": meta.get("deposit_tx_hash"),
        "ton_deposit_verification": meta.get("ton_deposit_verification"),
        "ton_deposit_status": meta.get("ton_deposit_status"),
        "ton_deposit_requested_at": meta.get("ton_deposit_requested_at"),
        "ton_deposit_query_id": meta.get("ton_deposit_query_id"),
        "ton_deposit_last_lookup": meta.get("ton_deposit_last_lookup"),
        "rub_amount": meta.get("rub_amount"),
        "rub_per_glm": meta.get("rub_per_glm"),
        "ton_rub_rate": meta.get("ton_rub_rate"),
        "pricing_source": meta.get("pricing_source"),
        "pricing_checked_at": meta.get("pricing_checked_at"),
        "pricing_error": meta.get("pricing_error"),
        "ton_amount": meta.get("ton_amount"),
        "ton_amount_nanoton": meta.get("ton_amount_nanoton"),
        "ton_payment_status": meta.get("ton_payment_status"),
        "ton_payment_tx_hash": meta.get("ton_payment_tx_hash"),
        "ton_payment_requested_at": meta.get("ton_payment_requested_at"),
        "ton_payment_last_lookup": meta.get("ton_payment_last_lookup"),
        "ton_payment_verification": meta.get("ton_payment_verification"),
        "gram_payout_status": meta.get("gram_payout_status"),
        "target_points": meta.get("target_points"),
        "processed_points": meta.get("processed_points"),
        "onec_document_id": meta.get("onec_document_id"),
        "onec_sync_status": meta.get("onec_sync_status"),
        "onec_sync_error": meta.get("onec_sync_error"),
        "onec_request_payload": meta.get("onec_request_payload"),
        "refunded_glm": meta.get("refunded_glm"),
        "ton_refund_required": meta.get("ton_refund_required"),
        "ton_refund_status": meta.get("ton_refund_status"),
        "ton_refund_tx_hash": meta.get("ton_refund_tx_hash"),
        "ton_refund_submitted_at": meta.get("ton_refund_submitted_at"),
        "ton_refund_verified_at": meta.get("ton_refund_verified_at"),
        "ton_refund_verification": meta.get("ton_refund_verification"),
        "loyalty_points_expires_at": meta.get("loyalty_points_expires_at"),
        "loyalty_points_expires_days": meta.get("loyalty_points_expires_days"),
        "sku": meta.get("sku"),
        "item_title": (meta.get("item") or {}).get("title") if isinstance(meta.get("item"), dict) else None,
        "payment_method": meta.get("payment_method"),
        "price_glm": meta.get("price_glm"),
        "price_points": meta.get("price_points"),
        "refunded_points": meta.get("refunded_points"),
        "onec_spend_document_id": meta.get("onec_spend_document_id"),
        "onec_spend_sync_status": meta.get("onec_spend_sync_status"),
        "onec_spend_sync_error": meta.get("onec_spend_sync_error"),
        "fulfillment_status": meta.get("fulfillment_status"),
        "delivery_note": meta.get("delivery_note"),
    }


def _glm_bridge_operation_payload(
    operation: GlameTokenBridgeOperation,
    member: ReferralProgramMember | None = None,
    user: User | None = None,
) -> dict[str, Any]:
    return {
        "id": str(operation.id),
        "transaction_id": str(operation.transaction_id),
        "member_id": str(operation.referral_member_id) if operation.referral_member_id else (str(member.id) if member else None),
        "partner_name": getattr(user, "full_name", None) or "Партнер GLAME",
        "partner_phone": getattr(user, "phone", None),
        "direction": operation.direction,
        "status": operation.status,
        "idempotency_key": operation.idempotency_key,
        "points_amount": int(operation.points_amount or 0),
        "glm_amount": int(operation.glm_amount or 0),
        "ton_network": operation.ton_network,
        "ton_sender_address": operation.ton_sender_address,
        "ton_recipient_address": operation.ton_recipient_address,
        "ton_treasury_address": operation.ton_treasury_address,
        "ton_tx_hash": operation.ton_tx_hash,
        "ton_status": operation.ton_status,
        "onec_document_id": operation.onec_document_id,
        "onec_status": operation.onec_status,
        "onec_error": operation.onec_error,
        "source": operation.source,
        "source_id": operation.source_id,
        "requested_at": operation.requested_at.isoformat() if operation.requested_at else None,
        "processed_at": operation.processed_at.isoformat() if operation.processed_at else None,
        "created_at": operation.created_at.isoformat() if operation.created_at else None,
        "updated_at": operation.updated_at.isoformat() if operation.updated_at else None,
        "meta": operation.meta if isinstance(operation.meta, dict) else {},
    }


async def _get_glm_bridge_operation_or_404(
    db: AsyncSession,
    operation_id: UUID,
    *,
    direction: str | None = None,
) -> GlameTokenBridgeOperation:
    conditions = [
        GlameTokenBridgeOperation.id == operation_id,
        GlameTokenBridgeOperation.token_code == "GLM",
    ]
    if direction:
        conditions.append(GlameTokenBridgeOperation.direction == direction)
    operation = (
        await db.execute(select(GlameTokenBridgeOperation).where(*conditions))
    ).scalar_one_or_none()
    if operation is None:
        raise HTTPException(status_code=404, detail="GLM bridge operation не найдена")
    return operation


def _glm_daily_audit_hash_payload(row: GlameTokenDailyAuditHash) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "audit_date": row.audit_date.isoformat() if row.audit_date else None,
        "token_code": row.token_code,
        "root_hash": row.root_hash,
        "previous_root_hash": row.previous_root_hash,
        "transactions_count": int(row.transactions_count or 0),
        "accounts_count": int(row.accounts_count or 0),
        "balance_total": int(row.balance_total or 0),
        "hold_total": int(row.hold_total or 0),
        "lifetime_earned_total": int(row.lifetime_earned_total or 0),
        "lifetime_burned_total": int(row.lifetime_burned_total or 0),
        "public_status": row.public_status,
        "public_reference": row.public_reference,
        "payload": row.payload or {},
        "generated_by": str(row.generated_by) if row.generated_by else None,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _glm_public_audit_hash_payload(row: GlameTokenDailyAuditHash) -> dict[str, Any]:
    return GlameTokenService.public_daily_audit_hash_payload(row)


def _write_glm_audit_public_journal(rows: list[GlameTokenDailyAuditHash]) -> None:
    GlameTokenService.write_public_audit_journal(rows)


def _glm_ton_deployment_artifact() -> dict[str, Any]:
    if not GLM_TON_TESTNET_ARTIFACT.exists():
        return {"exists": False, "path": str(GLM_TON_TESTNET_ARTIFACT), "data": None}
    try:
        return {
            "exists": True,
            "path": str(GLM_TON_TESTNET_ARTIFACT),
            "data": json.loads(GLM_TON_TESTNET_ARTIFACT.read_text(encoding="utf-8")),
        }
    except Exception as error:
        return {
            "exists": True,
            "path": str(GLM_TON_TESTNET_ARTIFACT),
            "data": None,
            "error": str(error),
        }


def _glm_ton_reference_status() -> dict[str, Any]:
    if not GLM_TON_REFERENCE_LOCK.exists():
        return {"exists": False, "path": str(GLM_TON_REFERENCE_LOCK), "data": None}
    try:
        lock = json.loads(GLM_TON_REFERENCE_LOCK.read_text(encoding="utf-8"))
    except Exception as error:
        return {
            "exists": True,
            "path": str(GLM_TON_REFERENCE_LOCK),
            "data": None,
            "error": str(error),
        }

    expected_commit = str(lock.get("commit") or "")
    vendor_path_value = str(lock.get("vendor_path") or "")
    vendor_path = (GLM_TON_REFERENCE_LOCK.parent / vendor_path_value).resolve() if vendor_path_value else None
    status_payload: dict[str, Any] = {
        "exists": True,
        "path": str(GLM_TON_REFERENCE_LOCK),
        "data": lock,
        "vendor_path": str(vendor_path) if vendor_path else None,
        "vendor_exists": bool(vendor_path and vendor_path.exists()),
        "expected_commit": expected_commit,
    }
    if not re.fullmatch(r"[0-9a-fA-F]{40}", expected_commit):
        status_payload["error"] = "reference lock commit must be a 40-character git hash"
        return status_payload
    if not vendor_path or not vendor_path.exists():
        return status_payload
    try:
        actual_commit = subprocess.run(
            ["git", "-C", str(vendor_path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception as error:
        status_payload["error"] = f"vendor git checkout is not readable: {error}"
        return status_payload
    status_payload["actual_commit"] = actual_commit
    status_payload["matches_lock"] = actual_commit == expected_commit
    return status_payload


def _glm_ton_blueprint_status(reference: dict[str, Any], artifact_data: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    lock_data = reference.get("data") if isinstance(reference.get("data"), dict) else {}
    vendor_path_value = str(lock_data.get("vendor_path") or "")
    vendor_path = (GLM_TON_REFERENCE_LOCK.parent / vendor_path_value).resolve() if vendor_path_value else None
    deploy_script_path = vendor_path / "scripts" / "deployGlmJettonMinter.ts" if vendor_path else None
    artifact_contracts = artifact_data.get("contracts") if isinstance(artifact_data.get("contracts"), dict) else {}
    artifact_token = artifact_data.get("token") if isinstance(artifact_data.get("token"), dict) else {}
    metadata_url = os.getenv("TON_GLM_METADATA_URL") or artifact_token.get("metadata_url") or policy.get("metadata_url")
    admin_address = os.getenv("TON_JETTON_ADMIN_ADDRESS") or artifact_contracts.get("admin_address")
    payload: dict[str, Any] = {
        "deploy_script_path": str(deploy_script_path) if deploy_script_path else None,
        "deploy_script_exists": bool(deploy_script_path and deploy_script_path.exists()),
        "metadata_url": metadata_url,
        "has_admin_address": bool(admin_address),
        "admin_address_source": "env_or_artifact" if admin_address else None,
        "mainnet_guard": False,
        "metadata_matches_script": False,
        "admin_matches_script": False,
    }
    if deploy_script_path and deploy_script_path.exists():
        try:
            script_text = deploy_script_path.read_text(encoding="utf-8")
            script_metadata_match = re.search(r'const GLM_METADATA_URI = "([^"]+)";', script_text)
            script_admin_match = re.search(r'const GLM_ADMIN_ADDRESS = "([^"]+)";', script_text)
            if not metadata_url and script_metadata_match:
                metadata_url = script_metadata_match.group(1)
                payload["metadata_url"] = metadata_url
            if not admin_address and script_admin_match:
                admin_address = script_admin_match.group(1)
                payload["has_admin_address"] = True
                payload["admin_address_source"] = "deploy_script"
            payload["mainnet_guard"] = "provider.network() === 'mainnet'" in script_text
            payload["metadata_matches_script"] = bool(metadata_url and metadata_url in script_text)
            payload["admin_matches_script"] = bool(admin_address and admin_address in script_text)
        except Exception as error:
            payload["error"] = str(error)
    return payload


def _glm_ton_build_status(reference: dict[str, Any]) -> dict[str, Any]:
    lock_data = reference.get("data") if isinstance(reference.get("data"), dict) else {}
    vendor_path_value = str(lock_data.get("vendor_path") or "")
    vendor_path = (GLM_TON_REFERENCE_LOCK.parent / vendor_path_value).resolve() if vendor_path_value else None
    payload: dict[str, Any] = {
        "vendor_path": str(vendor_path) if vendor_path else None,
        "minter_compiled": False,
        "wallet_compiled": False,
        "wallet_library_hash": None,
        "contracts": {},
    }
    if not vendor_path:
        return payload
    for name, key in (("JettonMinter", "minter"), ("JettonWallet", "wallet")):
        artifact_path = vendor_path / "build" / f"{name}.compiled.json"
        contract_payload: dict[str, Any] = {
            "path": str(artifact_path),
            "exists": artifact_path.exists(),
        }
        if artifact_path.exists():
            try:
                data = json.loads(artifact_path.read_text(encoding="utf-8"))
                contract_payload["hash"] = data.get("hash")
                contract_payload["hashBase64"] = data.get("hashBase64")
                contract_payload["libraryHash"] = data.get("libraryHash")
                contract_payload["ok"] = bool(re.fullmatch(r"[0-9a-fA-F]{64}", str(data.get("hash") or "")) and data.get("hashBase64"))
            except Exception as error:
                contract_payload["error"] = str(error)
                contract_payload["ok"] = False
        else:
            contract_payload["ok"] = False
        payload["contracts"][key] = contract_payload
    payload["minter_compiled"] = bool(payload["contracts"].get("minter", {}).get("ok"))
    payload["wallet_compiled"] = bool(payload["contracts"].get("wallet", {}).get("ok"))
    payload["wallet_library_hash"] = payload["contracts"].get("wallet", {}).get("libraryHash")
    return payload


async def _cash_requests(db: AsyncSession, member_id: UUID, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(ReferralCashUpgradeRequest)
            .where(ReferralCashUpgradeRequest.member_id == member_id)
            .order_by(desc(ReferralCashUpgradeRequest.created_at))
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(row.id),
            "status": row.status,
            "legal_status": row.legal_status,
            "inn": row.inn,
            "passport_data": row.passport_data or {},
            "payout_details": row.payout_details or {},
            "tax_responsibility_confirmed_at": row.tax_responsibility_confirmed_at.isoformat() if row.tax_responsibility_confirmed_at else None,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "review_comment": row.review_comment,
            "onec_sync_status": row.onec_sync_status,
            "onec_last_error": row.onec_last_error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) < 4:
        return None
    return f"+7 *** *** {digits[-4:-2]} {digits[-2:]}"


def _validate_ton_wallet_address(address: str) -> str:
    value = (address or "").strip()
    # Friendly TON addresses are usually 48 chars and start with EQ/UQ.
    if re.fullmatch(r"[EU]Q[A-Za-z0-9_-]{46}", value):
        return value
    # Raw TON addresses are represented as workchain:64 hex chars.
    if re.fullmatch(r"-?\d:[A-Fa-f0-9]{64}", value):
        return value
    raise HTTPException(status_code=400, detail="Укажите корректный TON-адрес кошелька")


def _validate_raw_ton_wallet_address(address: str) -> str:
    value = (address or "").strip()
    if re.fullmatch(r"-?\d:[A-Fa-f0-9]{64}", value):
        return value.lower()
    raise HTTPException(status_code=400, detail="TON Connect должен вернуть raw-адрес формата workchain:hex")


def _crypto_wallet_meta(member: ReferralProgramMember) -> dict[str, Any] | None:
    meta = member.meta if isinstance(member.meta, dict) else {}
    wallet = meta.get("crypto_wallet")
    return wallet if isinstance(wallet, dict) else None


def _ton_connect_domain() -> str:
    return os.getenv("TON_CONNECT_DOMAIN", "partner.glamejewelry.ru").strip().lower()


def _challenge_payload_for_member(member: ReferralProgramMember) -> tuple[str, str]:
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    payload = f"glame-ton-proof:{member.id}:{uuid4()}:{secrets.token_urlsafe(24)}"
    meta = dict(member.meta or {})
    meta["crypto_wallet_challenge"] = {
        "payload": payload,
        "issued_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    member.meta = meta
    flag_modified(member, "meta")
    return payload, expires_at.isoformat()


def _ton_proof_message(address: str, proof: dict[str, Any]) -> bytes:
    workchain, address_hex = address.split(":", 1)
    domain = proof.get("domain") if isinstance(proof.get("domain"), dict) else {}
    domain_value = str(domain.get("value") or "").strip().lower()
    payload = str(proof.get("payload") or "")
    timestamp = int(proof.get("timestamp") or 0)
    domain_bytes = domain_value.encode("utf-8")

    return b"".join(
        [
            b"ton-proof-item-v2/",
            int(workchain).to_bytes(4, "big", signed=True),
            bytes.fromhex(address_hex),
            len(domain_bytes).to_bytes(4, "little"),
            domain_bytes,
            timestamp.to_bytes(8, "little", signed=False),
            payload.encode("utf-8"),
        ]
    )


def _decode_ton_state_init_boc(wallet_state_init: str) -> bytes:
    value = (wallet_state_init or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="TON Connect не вернул walletStateInit")

    padded = value + ("=" * (-len(value) % 4))
    try:
        return base64.b64decode(padded, validate=True)
    except Exception:
        try:
            return base64.urlsafe_b64decode(padded)
        except Exception as error:
            raise HTTPException(status_code=400, detail="Некорректный walletStateInit") from error


def _parse_ton_state_init(wallet_state_init: str) -> tuple[Cell, Cell | None, Cell | None]:
    try:
        root = Cell.one_from_boc(_decode_ton_state_init_boc(wallet_state_init))
        state_init = root.begin_parse()
        if state_init.read_bit():
            state_init.skip_bits(5)
        if state_init.read_bit():
            state_init.skip_bits(2)
        code = state_init.read_ref() if state_init.read_bit() else None
        data = state_init.read_ref() if state_init.read_bit() else None
        return root, code, data
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail="Некорректный walletStateInit") from error


def _read_ton_wallet_public_key_candidate(data: Cell, layout: str) -> str | None:
    try:
        wallet_data = data.begin_parse()
        if layout == "v5":
            wallet_data.read_bit()
            wallet_data.read_uint(32)
            wallet_data.read_uint(32)
        elif layout == "v3_v4":
            wallet_data.read_uint(32)
            wallet_data.read_uint(32)
        elif layout == "v1_v2":
            wallet_data.read_uint(32)
        else:
            return None
        return wallet_data.read_bytes(32).hex()
    except Exception:
        return None


def _ton_wallet_public_key_candidates(data: Cell | None) -> list[str]:
    if data is None:
        return []
    candidates: list[str] = []
    for layout in ("v5", "v3_v4", "v1_v2"):
        public_key = _read_ton_wallet_public_key_candidate(data, layout)
        if public_key and re.fullmatch(r"[a-f0-9]{64}", public_key) and public_key not in candidates:
            candidates.append(public_key)
    return candidates


def _verify_ton_wallet_state_init(*, address: str, public_key: str, wallet_state_init: str) -> dict[str, Any]:
    _, address_hex = address.split(":", 1)
    root, _code, data = _parse_ton_state_init(wallet_state_init)
    state_init_hash = root.bytes_hash().hex()
    if state_init_hash.lower() != address_hex.lower():
        raise HTTPException(status_code=400, detail="walletStateInit не соответствует адресу TON-кошелька")

    public_key_candidates = _ton_wallet_public_key_candidates(data)
    normalized_public_key = public_key.lower()
    if not public_key_candidates:
        raise HTTPException(status_code=400, detail="Не удалось извлечь public key из walletStateInit")
    if normalized_public_key not in public_key_candidates:
        raise HTTPException(status_code=400, detail="TON Connect public key не соответствует walletStateInit")

    return {
        "wallet_state_init_hash": state_init_hash,
        "wallet_state_init_public_key": normalized_public_key,
        "wallet_state_init_public_key_candidates": public_key_candidates,
    }


def _verify_ton_proof(
    *,
    address: str,
    public_key: str,
    wallet_state_init: str,
    proof: dict[str, Any],
    expected_payload: str,
) -> dict[str, Any]:
    domain = proof.get("domain") if isinstance(proof.get("domain"), dict) else {}
    domain_value = str(domain.get("value") or "").strip().lower()
    try:
        domain_length = int(domain.get("lengthBytes") or -1)
        timestamp = int(proof.get("timestamp") or 0)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail="TON proof содержит некорректные числовые поля") from error
    expected_domain = _ton_connect_domain()
    if domain_value != expected_domain or domain_length != len(domain_value.encode("utf-8")):
        raise HTTPException(status_code=400, detail="TON proof подписан для другого домена")

    payload = str(proof.get("payload") or "")
    if not payload or payload != expected_payload:
        raise HTTPException(status_code=400, detail="TON proof payload не совпадает с выданным challenge")

    now_ts = int(datetime.utcnow().timestamp())
    if timestamp < now_ts - 600 or timestamp > now_ts + 120:
        raise HTTPException(status_code=400, detail="TON proof устарел или имеет некорректное время")

    if not re.fullmatch(r"[A-Fa-f0-9]{64}", public_key or ""):
        raise HTTPException(status_code=400, detail="TON Connect не вернул корректный public key")
    verified_state_init = _verify_ton_wallet_state_init(
        address=address,
        public_key=public_key,
        wallet_state_init=wallet_state_init,
    )

    try:
        signature = base64.b64decode(str(proof.get("signature") or ""), validate=True)
    except Exception as error:
        raise HTTPException(status_code=400, detail="Некорректная TON proof подпись") from error
    if len(signature) != 64:
        raise HTTPException(status_code=400, detail="Некорректная TON proof подпись")

    message_hash = hashlib.sha256(_ton_proof_message(address, proof)).digest()
    signed_message = hashlib.sha256(b"\xff\xff" + b"ton-connect" + message_hash).digest()
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(signature, signed_message)
    except InvalidSignature as error:
        raise HTTPException(status_code=400, detail="TON proof подпись не прошла проверку") from error

    return {
        "domain": domain_value,
        "timestamp": timestamp,
        "payload": payload,
        "signature": proof.get("signature"),
        **verified_state_init,
    }


def _public_user_profile(user: User, member: ReferralProgramMember) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "phone": user.phone,
        "email": user.email,
        "loyalty_points": int(user.loyalty_points or 0),
        "customer_id_1c": user.customer_id_1c,
        "discount_card_id_1c": user.discount_card_id_1c,
        "discount_card_number": user.discount_card_number,
        "legal_status": member.legal_status,
        "inn": member.inn,
        "passport_data": member.passport_data or {},
        "payout_details": member.payout_details or {},
        "tax_responsibility_confirmed_at": member.tax_responsibility_confirmed_at.isoformat() if member.tax_responsibility_confirmed_at else None,
    }


async def _admin_partner_payload(
    db: AsyncSession,
    service: ReferralService,
    member: ReferralProgramMember,
    user: User,
    code: ReferralCode | None = None,
) -> dict[str, Any]:
    active_code = code or await service.get_active_code(member.id)
    summary = await service.dashboard_summary(member)
    eligibility = await service.sync_cash_eligibility(member)
    token = await GlameTokenService(db).summary_for_member(member.id)
    return {
        "member": _member_response(member).model_dump(),
        "profile": _public_user_profile(user, member),
        "referral_code": _code_response(active_code).model_dump() if active_code else None,
        "summary": summary,
        "token": token,
        "cash_upgrade": {
            "eligible": eligibility.eligible,
            "active_referrals": eligibility.active_referrals,
            "referral_revenue": eligibility.referral_revenue,
            "annual_referral_turnover": eligibility.annual_referral_turnover,
            "current_level": _level_payload(eligibility.level),
            "levels": [_level_payload(level) for level in service.referral_levels()],
            "thresholds": service.cash_upgrade_thresholds(),
            "reason": eligibility.reason,
        },
    }


@router.get("/admin/partners")
async def admin_list_referral_partners(
    search: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    reward_mode: str | None = Query(default=None),
    cash_status: str | None = Query(default=None),
    ton_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    code_join = and_(ReferralCode.member_id == ReferralProgramMember.id, ReferralCode.status == "active")
    conditions = []
    if status_filter:
        conditions.append(ReferralProgramMember.status == status_filter)
    if reward_mode:
        conditions.append(ReferralProgramMember.reward_mode == reward_mode)
    if cash_status:
        conditions.append(ReferralProgramMember.cash_status == cash_status)
    if ton_status == "verified":
        conditions.append(ReferralProgramMember.meta["crypto_wallet"]["status"].as_string() == "verified")
    elif ton_status == "linked":
        conditions.append(ReferralProgramMember.meta["crypto_wallet"]["status"].as_string() == "linked")
    elif ton_status == "claim_enabled":
        conditions.append(ReferralProgramMember.meta["crypto_wallet"]["glm_claim_enabled"].as_boolean().is_(True))
    elif ton_status == "missing":
        conditions.append(ReferralProgramMember.meta["crypto_wallet"].is_(None))
    if search and search.strip():
        value = f"%{search.strip()}%"
        conditions.append(
            or_(
                User.full_name.ilike(value),
                User.phone.ilike(value),
                User.email.ilike(value),
                ReferralCode.code.ilike(value),
                ReferralProgramMember.inn.ilike(value),
            )
        )

    base = (
        select(ReferralProgramMember, User, ReferralCode)
        .join(User, User.id == ReferralProgramMember.user_id)
        .outerjoin(ReferralCode, code_join)
    )
    count_query = (
        select(func.count(func.distinct(ReferralProgramMember.id)))
        .join(User, User.id == ReferralProgramMember.user_id)
        .outerjoin(ReferralCode, code_join)
    )
    if conditions:
        base = base.where(*conditions)
        count_query = count_query.where(*conditions)

    total = int((await db.execute(count_query)).scalar_one() or 0)
    rows = (
        await db.execute(
            base.order_by(desc(ReferralProgramMember.created_at))
            .offset(offset)
            .limit(limit)
        )
    ).all()
    partners = [await _admin_partner_payload(db, service, member, user, code) for member, user, code in rows]
    overview = {
        "partners_total": int((await db.execute(select(func.count(ReferralProgramMember.id)))).scalar_one() or 0),
        "partners_active": int((await db.execute(select(func.count(ReferralProgramMember.id)).where(ReferralProgramMember.status == "active"))).scalar_one() or 0),
        "cash_pending": int((await db.execute(select(func.count(ReferralCashUpgradeRequest.id)).where(ReferralCashUpgradeRequest.status == "pending"))).scalar_one() or 0),
        "payouts_pending_kopecks": int((await db.execute(select(func.coalesce(func.sum(ReferralPayout.amount_kopecks), 0)).where(ReferralPayout.status.in_(["pending", "approved"])))).scalar_one() or 0),
        "ton_verified": int((await db.execute(select(func.count(ReferralProgramMember.id)).where(ReferralProgramMember.meta["crypto_wallet"]["status"].as_string() == "verified"))).scalar_one() or 0),
        "glm_claim_enabled": int((await db.execute(select(func.count(ReferralProgramMember.id)).where(ReferralProgramMember.meta["crypto_wallet"]["glm_claim_enabled"].as_boolean().is_(True)))).scalar_one() or 0),
    }
    return {"partners": partners, "total": total, "limit": limit, "offset": offset, "overview": overview}


@router.get("/admin/rate-promotions", response_model=list[ReferralRatePromotionResponse])
async def admin_list_referral_rate_promotions(
    _current_user: User = Depends(require_admin()),
):
    return [_rate_promotion_response(item) for item in ReferralService.list_rate_promotions()]


@router.post("/admin/rate-promotions", response_model=ReferralRatePromotionResponse)
async def admin_create_referral_rate_promotion(
    payload: ReferralRatePromotionCreateRequest,
    _current_user: User = Depends(require_admin()),
):
    try:
        promotion = ReferralService.create_rate_promotion(
            title=payload.title,
            rate_percent=Decimal(str(payload.rate_percent)),
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            is_active=payload.is_active,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _rate_promotion_response(promotion)


@router.patch("/admin/rate-promotions/{promotion_id}", response_model=ReferralRatePromotionResponse)
async def admin_update_referral_rate_promotion(
    promotion_id: str,
    payload: ReferralRatePromotionUpdateRequest,
    _current_user: User = Depends(require_admin()),
):
    patch = payload.model_dump(exclude_unset=True)
    try:
        promotion = ReferralService.update_rate_promotion(promotion_id, patch)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if promotion is None:
        raise HTTPException(status_code=404, detail="Акция не найдена")
    return _rate_promotion_response(promotion)


@router.delete("/admin/rate-promotions/{promotion_id}")
async def admin_delete_referral_rate_promotion(
    promotion_id: str,
    _current_user: User = Depends(require_admin()),
):
    if not ReferralService.delete_rate_promotion(promotion_id):
        raise HTTPException(status_code=404, detail="Акция не найдена")
    return {"status": "success"}


@router.get("/admin/reward-store-items")
async def admin_list_reward_store_items(
    include_archived: bool = Query(True),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_reward_store_table(db)
    stmt = select(RewardStoreItem)
    if not include_archived:
        stmt = stmt.where(RewardStoreItem.is_active == True, RewardStoreItem.status != "archived")
    rows = (
        await db.execute(
            stmt.order_by(
                RewardStoreItem.is_active.desc(),
                RewardStoreItem.sort_order.asc(),
                RewardStoreItem.created_at.asc(),
            )
        )
    ).scalars().all()
    return [_reward_store_item_payload(row) for row in rows]


@router.post("/admin/reward-store-items/image")
async def admin_upload_reward_store_item_image(
    file: UploadFile = File(...),
    _current_user: User = Depends(require_admin()),
):
    content_type = (file.content_type or "").lower()
    allowed = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    if content_type not in allowed:
        raise HTTPException(status_code=400, detail="Поддерживаются только JPG, PNG или WEBP")
    data = await file.read()
    detected_type = validate_image_upload(data, content_type, max_bytes=8 * 1024 * 1024)
    if not data:
        raise HTTPException(status_code=400, detail="Файл пустой")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл слишком большой, максимум 8 МБ")
    _ensure_reward_store_media_dir()
    digest = hashlib.sha256(data).hexdigest()[:16]
    file_name = f"reward_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{digest}{allowed[content_type]}"
    path = REWARD_STORE_MEDIA_DIR / file_name
    path.write_bytes(data)
    return {
        "status": "success",
        "image_url": _reward_store_media_public_url(file_name),
        "content_type": detected_type,
        "size": len(data),
    }


@router.post("/admin/reward-store-items")
async def admin_create_reward_store_item(
    payload: RewardStoreItemPayload,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_reward_store_table(db)
    sku = payload.sku.strip()
    exists = (await db.execute(select(RewardStoreItem).where(RewardStoreItem.sku == sku))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="SKU уже существует")
    item = RewardStoreItem(
        id=uuid4(),
        sku=sku,
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        category=payload.category.strip() or "branded_goods",
        inventory_status=payload.inventory_status.strip() or "pilot_batch",
        status=payload.status,
        price_glm=payload.price_glm,
        price_points=payload.price_points,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
        meta=_reward_store_meta_from_payload(payload),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _reward_store_item_payload(item)


@router.patch("/admin/reward-store-items/{item_id}")
async def admin_update_reward_store_item(
    item_id: UUID,
    payload: RewardStoreItemPatch,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_reward_store_table(db)
    item = (await db.execute(select(RewardStoreItem).where(RewardStoreItem.id == item_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    patch = payload.model_dump(exclude_unset=True)
    if "sku" in patch and patch["sku"] is not None:
        sku = str(patch["sku"]).strip()
        duplicate = (
            await db.execute(select(RewardStoreItem).where(RewardStoreItem.sku == sku, RewardStoreItem.id != item.id))
        ).scalar_one_or_none()
        if duplicate:
            raise HTTPException(status_code=400, detail="SKU уже существует")
        item.sku = sku
    for field in ("title", "description", "category", "inventory_status", "status", "price_glm", "price_points", "sort_order", "is_active"):
        if field not in patch:
            continue
        value = patch[field]
        if field in {"title", "description", "category", "inventory_status"} and isinstance(value, str):
            value = value.strip()
        setattr(item, field, value)
    if any(field in patch for field in ("meta", "quantity_available", "image_url")):
        item.meta = _reward_store_meta_from_payload(payload, item.meta if isinstance(item.meta, dict) else {})
        flag_modified(item, "meta")
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return _reward_store_item_payload(item)


@router.post("/admin/reward-store-items/{item_id}/archive")
async def admin_archive_reward_store_item(
    item_id: UUID,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_reward_store_table(db)
    item = (await db.execute(select(RewardStoreItem).where(RewardStoreItem.id == item_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    item.status = "archived"
    item.is_active = False
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return _reward_store_item_payload(item)


@router.post("/admin/reward-store-items/{item_id}/restore")
async def admin_restore_reward_store_item(
    item_id: UUID,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_reward_store_table(db)
    item = (await db.execute(select(RewardStoreItem).where(RewardStoreItem.id == item_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    item.status = "available"
    item.is_active = True
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return _reward_store_item_payload(item)


@router.get("/media-materials", response_model=list[ReferralMediaMaterialResponse])
async def list_referral_media_materials(
    _current_user: User = Depends(get_current_user),
):
    return [_media_response(item) for item in _read_media_materials() if item.get("is_active", True)]


@router.get("/media-materials/{material_id}/download")
async def download_referral_media_material(
    material_id: str,
    _current_user: User = Depends(get_current_user),
):
    material = next((item for item in _read_media_materials() if item.get("id") == material_id and item.get("is_active", True)), None)
    if not material:
        raise HTTPException(status_code=404, detail="Материал не найден")
    file_name = Path(str(material.get("file_name") or "")).name
    file_path = REFERRAL_MEDIA_DIR / file_name
    if not file_name or not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(
        path=str(file_path),
        media_type=material.get("content_type") or "application/octet-stream",
        filename=Path(str(material.get("original_file_name") or file_name)).name,
    )


@router.get("/admin/media-materials", response_model=list[ReferralMediaMaterialResponse])
async def admin_list_referral_media_materials(
    _current_user: User = Depends(require_admin()),
):
    return [_media_response(item) for item in _read_media_materials()]


@router.post("/admin/media-materials", response_model=ReferralMediaMaterialResponse)
async def admin_upload_referral_media_material(
    title: str = Form(...),
    category: str = Form("other"),
    description: str | None = Form(None),
    sort_order: int = Form(100),
    is_active: bool = Form(True),
    file: UploadFile = File(...),
    _current_user: User = Depends(require_admin()),
):
    _ensure_media_dir()
    content_type = (file.content_type or "").lower()
    allowed = content_type.startswith("image/") or content_type == "application/pdf"
    if not allowed:
        raise HTTPException(status_code=400, detail="Можно загружать только изображения или PDF")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой")
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Файл слишком большой, максимум 15 МБ")
    if content_type == "application/pdf":
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Содержимое файла не соответствует PDF")
    else:
        content_type = validate_image_upload(content, content_type)
    original_name = _safe_media_filename(file.filename or "material")
    safe_name = f"{uuid4().hex}_{original_name}"
    target = REFERRAL_MEDIA_DIR / safe_name
    try:
        target.write_bytes(content)
    finally:
        await file.close()
    preview_file_name = _create_pdf_preview(target) if content_type == "application/pdf" else None
    now = datetime.utcnow().isoformat()
    material = {
        "id": str(uuid4()),
        "title": title.strip() or Path(file.filename or original_name).stem,
        "category": _normalize_media_category(category),
        "description": (description or "").strip() or None,
        "file_name": safe_name,
        "preview_file_name": preview_file_name,
        "original_file_name": file.filename or original_name,
        "content_type": content_type or None,
        "size": target.stat().st_size if target.exists() else 0,
        "is_active": bool(is_active),
        "sort_order": int(sort_order or 100),
        "created_at": now,
        "updated_at": now,
    }
    materials = _read_media_materials()
    materials.append(material)
    _write_media_materials(materials)
    return _media_response(material)


@router.patch("/admin/media-materials/{material_id}", response_model=ReferralMediaMaterialResponse)
async def admin_update_referral_media_material(
    material_id: str,
    payload: ReferralMediaMaterialUpdateRequest,
    _current_user: User = Depends(require_admin()),
):
    materials = _read_media_materials()
    for item in materials:
        if item.get("id") != material_id:
            continue
        if payload.title is not None:
            item["title"] = payload.title.strip() or item.get("title") or "Материал"
        if payload.category is not None:
            item["category"] = _normalize_media_category(payload.category)
        if payload.description is not None:
            item["description"] = payload.description.strip() or None
        if payload.is_active is not None:
            item["is_active"] = bool(payload.is_active)
        if payload.sort_order is not None:
            item["sort_order"] = int(payload.sort_order)
        item["updated_at"] = datetime.utcnow().isoformat()
        _write_media_materials(materials)
        return _media_response(item)
    raise HTTPException(status_code=404, detail="Медиаматериал не найден")


@router.delete("/admin/media-materials/{material_id}")
async def admin_delete_referral_media_material(
    material_id: str,
    _current_user: User = Depends(require_admin()),
):
    materials = _read_media_materials()
    next_materials: list[dict[str, Any]] = []
    deleted: dict[str, Any] | None = None
    for item in materials:
        if item.get("id") == material_id:
            deleted = item
        else:
            next_materials.append(item)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Медиаматериал не найден")
    file_name = str(deleted.get("file_name") or "")
    target = REFERRAL_MEDIA_DIR / file_name
    if target.exists() and target.is_file():
        target.unlink()
    preview_file_name = str(deleted.get("preview_file_name") or "")
    preview = REFERRAL_MEDIA_DIR / preview_file_name
    if preview.exists() and preview.is_file():
        preview.unlink()
    _write_media_materials(next_materials)
    return {"status": "success"}


@router.get("/admin/partners/{member_id}")
async def admin_get_referral_partner(
    member_id: UUID,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    row = (
        await db.execute(
            select(ReferralProgramMember, User)
            .join(User, User.id == ReferralProgramMember.user_id)
            .where(ReferralProgramMember.id == member_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Партнер не найден")
    member, user = row
    payload = await _admin_partner_payload(db, service, member, user)
    payload.update(
        {
            "referrals": await _recent_referrals(db, member.id, limit=200),
            "commissions": await _recent_commissions(db, member.id, limit=200),
            "payouts": await _recent_payouts(db, member.id, limit=200),
            "cash_requests": await _cash_requests(db, member.id, limit=50),
        }
    )
    return payload


@router.post("/admin/pos-attribution", response_model=AdminPosReferralAttachResponse)
async def admin_attach_pos_referral(
    payload: AdminPosReferralAttachRequest,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    phone_norm = normalize_phone(payload.phone)
    code_value = payload.code.strip().upper()
    full_name = (payload.full_name or "").strip() or None
    if not phone_norm:
        raise HTTPException(status_code=400, detail="Укажите телефон покупателя")
    if not code_value:
        raise HTTPException(status_code=400, detail="Укажите реферальный код")

    service = ReferralService(db)
    code = await service.validate_code(code_value)
    if code is None:
        raise HTTPException(status_code=404, detail="Реферальный код не найден или неактивен")

    member = (
        await db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == code.member_id))
    ).scalar_one_or_none()
    if member is None or member.status != "active":
        raise HTTPException(status_code=400, detail="Партнерская программа по этому коду неактивна")

    user = (await db.execute(select(User).where(User.phone == phone_norm))).scalar_one_or_none()
    created_user = False
    if user is None:
        user = User(
            phone=phone_norm,
            full_name=full_name,
            role="customer",
            is_customer=True,
            discount_card_number=phone_norm,
            preferences={"source": "pos_referral"},
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        created_user = True
    elif full_name and not user.full_name:
        user.full_name = full_name
        await db.commit()
        await db.refresh(user)

    if member.user_id == user.id:
        raise HTTPException(status_code=400, detail="Партнер не может быть собственным рефералом")

    existing = (
        await db.execute(
            select(ReferralAttribution).where(
                ReferralAttribution.referee_user_id == user.id,
                ReferralAttribution.status.in_(["pending", "active"]),
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        attribution = existing
        if attribution.referrer_member_id != member.id:
            raise HTTPException(status_code=409, detail="Покупатель уже привязан к другому партнеру")
    else:
        attribution = ReferralAttribution(
            referrer_member_id=member.id,
            referral_code_id=code.id,
            referee_user_id=user.id,
            status="pending",
            source="pos_rmk",
            meta={"phone": phone_norm, "created_user": created_user},
        )
        code.usage_count = int(code.usage_count or 0) + 1
        db.add(attribution)
        await db.commit()
        await db.refresh(attribution)

    welcome_source_id = f"referral_welcome:{user.id}:{code.code}"
    existing_welcome = (
        await db.execute(select(LoyaltyTransaction).where(LoyaltyTransaction.source_id == welcome_source_id))
    ).scalar_one_or_none()
    welcome_points = 0
    if existing_welcome is None:
        loyalty = LoyaltyService(db)
        await loyalty.earn_points(
            user_id=user.id,
            points=REFERRED_CLIENT_WELCOME_BONUS_POINTS,
            reason="referral_welcome",
            metadata={"description": "Бонус за регистрацию по реферальному коду", "referral_code": code.code},
            source="platform",
            source_id=welcome_source_id,
        )
        welcome_points = REFERRED_CLIENT_WELCOME_BONUS_POINTS
        await db.refresh(user)

    onec_sync_status = None
    onec_sync_job_id = None
    try:
        onec_payload = OneCUserRegistrationPayload(
            phone=phone_norm,
            full_name=user.full_name or full_name or phone_norm,
            email=user.email,
            inn=None,
            birth_date=user.birth_date,
            loyalty_program_key=None,
            source="referral_client",
            customer_group_key=REFERRAL_CLIENT_CUSTOMER_GROUP_KEY,
            referral_code=code.code,
            welcome_bonus_points=REFERRED_CLIENT_WELCOME_BONUS_POINTS,
            welcome_bonus_comment=welcome_source_id,
        )
        job = await OneCUserSyncService(db).enqueue_registration(user, onec_payload)
        if job:
            onec_sync_status = job.status
            onec_sync_job_id = str(job.id)
    except Exception:
        onec_sync_status = "not_queued"

    return AdminPosReferralAttachResponse(
        status="success",
        message="Покупатель привязан к партнеру. Бонусы будут синхронизированы с 1С.",
        attribution_id=str(attribution.id),
        user_id=str(user.id),
        phone=phone_norm,
        code=code.code,
        welcome_points=welcome_points,
        onec_sync_status=onec_sync_status,
        onec_sync_job_id=onec_sync_job_id,
    )


@router.patch("/admin/partners/{member_id}")
async def admin_update_referral_partner(
    member_id: UUID,
    payload: AdminPartnerUpdateRequest,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(ReferralProgramMember, User)
            .join(User, User.id == ReferralProgramMember.user_id)
            .where(ReferralProgramMember.id == member_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Партнер не найден")
    member, user = row
    changed = False
    for field in ["status", "reward_mode", "cash_status", "program_level", "onec_agency_contract_id", "block_reason"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(member, field, value.strip() if isinstance(value, str) else value)
            changed = True
    if payload.points_rate_percent is not None:
        member.points_rate_percent = payload.points_rate_percent
        changed = True
    if payload.cash_rate_percent is not None:
        member.cash_rate_percent = payload.cash_rate_percent
        changed = True
    if payload.status == "blocked" and not member.blocked_at:
        member.blocked_at = datetime.utcnow()
    if payload.status == "active":
        member.blocked_at = None
        member.block_reason = None
    if changed:
        await db.commit()
        await db.refresh(member)
    return await _admin_partner_payload(db, ReferralService(db), member, user)


@router.post("/admin/partners/{member_id}/glm-claim")
async def admin_set_glm_claim_access(
    member_id: UUID,
    payload: AdminGlmClaimRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(ReferralProgramMember, User)
            .join(User, User.id == ReferralProgramMember.user_id)
            .where(ReferralProgramMember.id == member_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Партнер не найден")
    member, user = row
    wallet = _crypto_wallet_meta(member)
    if payload.enabled and (not wallet or wallet.get("status") != "verified"):
        raise HTTPException(status_code=400, detail="GLM claim можно включить только для verified TON-кошелька")

    now = datetime.utcnow().isoformat()
    wallet_payload = {
        **(wallet or {}),
        "glm_claim_enabled": bool(payload.enabled),
        "glm_claim_updated_at": now,
        "glm_claim_updated_by": str(current_user.id),
    }
    if payload.comment:
        wallet_payload["glm_claim_comment"] = payload.comment.strip()
    if payload.enabled and not wallet_payload.get("glm_claim_enabled_at"):
        wallet_payload["glm_claim_enabled_at"] = now
    if not payload.enabled:
        wallet_payload["glm_claim_disabled_at"] = now
    member.meta = {
        **(member.meta or {}),
        "crypto_wallet": wallet_payload,
    }
    flag_modified(member, "meta")
    await db.commit()
    await db.refresh(member)
    return await _admin_partner_payload(db, ReferralService(db), member, user)


@router.post("/admin/partners/{member_id}/glm-release")
async def admin_release_glm_hold(
    member_id: UUID,
    payload: AdminGlmReleaseRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(ReferralProgramMember, User)
            .join(User, User.id == ReferralProgramMember.user_id)
            .where(ReferralProgramMember.id == member_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Партнер не найден")
    member, user = row
    token_service = GlameTokenService(db)
    try:
        tx = await token_service.release_hold_to_balance(
            member=member,
            amount=payload.amount,
            admin_user_id=current_user.id,
            reason=payload.reason or "admin_release",
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    result = await _admin_partner_payload(db, ReferralService(db), member, user)
    result["glm_release"] = {
        "id": str(tx.id),
        "amount": int(tx.amount or 0),
        "status": tx.status,
    }
    return result


@router.post("/admin/glm-release-due")
async def admin_release_due_glm_holds(
    payload: AdminGlmReleaseDueRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    result = await GlameTokenService(db).release_due_holds(limit=payload.limit, admin_user_id=current_user.id)
    await db.commit()
    return {"status": "success", **result}


@router.post("/admin/partners/{member_id}/glm-adjustment")
async def admin_adjust_glm_balance(
    member_id: UUID,
    payload: AdminGlmAdjustmentRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(ReferralProgramMember, User)
            .join(User, User.id == ReferralProgramMember.user_id)
            .where(ReferralProgramMember.id == member_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Партнер не найден")
    member, user = row
    try:
        tx = await GlameTokenService(db).adjust_available_balance(
            member=member,
            amount=payload.amount,
            direction=payload.direction,
            reason=payload.reason,
            admin_user_id=current_user.id,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    result = await _admin_partner_payload(db, ReferralService(db), member, user)
    result["glm_adjustment"] = _glm_transaction_payload(tx, member, user)
    return result


@router.post("/admin/partners/{member_id}/commissions/{commission_id}/cancel")
async def admin_cancel_referral_commission(
    member_id: UUID,
    commission_id: UUID,
    payload: AdminCommissionCancelRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(ReferralCommission, ReferralProgramMember, User)
            .join(ReferralProgramMember, ReferralProgramMember.id == ReferralCommission.referrer_member_id)
            .join(User, User.id == ReferralProgramMember.user_id)
            .where(
                ReferralCommission.id == commission_id,
                ReferralCommission.referrer_member_id == member_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Комиссия не найдена")
    commission, member, user = row
    try:
        reversal = await GlameTokenService(db).cancel_referral_commission_glm(
            commission=commission,
            admin_user_id=current_user.id,
            reason=payload.reason,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    result = await _admin_partner_payload(db, ReferralService(db), member, user)
    result["glm_reversal"] = reversal
    return result

@router.get("/admin/glm-dashboard")
async def admin_glm_dashboard(
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    account_totals = (
        await db.execute(
            select(
                func.count(GlameTokenAccount.id),
                func.coalesce(func.sum(GlameTokenAccount.balance), 0),
                func.coalesce(func.sum(GlameTokenAccount.hold_balance), 0),
                func.coalesce(func.sum(GlameTokenAccount.lifetime_earned), 0),
                func.coalesce(func.sum(GlameTokenAccount.lifetime_burned), 0),
            ).where(GlameTokenAccount.token_code == "GLM")
        )
    ).one()
    tx_totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(GlameTokenTransaction.transaction_type == "earn"), 0),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(GlameTokenTransaction.transaction_type == "release"), 0),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(GlameTokenTransaction.transaction_type == "claim"), 0),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(GlameTokenTransaction.transaction_type == "claim", GlameTokenTransaction.status == "pending"), 0),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(GlameTokenTransaction.transaction_type == "claim", GlameTokenTransaction.status == "processed"), 0),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(GlameTokenTransaction.transaction_type == "earn", GlameTokenTransaction.status == "hold", GlameTokenTransaction.available_at <= now), 0),
                func.count(GlameTokenTransaction.id).filter(GlameTokenTransaction.transaction_type == "claim", GlameTokenTransaction.status == "pending"),
                func.count(GlameTokenTransaction.id).filter(GlameTokenTransaction.transaction_type == "earn", GlameTokenTransaction.status == "hold", GlameTokenTransaction.available_at <= now),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(GlameTokenTransaction.transaction_type == "earn", GlameTokenTransaction.created_at >= month_start), 0),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(GlameTokenTransaction.transaction_type == "conversion"), 0),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(GlameTokenTransaction.transaction_type == "redemption"), 0),
            ).where(GlameTokenTransaction.token_code == "GLM")
        )
    ).one()
    top_rows = (
        await db.execute(
            select(GlameTokenAccount, ReferralProgramMember, User)
            .join(ReferralProgramMember, ReferralProgramMember.id == GlameTokenAccount.referral_member_id)
            .join(User, User.id == ReferralProgramMember.user_id)
            .where(GlameTokenAccount.token_code == "GLM")
            .order_by((GlameTokenAccount.balance + GlameTokenAccount.hold_balance).desc())
            .limit(10)
        )
    ).all()
    earn_total = int(tx_totals[0] or 0)
    conversion_total = int(tx_totals[9] or 0)
    redemption_total = abs(int(tx_totals[10] or 0))
    emission_total = max(0, earn_total + conversion_total)
    monthly_earn_total = int(tx_totals[8] or 0)
    return {
        "accounts_total": int(account_totals[0] or 0),
        "balance_total": int(account_totals[1] or 0),
        "hold_total": int(account_totals[2] or 0),
        "lifetime_earned_total": int(account_totals[3] or 0),
        "lifetime_burned_total": int(account_totals[4] or 0),
        "earn_total": earn_total,
        "release_total": int(tx_totals[1] or 0),
        "claim_total": int(tx_totals[2] or 0),
        "pending_claim_total": int(tx_totals[3] or 0),
        "processed_claim_total": int(tx_totals[4] or 0),
        "due_hold_total": int(tx_totals[5] or 0),
        "pending_claim_count": int(tx_totals[6] or 0),
        "due_hold_count": int(tx_totals[7] or 0),
        "monthly_earn_total": monthly_earn_total,
        "monthly_referral_emission_limit": GLAME_TOKEN_MONTHLY_REFERRAL_EMISSION_LIMIT,
        "monthly_referral_emission_remaining": max(0, GLAME_TOKEN_MONTHLY_REFERRAL_EMISSION_LIMIT - monthly_earn_total),
        "monthly_referral_emission_percent": round((monthly_earn_total / GLAME_TOKEN_MONTHLY_REFERRAL_EMISSION_LIMIT) * 100, 1) if GLAME_TOKEN_MONTHLY_REFERRAL_EMISSION_LIMIT else 0,
        "referral_campaign": GlameTokenService.referral_campaign_payload(),
        "conversion_total": conversion_total,
        "redemption_total": redemption_total,
        "burned_total": int(account_totals[4] or 0),
        "emission_total": emission_total,
        "real_turnover_backed_total": earn_total,
        "real_turnover_backed_percent": round((earn_total / emission_total) * 100, 1) if emission_total else 0,
        "top_partners": [
            {
                "member_id": str(member.id),
                "partner_name": user.full_name or "Партнер GLAME",
                "partner_phone": user.phone,
                "balance": int(account.balance or 0),
                "hold_balance": int(account.hold_balance or 0),
                "lifetime_earned": int(account.lifetime_earned or 0),
            }
            for account, member, user in top_rows
        ],
    }


@router.get("/admin/glm-effectiveness")
async def admin_glm_effectiveness(
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    stats_start_at = _glm_operational_stats_start_at()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if stats_start_at and stats_start_at > month_start:
        month_start = stats_start_at
    active_redemption_statuses = ("pending_fulfillment", "fulfilled")
    tx_window_conditions = [GlameTokenTransaction.created_at >= stats_start_at] if stats_start_at else []

    totals = (
        await db.execute(
            select(
                func.count(GlameTokenAccount.id),
                func.count(GlameTokenAccount.id).filter((GlameTokenAccount.balance + GlameTokenAccount.hold_balance) > 0),
                func.count(GlameTokenAccount.id).filter(GlameTokenAccount.balance >= 800),
                func.count(GlameTokenAccount.id).filter(GlameTokenAccount.balance >= 5000),
                func.coalesce(func.sum(GlameTokenAccount.lifetime_earned), 0),
                func.coalesce(func.sum(GlameTokenAccount.lifetime_burned), 0),
            ).where(GlameTokenAccount.token_code == "GLM")
        )
    ).one()
    tx_totals = (
        await db.execute(
            select(
                func.count(func.distinct(GlameTokenTransaction.account_id)).filter(
                    GlameTokenTransaction.transaction_type == "redemption",
                    GlameTokenTransaction.status.in_(active_redemption_statuses),
                ),
                func.count(GlameTokenTransaction.id).filter(
                    GlameTokenTransaction.transaction_type == "redemption",
                    GlameTokenTransaction.status.in_(active_redemption_statuses),
                ),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(
                    GlameTokenTransaction.transaction_type == "redemption",
                    GlameTokenTransaction.status.in_(active_redemption_statuses),
                ), 0),
                func.count(func.distinct(GlameTokenTransaction.account_id)).filter(
                    GlameTokenTransaction.transaction_type == "conversion",
                    GlameTokenTransaction.status == "available",
                ),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(
                    GlameTokenTransaction.transaction_type == "conversion",
                    GlameTokenTransaction.status == "available",
                ), 0),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(
                    GlameTokenTransaction.transaction_type == "earn",
                    GlameTokenTransaction.created_at >= month_start,
                ), 0),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(
                    GlameTokenTransaction.transaction_type == "conversion",
                    GlameTokenTransaction.status == "available",
                    GlameTokenTransaction.created_at >= month_start,
                ), 0),
                func.coalesce(func.sum(GlameTokenTransaction.amount).filter(
                    GlameTokenTransaction.transaction_type == "redemption",
                    GlameTokenTransaction.status.in_(active_redemption_statuses),
                    GlameTokenTransaction.created_at >= month_start,
                ), 0),
            ).where(GlameTokenTransaction.token_code == "GLM", *tx_window_conditions)
        )
    ).one()
    redeemed_account_ids = (
        await db.execute(
            select(GlameTokenTransaction.account_id)
            .where(
                GlameTokenTransaction.token_code == "GLM",
                GlameTokenTransaction.transaction_type == "redemption",
                GlameTokenTransaction.status.in_(active_redemption_statuses),
                *tx_window_conditions,
            )
            .group_by(GlameTokenTransaction.account_id)
        )
    ).scalars().all()
    redeemed_account_id_set = {str(account_id) for account_id in redeemed_account_ids}
    high_balance_rows = (
        await db.execute(
            select(GlameTokenAccount.id)
            .where(
                GlameTokenAccount.token_code == "GLM",
                GlameTokenAccount.balance >= 5000,
            )
        )
    ).scalars().all()
    high_balance_no_redemption_count = sum(1 for account_id in high_balance_rows if str(account_id) not in redeemed_account_id_set)

    redemption_rows = (
        await db.execute(
            select(GlameTokenTransaction.amount, GlameTokenTransaction.meta)
            .where(
                GlameTokenTransaction.token_code == "GLM",
                GlameTokenTransaction.transaction_type == "redemption",
                GlameTokenTransaction.status.in_(active_redemption_statuses),
                *tx_window_conditions,
            )
            .order_by(GlameTokenTransaction.created_at.desc())
            .limit(500)
        )
    ).all()
    commission_window_conditions = [ReferralCommission.created_at >= stats_start_at] if stats_start_at else []
    commission_totals = (
        await db.execute(
            select(
                func.count(ReferralCommission.id),
                func.coalesce(func.sum(ReferralCommission.commission_base), 0),
                func.coalesce(func.sum(ReferralCommission.amount_kopecks), 0),
                func.count(func.distinct(ReferralCommission.referrer_member_id)),
                func.count(func.distinct(ReferralCommission.referee_user_id)),
            ).where(
                ReferralCommission.status != "canceled",
                *commission_window_conditions,
            )
        )
    ).one()
    glm_linked_totals = (
        await db.execute(
            select(
                func.count(func.distinct(ReferralCommission.referrer_member_id)),
                func.coalesce(func.sum(ReferralCommission.commission_base), 0),
                func.coalesce(func.sum(ReferralCommission.amount_kopecks), 0),
            )
            .join(
                GlameTokenAccount,
                and_(
                    GlameTokenAccount.referral_member_id == ReferralCommission.referrer_member_id,
                    GlameTokenAccount.token_code == "GLM",
                ),
            )
            .where(
                ReferralCommission.status != "canceled",
                *commission_window_conditions,
            )
        )
    ).one()
    repeat_referee_rows = (
        await db.execute(
            select(
                ReferralCommission.referee_user_id,
                func.count(ReferralCommission.id).label("orders_count"),
                func.coalesce(func.sum(ReferralCommission.commission_base), 0).label("turnover_kopecks"),
            )
            .where(
                ReferralCommission.status != "canceled",
                ReferralCommission.referee_user_id.is_not(None),
                *commission_window_conditions,
            )
            .group_by(ReferralCommission.referee_user_id)
            .having(func.count(ReferralCommission.id) > 1)
        )
    ).all()
    top_referral_rows = (
        await db.execute(
            select(
                ReferralProgramMember.id,
                User.full_name,
                User.phone,
                func.count(ReferralCommission.id),
                func.coalesce(func.sum(ReferralCommission.commission_base), 0),
                func.coalesce(func.sum(ReferralCommission.amount_kopecks), 0),
                func.coalesce(func.max(GlameTokenAccount.balance), 0),
                func.coalesce(func.max(GlameTokenAccount.hold_balance), 0),
                func.coalesce(func.max(GlameTokenAccount.lifetime_earned), 0),
            )
            .join(ReferralProgramMember, ReferralProgramMember.id == ReferralCommission.referrer_member_id)
            .join(User, User.id == ReferralProgramMember.user_id)
            .outerjoin(
                GlameTokenAccount,
                and_(
                    GlameTokenAccount.referral_member_id == ReferralProgramMember.id,
                    GlameTokenAccount.token_code == "GLM",
                ),
            )
            .where(
                ReferralCommission.status != "canceled",
                *commission_window_conditions,
            )
            .group_by(ReferralProgramMember.id, User.full_name, User.phone)
            .order_by(desc(func.coalesce(func.sum(ReferralCommission.commission_base), 0)))
            .limit(8)
        )
    ).all()
    by_category: dict[str, dict[str, int | str]] = {}
    by_sku: dict[str, dict[str, int | str]] = {}
    for amount, meta in redemption_rows:
        redemption_amount = abs(int(amount or 0))
        payload = meta if isinstance(meta, dict) else {}
        category = str(payload.get("category") or "other")
        sku = str(payload.get("sku") or "unknown")
        title = str(payload.get("title") or payload.get("item_title") or sku)
        category_bucket = by_category.setdefault(category, {"category": category, "count": 0, "amount": 0})
        category_bucket["count"] = int(category_bucket["count"]) + 1
        category_bucket["amount"] = int(category_bucket["amount"]) + redemption_amount
        sku_bucket = by_sku.setdefault(sku, {"sku": sku, "title": title, "count": 0, "amount": 0})
        sku_bucket["count"] = int(sku_bucket["count"]) + 1
        sku_bucket["amount"] = int(sku_bucket["amount"]) + redemption_amount

    accounts_total = int(totals[0] or 0)
    active_balance_accounts = int(totals[1] or 0)
    ready_to_redeem_count = int(totals[2] or 0)
    redeemers_count = int(tx_totals[0] or 0)
    redemption_total = abs(int(tx_totals[2] or 0))
    conversion_total = int(tx_totals[4] or 0)
    monthly_redemption_total = abs(int(tx_totals[7] or 0))
    lifetime_earned_total = int(tx_totals[5] or 0)
    lifetime_burned_total = redemption_total
    referral_turnover_kopecks = int(commission_totals[1] or 0)
    glm_linked_turnover_kopecks = int(glm_linked_totals[1] or 0)
    repeat_referral_orders_count = sum(max(0, int(row.orders_count or 0) - 1) for row in repeat_referee_rows)
    repeat_referral_turnover_kopecks = sum(int(row.turnover_kopecks or 0) for row in repeat_referee_rows)

    return {
        "generated_at": now.isoformat(),
        "network": _glm_operational_network(),
        "period": {
            "current_month_start": month_start.isoformat(),
            "operational_stats_start_at": stats_start_at.isoformat() if stats_start_at else None,
        },
        "accounts_total": accounts_total,
        "active_balance_accounts": active_balance_accounts,
        "redeemers_count": redeemers_count,
        "redemption_conversion_percent": round((redeemers_count / accounts_total) * 100, 1) if accounts_total else 0,
        "redemption_count": int(tx_totals[1] or 0),
        "redemption_total": redemption_total,
        "burn_ratio_percent": round((lifetime_burned_total / lifetime_earned_total) * 100, 1) if lifetime_earned_total else 0,
        "lifetime_earned_total": lifetime_earned_total,
        "lifetime_burned_total": lifetime_burned_total,
        "conversion_accounts": int(tx_totals[3] or 0),
        "conversion_total": conversion_total,
        "conversion_to_redemption_percent": round((redemption_total / conversion_total) * 100, 1) if conversion_total else 0,
        "ready_to_redeem_count": ready_to_redeem_count,
        "high_balance_count": int(totals[3] or 0),
        "high_balance_no_redemption_count": high_balance_no_redemption_count,
        "monthly_earn_total": int(tx_totals[5] or 0),
        "monthly_conversion_total": int(tx_totals[6] or 0),
        "monthly_redemption_total": monthly_redemption_total,
        "redemption_by_category": sorted(by_category.values(), key=lambda item: int(item["amount"]), reverse=True)[:8],
        "top_redemption_items": sorted(by_sku.values(), key=lambda item: int(item["amount"]), reverse=True)[:8],
        "business_impact": {
            "referral_orders_count": int(commission_totals[0] or 0),
            "referral_turnover_kopecks": referral_turnover_kopecks,
            "referral_commission_kopecks": int(commission_totals[2] or 0),
            "referral_partner_count": int(commission_totals[3] or 0),
            "referral_customer_count": int(commission_totals[4] or 0),
            "glm_linked_partner_count": int(glm_linked_totals[0] or 0),
            "glm_linked_turnover_kopecks": glm_linked_turnover_kopecks,
            "glm_linked_commission_kopecks": int(glm_linked_totals[2] or 0),
            "glm_linked_turnover_percent": round((glm_linked_turnover_kopecks / referral_turnover_kopecks) * 100, 1) if referral_turnover_kopecks else 0,
            "repeat_referral_customer_count": len(repeat_referee_rows),
            "repeat_referral_orders_count": repeat_referral_orders_count,
            "repeat_referral_turnover_kopecks": repeat_referral_turnover_kopecks,
        },
        "top_referral_turnover_partners": [
            {
                "member_id": str(member_id),
                "partner_name": partner_name or "Партнер GLAME",
                "partner_phone": partner_phone,
                "orders_count": int(orders_count or 0),
                "turnover_kopecks": int(turnover_kopecks or 0),
                "commission_kopecks": int(commission_kopecks or 0),
                "glm_balance": int(glm_balance or 0),
                "glm_hold_balance": int(glm_hold_balance or 0),
                "glm_lifetime_earned": int(glm_lifetime_earned or 0),
            }
            for (
                member_id,
                partner_name,
                partner_phone,
                orders_count,
                turnover_kopecks,
                commission_kopecks,
                glm_balance,
                glm_hold_balance,
                glm_lifetime_earned,
            ) in top_referral_rows
        ],
    }


async def _glm_refund_candidate_items(db: AsyncSession, *, limit: int) -> list[dict[str, Any]]:
    commission_rows = (
        await db.execute(
            select(ReferralCommission, ReferralProgramMember, User, GlameTokenTransaction)
            .join(ReferralProgramMember, ReferralProgramMember.id == ReferralCommission.referrer_member_id)
            .join(User, User.id == ReferralProgramMember.user_id)
            .outerjoin(
                GlameTokenTransaction,
                and_(
                    GlameTokenTransaction.referral_commission_id == ReferralCommission.id,
                    GlameTokenTransaction.token_code == "GLM",
                    GlameTokenTransaction.transaction_type == "earn",
                ),
            )
            .where(ReferralCommission.status != "canceled")
            .order_by(desc(ReferralCommission.created_at))
            .limit(limit * 3)
        )
    ).all()

    order_ids = [commission.order_id for commission, *_ in commission_rows if commission.order_id]
    purchase_ids = [commission.purchase_id for commission, *_ in commission_rows if commission.purchase_id]
    orders_by_id: dict[str, Order] = {}
    purchases_by_id: dict[str, PurchaseHistory] = {}
    if order_ids:
        orders = (await db.execute(select(Order).where(Order.id.in_(order_ids)))).scalars().all()
        orders_by_id = {str(order.id): order for order in orders}
    if purchase_ids:
        purchases = (await db.execute(select(PurchaseHistory).where(PurchaseHistory.id.in_(purchase_ids)))).scalars().all()
        purchases_by_id = {str(purchase.id): purchase for purchase in purchases}

    candidates: list[dict[str, Any]] = []
    for commission, member, user, glm_tx in commission_rows:
        signals: list[str] = []
        severity = "review"
        order = orders_by_id.get(str(commission.order_id)) if commission.order_id else None
        purchase = purchases_by_id.get(str(commission.purchase_id)) if commission.purchase_id else None

        if order is not None and str(order.status or "").lower() in {"canceled", "cancelled", "refunded", "returned"}:
            signals.append(f"order_status:{order.status}")
            severity = "high"
        if purchase is not None and int(purchase.total_amount or 0) <= 0:
            signals.append("purchase_amount_non_positive")
            severity = "high"
        if purchase is not None and int(purchase.quantity or 0) <= 0:
            signals.append("purchase_quantity_non_positive")
            severity = "high"
        purchase_meta = purchase.sync_metadata if purchase is not None and isinstance(purchase.sync_metadata, dict) else {}
        purchase_meta_text = json.dumps(purchase_meta, ensure_ascii=False).lower() if purchase_meta else ""
        if any(word in purchase_meta_text for word in ["возврат", "return", "refund", "отмена", "cancel"]):
            signals.append("purchase_meta_refund_keyword")
            severity = "high"

        if not signals:
            continue

        auto_apply_eligible = severity == "high"
        candidates.append(
            {
                "commission_id": str(commission.id),
                "member_id": str(member.id),
                "partner_name": user.full_name or "Партнер GLAME",
                "partner_phone": user.phone,
                "commission_status": commission.status,
                "commission_base": int(commission.commission_base or 0),
                "commission_amount_kopecks": int(commission.amount_kopecks or 0),
                "points": int(commission.points or 0),
                "reward_mode": commission.reward_mode,
                "order_id": str(commission.order_id) if commission.order_id else None,
                "order_status": order.status if order is not None else None,
                "purchase_id": str(commission.purchase_id) if commission.purchase_id else None,
                "purchase_total_amount": int(purchase.total_amount or 0) if purchase is not None else None,
                "purchase_quantity": int(purchase.quantity or 0) if purchase is not None else None,
                "glm_amount": int(glm_tx.amount or 0) if glm_tx is not None else 0,
                "glm_status": glm_tx.status if glm_tx is not None else None,
                "signals": signals,
                "severity": severity,
                "auto_apply_eligible": auto_apply_eligible,
                "created_at": commission.created_at.isoformat() if commission.created_at else None,
            }
        )
        if len(candidates) >= limit:
            break

    return candidates


@router.get("/admin/glm-refund-candidates")
async def admin_glm_refund_candidates(
    limit: int = Query(default=100, ge=1, le=300),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    candidates = await _glm_refund_candidate_items(db, limit=limit)
    return {
        "status": "success",
        "count": len(candidates),
        "candidates": candidates,
        "policy": "review candidates first, then cancel commission to create GLM reversal",
    }


@router.post("/admin/glm-refund-candidates/auto-apply")
async def admin_auto_apply_glm_refund_candidates(
    payload: AdminGlmRefundAutoApplyRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    candidates = [
        item
        for item in await _glm_refund_candidate_items(db, limit=payload.limit)
        if item.get("auto_apply_eligible")
    ][: payload.limit]
    planned = [
        {
            "commission_id": item["commission_id"],
            "member_id": item["member_id"],
            "partner_name": item.get("partner_name"),
            "glm_amount": item.get("glm_amount", 0),
            "signals": item.get("signals", []),
        }
        for item in candidates
    ]
    if payload.dry_run:
        return {
            "status": "dry_run",
            "dry_run": True,
            "planned_count": len(planned),
            "applied_count": 0,
            "planned": planned,
        }

    applied: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    token_service = GlameTokenService(db)
    for item in candidates:
        try:
            commission_id = UUID(str(item["commission_id"]))
            commission = (
                await db.execute(
                    select(ReferralCommission).where(
                        ReferralCommission.id == commission_id,
                        ReferralCommission.status != "canceled",
                    )
                )
            ).scalar_one_or_none()
            if commission is None:
                errors.append({"commission_id": item["commission_id"], "error": "commission_not_found_or_canceled"})
                continue
            reversal = await token_service.cancel_referral_commission_glm(
                commission=commission,
                admin_user_id=current_user.id,
                reason="auto_refund_candidate",
                comment=payload.comment or "Auto-apply GLM refund candidate",
            )
            applied.append(
                {
                    "commission_id": item["commission_id"],
                    "member_id": item["member_id"],
                    "glm_amount": item.get("glm_amount", 0),
                    "signals": item.get("signals", []),
                    "reversal": reversal,
                }
            )
        except Exception as error:
            errors.append({"commission_id": item.get("commission_id"), "error": str(error)})

    await db.commit()
    return {
        "status": "success",
        "dry_run": False,
        "planned_count": len(planned),
        "applied_count": len(applied),
        "error_count": len(errors),
        "applied": applied,
        "errors": errors,
    }


@router.get("/admin/glm-segments")
async def admin_glm_segments(
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(GlameTokenAccount, ReferralProgramMember, User)
            .join(ReferralProgramMember, ReferralProgramMember.id == GlameTokenAccount.referral_member_id)
            .join(User, User.id == ReferralProgramMember.user_id)
            .where(GlameTokenAccount.token_code == "GLM")
            .order_by((GlameTokenAccount.balance + GlameTokenAccount.hold_balance).desc())
        )
    ).all()
    redemption_rows = (
        await db.execute(
            select(
                GlameTokenTransaction.account_id,
                func.count(GlameTokenTransaction.id),
                func.coalesce(func.sum(GlameTokenTransaction.amount), 0),
            )
            .where(GlameTokenTransaction.transaction_type == "redemption")
            .group_by(GlameTokenTransaction.account_id)
        )
    ).all()
    conversion_rows = (
        await db.execute(
            select(
                GlameTokenTransaction.account_id,
                func.coalesce(func.sum(GlameTokenTransaction.amount), 0),
            )
            .where(
                GlameTokenTransaction.transaction_type == "conversion",
                GlameTokenTransaction.status == "available",
            )
            .group_by(GlameTokenTransaction.account_id)
        )
    ).all()
    redemptions = {str(account_id): {"count": int(count or 0), "amount": abs(int(amount or 0))} for account_id, count, amount in redemption_rows}
    conversions = {str(account_id): int(amount or 0) for account_id, amount in conversion_rows}

    segments = {
        "ready_to_redeem": {
            "title": "Готовы использовать GLM",
            "description": "Есть доступный GLM для онлайн-покупок, GLM Store, сервисов или bridge в баллы 1С.",
            "items": [],
        },
        "near_next_tier": {
            "title": "Близко к следующему уровню",
            "description": "До следующего GLM-статуса осталось не больше 1 000 GLM.",
            "items": [],
        },
        "high_balance_no_redemption": {
            "title": "Высокий баланс без использования",
            "description": "Накопили GLM, но еще не тратили на товары или сервисы.",
            "items": [],
        },
        "bonus_converters": {
            "title": "Points→GLM bridge",
            "description": "Пользователи, которые уже перевели бонусные баллы в GLM.",
            "items": [],
        },
    }

    for account, member, user in rows:
        account_id = str(account.id)
        balance = int(account.balance or 0)
        hold_balance = int(account.hold_balance or 0)
        burned = int(account.lifetime_burned or 0)
        privilege_score = max(0, int(account.lifetime_earned or 0) - burned)
        tier = GlameTokenService.tier_payload(privilege_score)
        item = {
            "member_id": str(member.id),
            "partner_name": user.full_name or "Партнер GLAME",
            "partner_phone": user.phone,
            "balance": balance,
            "hold_balance": hold_balance,
            "privilege_score": privilege_score,
            "tier": (tier.get("privilege_tier") or {}).get("name"),
            "next_tier": (tier.get("next_privilege_tier") or {}).get("name") if tier.get("next_privilege_tier") else None,
            "to_next": int(tier.get("privilege_to_next") or 0),
            "redemption_total": redemptions.get(account_id, {}).get("amount", 0),
            "redemption_count": redemptions.get(account_id, {}).get("count", 0),
            "converted_total": conversions.get(account_id, 0),
        }
        if balance >= 800:
            segments["ready_to_redeem"]["items"].append(item)
        if item["next_tier"] and 0 < item["to_next"] <= 1000:
            segments["near_next_tier"]["items"].append(item)
        if balance >= 5000 and item["redemption_count"] == 0:
            segments["high_balance_no_redemption"]["items"].append(item)
        if item["converted_total"] > 0:
            segments["bonus_converters"]["items"].append(item)

    return {
        "segments": [
            {
                "code": code,
                "title": payload["title"],
                "description": payload["description"],
                "count": len(payload["items"]),
                "items": payload["items"][:20],
            }
            for code, payload in segments.items()
        ],
    }


async def _bonus_expiry_audience_items(db: AsyncSession, *, days: int, limit: int) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=days)
    rows = (
        await db.execute(
            select(
                User.id,
                User.full_name,
                User.phone,
                User.email,
                User.loyalty_points,
                func.coalesce(func.sum(LoyaltyTransaction.points), 0).label("expiring_points"),
                func.min(LoyaltyTransaction.expires_at).label("nearest_expiry"),
                func.count(LoyaltyTransaction.id).label("lots_count"),
            )
            .join(User, User.id == LoyaltyTransaction.user_id)
            .where(
                LoyaltyTransaction.points > 0,
                LoyaltyTransaction.expires_at.is_not(None),
                LoyaltyTransaction.expires_at >= now,
                LoyaltyTransaction.expires_at <= until,
            )
            .group_by(User.id, User.full_name, User.phone, User.email, User.loyalty_points)
            .order_by(func.min(LoyaltyTransaction.expires_at).asc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "user_id": str(user_id),
            "full_name": full_name or "Клиент GLAME",
            "phone": phone,
            "email": email,
            "loyalty_points": int(loyalty_points or 0),
            "expiring_points": int(expiring_points or 0),
            "nearest_expiry": nearest_expiry.isoformat() if nearest_expiry else None,
            "lots_count": int(lots_count or 0),
            "campaign_message": (
                f"У вас скоро истекает до {int(expiring_points or 0)} бонусных баллов GLAME. "
                "Вы можете перевести их в GLM через CryptoGLAME до сгорания, хранить GLM отдельно, "
                "а перед покупкой вернуть GLM в баллы по правилам bridge."
            ),
        }
        for user_id, full_name, phone, email, loyalty_points, expiring_points, nearest_expiry, lots_count in rows
    ]


@router.get("/admin/bonus-expiry-audience")
async def admin_bonus_expiry_audience(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=300),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    return {
        "days": days,
        "items": await _bonus_expiry_audience_items(db, days=days, limit=limit),
    }


@router.get("/admin/bonus-expiry-audience.csv")
async def admin_bonus_expiry_audience_csv(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=300, ge=1, le=1000),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    items = await _bonus_expiry_audience_items(db, days=days, limit=limit)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "user_id",
            "full_name",
            "phone",
            "email",
            "loyalty_points",
            "expiring_points",
            "nearest_expiry",
            "lots_count",
            "campaign_message",
        ],
    )
    writer.writeheader()
    writer.writerows(items)
    filename = f"bonus-expiry-glm-{days}d.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/admin/bonus-expiry-drafts")
async def admin_create_bonus_expiry_drafts(
    payload: BonusExpiryDraftRequest,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    items = await _bonus_expiry_audience_items(db, days=payload.days, limit=payload.limit)
    generation_id = f"bonus-expiry-glm-{payload.days}d"
    created_count = 0
    skipped_count = 0
    for item in items:
        try:
            user_id = UUID(str(item["user_id"]))
        except Exception:
            skipped_count += 1
            continue
        message_id = uuid5(
            UUID("7a30bdc0-9a4a-4e2d-92eb-d6c70b4dbed6"),
            f"{generation_id}:{item['user_id']}:{item.get('nearest_expiry') or ''}",
        )
        existing = (
            await db.execute(select(CustomerMessage.id).where(CustomerMessage.id == message_id))
        ).scalar_one_or_none()
        if existing:
            skipped_count += 1
            continue
        db.add(
            CustomerMessage(
                id=message_id,
                user_id=user_id,
                message=item["campaign_message"],
                cta="Перевести баллы в GLM",
                segment="bonus_expiry_points_to_glm",
                event_type="bonus_expiry_points_to_glm",
                event_brand="GLAME",
                payload={
                    **item,
                    "bridge_type": "points_to_glm",
                    "cta_url": "/referral?section=crypto-glame&bridge=points_to_glm",
                    "message_kind": "broadcast",
                    "generation_id": generation_id,
                    "source": "referral_admin_bonus_expiry",
                    "days": payload.days,
                },
                status="new",
            )
        )
        created_count += 1
    await db.commit()
    return {
        "status": "success",
        "generation_id": generation_id,
        "created_count": created_count,
        "skipped_count": skipped_count,
        "total": len(items),
    }


@router.get("/admin/glm-transactions")
async def admin_list_glm_transactions(
    type_filter: str | None = Query(default=None, alias="type"),
    status_filter: str | None = Query(default=None, alias="status"),
    member_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(GlameTokenTransaction, ReferralProgramMember, User)
        .outerjoin(ReferralProgramMember, ReferralProgramMember.id == GlameTokenTransaction.referral_member_id)
        .outerjoin(User, User.id == ReferralProgramMember.user_id)
        .where(GlameTokenTransaction.token_code == "GLM")
        .order_by(desc(GlameTokenTransaction.created_at))
        .offset(offset)
        .limit(limit)
    )
    count_stmt = select(func.count(GlameTokenTransaction.id)).where(GlameTokenTransaction.token_code == "GLM")
    if type_filter:
        stmt = stmt.where(GlameTokenTransaction.transaction_type == type_filter)
        count_stmt = count_stmt.where(GlameTokenTransaction.transaction_type == type_filter)
    if status_filter:
        stmt = stmt.where(GlameTokenTransaction.status == status_filter)
        count_stmt = count_stmt.where(GlameTokenTransaction.status == status_filter)
    if member_id:
        stmt = stmt.where(GlameTokenTransaction.referral_member_id == member_id)
        count_stmt = count_stmt.where(GlameTokenTransaction.referral_member_id == member_id)
    rows = (await db.execute(stmt)).all()
    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    return {
        "transactions": [_glm_transaction_payload(tx, member, user) for tx, member, user in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/admin/glm-claims")
async def admin_list_glm_claims(
    status_filter: str | None = Query(default="pending", alias="status"),
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(GlameTokenTransaction, ReferralProgramMember, User, GlameTokenBridgeOperation)
        .join(ReferralProgramMember, ReferralProgramMember.id == GlameTokenTransaction.referral_member_id)
        .join(User, User.id == ReferralProgramMember.user_id)
        .outerjoin(GlameTokenBridgeOperation, GlameTokenBridgeOperation.transaction_id == GlameTokenTransaction.id)
        .where(GlameTokenTransaction.transaction_type == "claim")
        .order_by(desc(GlameTokenTransaction.created_at))
        .offset(offset)
        .limit(limit)
    )
    count_stmt = select(func.count(GlameTokenTransaction.id)).where(
        GlameTokenTransaction.transaction_type == "claim"
    )
    if status_filter:
        stmt = stmt.where(GlameTokenTransaction.status == status_filter)
        count_stmt = count_stmt.where(GlameTokenTransaction.status == status_filter)
    rows = (await db.execute(stmt)).all()
    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    return {
        "claims": [_glm_claim_payload(tx, member, user, operation) for tx, member, user, operation in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/admin/glm-ton-readiness")
async def admin_glm_ton_readiness(
    request: Request,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    pending_points_to_ton_conditions = [
        GlameTokenTransaction.transaction_type == "claim",
        GlameTokenTransaction.status == "pending",
        GlameTokenTransaction.reason == "points_to_ton_bridge",
    ]
    pending_claim_count = int(
        (
            await db.execute(
                select(func.count(GlameTokenTransaction.id)).where(*pending_points_to_ton_conditions)
            )
        ).scalar_one()
        or 0
    )
    pending_claim_total = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(GlameTokenTransaction.amount), 0)).where(*pending_points_to_ton_conditions)
            )
        ).scalar_one()
        or 0
    )
    pending_claim_rows = (
        await db.execute(
            select(GlameTokenTransaction)
            .where(*pending_points_to_ton_conditions)
            .order_by(GlameTokenTransaction.created_at.asc(), GlameTokenTransaction.id.asc())
            .limit(1000)
        )
    ).scalars().all()
    auto_transfer_status_counts: dict[str, int] = {}
    auto_transfer_amounts_by_status: dict[str, int] = {}
    pending_claim_samples: list[dict[str, Any]] = []
    now_for_health = datetime.now(timezone.utc)
    auto_transfer_health = {
        "blocked_count": 0,
        "blocked_amount_glm": 0,
        "waiting_settlement_count": 0,
        "waiting_settlement_amount_glm": 0,
        "not_started_count": 0,
        "not_started_amount_glm": 0,
        "oldest_pending_age_minutes": 0,
        "oldest_pending_created_at": None,
        "needs_attention": False,
    }
    for tx in pending_claim_rows:
        meta = tx.meta if isinstance(tx.meta, dict) else {}
        auto_transfer = meta.get("ton_auto_transfer") if isinstance(meta.get("ton_auto_transfer"), dict) else {}
        auto_status = str(auto_transfer.get("status") or "not_started")
        amount = int(tx.amount or 0)
        auto_transfer_status_counts[auto_status] = auto_transfer_status_counts.get(auto_status, 0) + 1
        auto_transfer_amounts_by_status[auto_status] = auto_transfer_amounts_by_status.get(auto_status, 0) + amount
        if auto_status.startswith("blocked_"):
            auto_transfer_health["blocked_count"] += 1
            auto_transfer_health["blocked_amount_glm"] += amount
        elif auto_status == "sent_waiting_settlement":
            auto_transfer_health["waiting_settlement_count"] += 1
            auto_transfer_health["waiting_settlement_amount_glm"] += amount
        elif auto_status in {"not_started", "disabled"}:
            auto_transfer_health["not_started_count"] += 1
            auto_transfer_health["not_started_amount_glm"] += amount
        if tx.created_at:
            created_at = tx.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age_minutes = max(0, int((now_for_health - created_at).total_seconds() // 60))
            if age_minutes > int(auto_transfer_health["oldest_pending_age_minutes"] or 0):
                auto_transfer_health["oldest_pending_age_minutes"] = age_minutes
                auto_transfer_health["oldest_pending_created_at"] = created_at.isoformat()
        if len(pending_claim_samples) < 10:
            pending_claim_samples.append({
                "id": str(tx.id),
                "amount_glm": amount,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
                "onec_spend_sync_status": meta.get("onec_spend_sync_status"),
                "auto_transfer_status": auto_status,
                "auto_transfer_error": auto_transfer.get("error"),
                "tx_hash": auto_transfer.get("tx_hash") or meta.get("tx_hash"),
            })
    auto_transfer_health["needs_attention"] = bool(
        auto_transfer_health["blocked_count"]
        or auto_transfer_health["waiting_settlement_count"]
        or int(auto_transfer_health["oldest_pending_age_minutes"] or 0) >= 60
    )
    pending_glm_to_points_conditions = [
        GlameTokenTransaction.transaction_type == "bridge",
        GlameTokenTransaction.status == "pending",
        GlameTokenTransaction.reason.in_(("glm_to_points_bridge", "buy_loyalty_points")),
    ]
    pending_glm_to_points_rows = (
        await db.execute(
            select(GlameTokenTransaction)
            .where(*pending_glm_to_points_conditions)
            .order_by(GlameTokenTransaction.created_at.asc(), GlameTokenTransaction.id.asc())
            .limit(1000)
        )
    ).scalars().all()
    deposit_status_counts: dict[str, int] = {}
    deposit_amounts_by_status: dict[str, int] = {}
    pending_glm_to_points_samples: list[dict[str, Any]] = []
    pending_glm_to_points_total = 0
    glm_to_points_health = {
        "waiting_deposit_count": 0,
        "waiting_deposit_amount_glm": 0,
        "tx_found_count": 0,
        "tx_found_amount_glm": 0,
        "onec_issue_count": 0,
        "onec_issue_amount_glm": 0,
        "oldest_pending_age_minutes": 0,
        "oldest_pending_created_at": None,
        "needs_attention": False,
    }
    deposit_waiting_statuses = {"not_started", "wallet_request_prepared", "waiting_for_deposit", "not_found"}
    onec_issue_statuses = {"failed", "ready_for_1c", "created_without_ref_key", "posted_without_balance_change"}
    for tx in pending_glm_to_points_rows:
        meta = tx.meta if isinstance(tx.meta, dict) else {}
        deposit_status = str(meta.get("ton_deposit_status") or ("tx_hash_present" if meta.get("deposit_tx_hash") else "not_started"))
        onec_status = str(meta.get("onec_sync_status") or "")
        amount = abs(int(tx.amount or 0))
        pending_glm_to_points_total += amount
        deposit_status_counts[deposit_status] = deposit_status_counts.get(deposit_status, 0) + 1
        deposit_amounts_by_status[deposit_status] = deposit_amounts_by_status.get(deposit_status, 0) + amount
        if deposit_status in deposit_waiting_statuses:
            glm_to_points_health["waiting_deposit_count"] += 1
            glm_to_points_health["waiting_deposit_amount_glm"] += amount
        if deposit_status in {"tx_hash_present", "verified"} or meta.get("deposit_tx_hash"):
            glm_to_points_health["tx_found_count"] += 1
            glm_to_points_health["tx_found_amount_glm"] += amount
        if onec_status in onec_issue_statuses:
            glm_to_points_health["onec_issue_count"] += 1
            glm_to_points_health["onec_issue_amount_glm"] += amount
        if tx.created_at:
            created_at = tx.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age_minutes = max(0, int((now_for_health - created_at).total_seconds() // 60))
            if age_minutes > int(glm_to_points_health["oldest_pending_age_minutes"] or 0):
                glm_to_points_health["oldest_pending_age_minutes"] = age_minutes
                glm_to_points_health["oldest_pending_created_at"] = created_at.isoformat()
        if len(pending_glm_to_points_samples) < 10:
            pending_glm_to_points_samples.append({
                "id": str(tx.id),
                "amount_glm": amount,
                "target_points": meta.get("target_points"),
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
                "ton_deposit_status": deposit_status,
                "deposit_tx_hash": meta.get("deposit_tx_hash"),
                "expected_ton_sender_address": meta.get("expected_ton_sender_address"),
                "treasury_address": meta.get("treasury_address"),
                "last_lookup_status": (meta.get("ton_deposit_last_lookup") or {}).get("status") if isinstance(meta.get("ton_deposit_last_lookup"), dict) else None,
                "onec_sync_status": meta.get("onec_sync_status"),
            })
    glm_to_points_health["needs_attention"] = bool(
        glm_to_points_health["tx_found_count"]
        or glm_to_points_health["onec_issue_count"]
        or int(glm_to_points_health["oldest_pending_age_minutes"] or 0) >= 60
    )
    bridge_operation_rows = (
        await db.execute(
            select(
                GlameTokenBridgeOperation.direction,
                GlameTokenBridgeOperation.status,
                func.count(GlameTokenBridgeOperation.id),
                func.coalesce(func.sum(GlameTokenBridgeOperation.glm_amount), 0),
            )
            .where(GlameTokenBridgeOperation.token_code == "GLM")
            .group_by(GlameTokenBridgeOperation.direction, GlameTokenBridgeOperation.status)
        )
    ).all()
    bridge_operations_summary: dict[str, Any] = {
        "count": 0,
        "amount_glm": 0,
        "by_direction": {},
        "by_status": {},
    }
    for direction, status, count, amount in bridge_operation_rows:
        count_int = int(count or 0)
        amount_int = int(amount or 0)
        direction_key = str(direction or "unknown")
        status_key = str(status or "unknown")
        bridge_operations_summary["count"] += count_int
        bridge_operations_summary["amount_glm"] += amount_int
        direction_bucket = bridge_operations_summary["by_direction"].setdefault(direction_key, {"count": 0, "amount_glm": 0, "statuses": {}})
        direction_bucket["count"] += count_int
        direction_bucket["amount_glm"] += amount_int
        direction_bucket["statuses"][status_key] = {
            "count": count_int,
            "amount_glm": amount_int,
        }
        status_bucket = bridge_operations_summary["by_status"].setdefault(status_key, {"count": 0, "amount_glm": 0})
        status_bucket["count"] += count_int
        status_bucket["amount_glm"] += amount_int
    legacy_bridge_transaction_ids = (
        select(GlameTokenTransaction.id)
        .where(
            GlameTokenTransaction.token_code == "GLM",
            or_(
                and_(
                    GlameTokenTransaction.transaction_type == "bridge",
                    GlameTokenTransaction.reason.in_(("glm_to_points_bridge", "buy_loyalty_points")),
                ),
                and_(
                    GlameTokenTransaction.transaction_type.in_(("claim", "conversion")),
                    GlameTokenTransaction.reason.in_(("points_to_ton_bridge", "points_to_glm_bridge")),
                ),
            ),
        )
    )
    bridge_operations_summary["missing_domain_count"] = int(
        (
            await db.execute(
                select(func.count(GlameTokenTransaction.id))
                .where(
                    GlameTokenTransaction.id.in_(legacy_bridge_transaction_ids),
                    ~GlameTokenTransaction.id.in_(select(GlameTokenBridgeOperation.transaction_id)),
                )
            )
        ).scalar_one()
        or 0
    )
    bridge_operation_stale_minutes = int(os.getenv("TON_GLM_BRIDGE_DOMAIN_STALE_MINUTES", "60") or 60)
    bridge_operation_stale_before = now_for_health - timedelta(minutes=max(1, bridge_operation_stale_minutes))
    bridge_operation_health_rows = (
        await db.execute(
            select(GlameTokenBridgeOperation)
            .where(GlameTokenBridgeOperation.token_code == "GLM")
            .order_by(desc(GlameTokenBridgeOperation.updated_at), desc(GlameTokenBridgeOperation.created_at))
            .limit(500)
        )
    ).scalars().all()
    bridge_operations_health: dict[str, Any] = {
        "needs_attention": False,
        "stale_pending_count": 0,
        "stale_pending_amount_glm": 0,
        "ton_waiting_count": 0,
        "ton_waiting_amount_glm": 0,
        "onec_issue_count": 0,
        "onec_issue_amount_glm": 0,
        "domain_gap_count": int(bridge_operations_summary.get("missing_domain_count") or 0),
        "oldest_pending_age_minutes": 0,
        "oldest_pending_created_at": None,
        "sample": [],
    }
    bridge_ton_waiting_statuses = {
        "sent",
        "sent_waiting_settlement",
        "wallet_request_prepared",
        "waiting_for_deposit",
        "not_found",
    }
    bridge_onec_issue_statuses = {
        "failed",
        "missing_discount_card",
        "ready_for_1c",
        "ready_for_1c_spend",
        "posted_without_balance_change",
        "created_without_ref_key",
    }
    for operation in bridge_operation_health_rows:
        amount = int(operation.glm_amount or 0)
        requested_at = operation.requested_at or operation.created_at
        if requested_at and requested_at.tzinfo is None:
            requested_at = requested_at.replace(tzinfo=timezone.utc)
        age_minutes = 0
        if requested_at:
            age_minutes = max(0, int((now_for_health - requested_at).total_seconds() // 60))
        is_stale_pending = operation.status == "pending" and requested_at is not None and requested_at < bridge_operation_stale_before
        is_ton_waiting = operation.status == "pending" and str(operation.ton_status or "") in bridge_ton_waiting_statuses
        is_onec_issue = operation.status not in {"canceled", "superseded"} and str(operation.onec_status or "") in bridge_onec_issue_statuses
        if is_stale_pending:
            bridge_operations_health["stale_pending_count"] += 1
            bridge_operations_health["stale_pending_amount_glm"] += amount
            if age_minutes > int(bridge_operations_health["oldest_pending_age_minutes"] or 0):
                bridge_operations_health["oldest_pending_age_minutes"] = age_minutes
                bridge_operations_health["oldest_pending_created_at"] = requested_at.isoformat() if requested_at else None
        if is_ton_waiting:
            bridge_operations_health["ton_waiting_count"] += 1
            bridge_operations_health["ton_waiting_amount_glm"] += amount
        if is_onec_issue:
            bridge_operations_health["onec_issue_count"] += 1
            bridge_operations_health["onec_issue_amount_glm"] += amount
        if (is_stale_pending or is_ton_waiting or is_onec_issue) and len(bridge_operations_health["sample"]) < 10:
            bridge_operations_health["sample"].append({
                "id": str(operation.id),
                "transaction_id": str(operation.transaction_id),
                "direction": operation.direction,
                "status": operation.status,
                "glm_amount": amount,
                "points_amount": int(operation.points_amount or 0),
                "ton_status": operation.ton_status,
                "ton_tx_hash": operation.ton_tx_hash,
                "onec_status": operation.onec_status,
                "requested_at": requested_at.isoformat() if requested_at else None,
                "age_minutes": age_minutes,
            })
    bridge_operations_health["needs_attention"] = bool(
        bridge_operations_health["domain_gap_count"]
        or bridge_operations_health["stale_pending_count"]
        or bridge_operations_health["ton_waiting_count"]
        or bridge_operations_health["onec_issue_count"]
    )
    policy = GlameTokenService.policy_payload().get("onchain_policy") or {}
    artifact = _glm_ton_deployment_artifact()
    reference = _glm_ton_reference_status()
    artifact_data = artifact.get("data") if isinstance(artifact.get("data"), dict) else {}
    blueprint = _glm_ton_blueprint_status(reference, artifact_data, policy)
    build_status = _glm_ton_build_status(reference)
    artifact_contracts = artifact_data.get("contracts") if isinstance(artifact_data.get("contracts"), dict) else {}
    artifact_deployment = artifact_data.get("deployment") if isinstance(artifact_data.get("deployment"), dict) else {}
    settlement_config = TonGlmSettlementService.config_payload()
    auto_transfer_config = TonGlmAutoTransferService.config_payload()
    treasury_balances = await TonGlmTreasuryBalanceService(db).payload()
    wallet_cache_propagation = await _glm_wallet_cache_propagation_payload(policy)
    treasury_alert_codes = [
        str(item.get("code"))
        for item in (treasury_balances.get("alerts") or [])
        if isinstance(item, dict) and item.get("code")
    ]
    treasury_alert_state = GlmTelegramAlertService.state_summary(treasury_alert_codes)
    treasury_balances["telegram_alert_state"] = treasury_alert_state
    settlement_checks = [
        {
            "code": "settlement_lookup_addresses",
            "ok": bool(settlement_config.get("lookup_addresses")),
            "message": "TON_GLM_SETTLEMENT_LOOKUP_ADDRESSES нужен для auto-settlement проверки tx hash",
        },
        {
            "code": "settlement_admin_user",
            "ok": bool((os.getenv("TON_GLM_SETTLEMENT_ADMIN_USER_ID") or "").strip()),
            "message": "TON_GLM_SETTLEMENT_ADMIN_USER_ID нужен, чтобы background watcher мог закрывать claim с audit trail",
        },
        {
            "code": "settlement_watcher_enabled",
            "ok": bool(settlement_config.get("enabled")),
            "message": "TON_GLM_SETTLEMENT_WATCHER_ENABLED включает background auto-settlement; manual endpoint доступен и без него",
        },
        {
            "code": "auto_transfer_enabled",
            "ok": bool(auto_transfer_config.get("enabled")),
            "message": "TON_GLM_AUTO_TRANSFER_ENABLED включает автоматический перевод GLM из hot-wallet после 1С-списания",
        },
        {
            "code": "auto_transfer_hot_wallet",
            "ok": bool(auto_transfer_config.get("has_hot_wallet_mnemonic")),
            "message": "TON_GLM_AUTO_TRANSFER_HOT_WALLET_MNEMONIC нужен для подписи hot-wallet transfer",
        },
        {
            "code": "auto_transfer_admin_user",
            "ok": bool(auto_transfer_config.get("admin_user_id")),
            "message": "TON_GLM_AUTO_TRANSFER_ADMIN_USER_ID или TON_GLM_SETTLEMENT_ADMIN_USER_ID нужен для audit trail",
        },
    ]
    wallet_by_role = {
        str(item.get("role")): item
        for item in (treasury_balances.get("wallets") or [])
        if isinstance(item, dict)
    }
    hot_wallet_balance = wallet_by_role.get("hot_wallet") or {}
    treasury_balance = wallet_by_role.get("treasury") or {}
    settlement_checks.extend(
        [
            {
                "code": "hot_wallet_glm_balance",
                "ok": hot_wallet_balance.get("status") in {"ok", "warning"},
                "message": "Hot-wallet должен иметь GLM для auto-transfer pending заявок.",
            },
            {
                "code": "hot_wallet_ton_gas",
                "ok": hot_wallet_balance.get("status") in {"ok", "warning"},
                "message": "Hot-wallet должен иметь TON gas для отправки Jetton transfer.",
            },
            {
                "code": "treasury_glm_balance",
                "ok": treasury_balance.get("status") in {"ok", "warning"},
                "message": "Treasury/deposit address должен читаться по GLM Jetton balance.",
            },
            {
                "code": "treasury_ton_gas",
                "ok": treasury_balance.get("status") in {"ok", "warning"},
                "message": "Treasury/deposit address должен читаться по TON gas balance.",
            },
        ]
    )
    mainnet_enabled = bool(policy.get("mainnet_enabled"))
    network = str(policy.get("network") or "testnet").strip() or "testnet"
    hot_wallet_secret_source = str(auto_transfer_config.get("secret_source") or "none")
    hot_wallet_address = str(auto_transfer_config.get("hot_wallet_address") or "").strip()
    active_hot_wallet_address = str(auto_transfer_config.get("active_hot_wallet_address") or "").strip()
    production_hot_wallet_address = str(auto_transfer_config.get("production_hot_wallet_address") or "").strip()
    production_treasury_address = str(auto_transfer_config.get("production_treasury_address") or "").strip()
    production_signer_mode = str(auto_transfer_config.get("production_signer_mode") or "not_configured").strip()
    production_safe_signer = bool(auto_transfer_config.get("production_safe_signer"))
    auto_transfer_signer_ready = bool(
        production_safe_signer if network == "mainnet" else auto_transfer_config.get("has_hot_wallet_mnemonic")
    )
    security_warnings = []
    mainnet_blockers = []
    if hot_wallet_secret_source == "env_mnemonic":
        security_warnings.append({
            "code": "hot_wallet_env_mnemonic",
            "severity": "pilot_warning",
            "message": "Testnet hot-wallet signer хранится как mnemonic в env. Это допустимо только для testnet-пилота; production/mainnet должен использовать отдельный secret manager/external signer.",
        })
        if not production_safe_signer:
            mainnet_blockers.append({
                "code": "hot_wallet_env_mnemonic",
                "message": "Mainnet запрещен, пока production signer не вынесен из backend env в KMS/Vault/external signer.",
            })
    if auto_transfer_config.get("enabled") and not active_hot_wallet_address:
        mainnet_blockers.append({
            "code": "hot_wallet_address_missing",
            "message": "Для auto-transfer должен быть задан активный hot-wallet address: testnet TON_GLM_AUTO_TRANSFER_HOT_WALLET_ADDRESS или mainnet TON_GLM_PRODUCTION_HOT_WALLET_ADDRESS.",
        })
    if not production_hot_wallet_address:
        mainnet_blockers.append({
            "code": "production_hot_wallet_missing",
            "message": "Для mainnet нужен отдельный production hot-wallet address без seed-фразы в env.",
        })
    if not production_treasury_address:
        mainnet_blockers.append({
            "code": "production_treasury_missing",
            "message": "Для mainnet нужен production treasury/bank wallet address, куда минтится основной банк GLM.",
        })
    if production_hot_wallet_address and not production_safe_signer:
        mainnet_blockers.append({
            "code": "production_signer_missing",
            "message": f"Production hot-wallet address задан, но безопасный signer не подключен: signer_mode={production_signer_mode}, endpoint={bool(auto_transfer_config.get('production_signer_endpoint_configured'))}, token={bool(auto_transfer_config.get('production_signer_auth_configured'))}. Нужен KMS/Vault/external signer endpoint без mnemonic в backend env.",
        })
    if not auto_transfer_config.get("production_legal_approved"):
        mainnet_blockers.append({
            "code": "production_legal_approval_missing",
            "message": "Mainnet запрещен до юридического approval по GLM utility/bridge, оферте, KYC/AML и учету.",
        })
    if not auto_transfer_config.get("production_security_approved"):
        mainnet_blockers.append({
            "code": "production_security_approval_missing",
            "message": "Mainnet запрещен до security review Jetton/treasury/signer workflow.",
        })
    if not auto_transfer_config.get("production_treasury_approved"):
        mainnet_blockers.append({
            "code": "production_treasury_approval_missing",
            "message": "Mainnet запрещен до утверждения treasury policy, лимитов, refill/burn/incident-регламента.",
        })
    if auto_transfer_config.get("daily_limit_glm", 0) > 0 and int(auto_transfer_config.get("daily_limit_glm") or 0) > 50_000:
        security_warnings.append({
            "code": "hot_wallet_daily_limit_high",
            "severity": "warning",
            "message": "Daily cap hot-wallet выше пилотного порога 50 000 GLM; перед расширением пилота нужен treasury approval.",
        })
    if mainnet_enabled and mainnet_blockers:
        security_warnings.append({
            "code": "mainnet_blocked_by_security",
            "severity": "blocker",
            "message": "Mainnet включать нельзя, пока есть security blockers по signer/hot-wallet.",
        })
    env_status = {
        "TON_NETWORK": os.getenv("TON_NETWORK", "testnet"),
        "TON_GLM_JETTON_MASTER_ADDRESS": bool(os.getenv("TON_GLM_JETTON_MASTER_ADDRESS")),
        "TON_GLM_TREASURY_ADDRESS": bool(os.getenv("TON_GLM_TREASURY_ADDRESS")),
        "TON_GLM_METADATA_URL": bool(os.getenv("TON_GLM_METADATA_URL")),
        "TON_GLM_SETTLEMENT_WATCHER_ENABLED": bool(settlement_config.get("enabled")),
        "TON_GLM_SETTLEMENT_LOOKUP_ADDRESSES": bool(settlement_config.get("lookup_addresses")),
        "TON_GLM_SETTLEMENT_ADMIN_USER_ID": bool((os.getenv("TON_GLM_SETTLEMENT_ADMIN_USER_ID") or "").strip()),
        "TON_GLM_AUTO_TRANSFER_ENABLED": bool(auto_transfer_config.get("enabled")),
        "TON_GLM_AUTO_TRANSFER_HOT_WALLET_MNEMONIC": bool(auto_transfer_config.get("has_hot_wallet_mnemonic")),
        "TON_GLM_AUTO_TRANSFER_SIGNER_MODE": auto_transfer_config.get("signer_mode"),
        "TON_GLM_AUTO_TRANSFER_PRODUCTION_SAFE_SIGNER": bool(auto_transfer_config.get("production_safe_signer")),
        "TON_GLM_PRODUCTION_HOT_WALLET_ADDRESS": bool(auto_transfer_config.get("production_hot_wallet_address")),
        "TON_GLM_PRODUCTION_TREASURY_ADDRESS": bool(auto_transfer_config.get("production_treasury_address")),
        "TON_GLM_PRODUCTION_SIGNER_MODE": auto_transfer_config.get("production_signer_mode"),
        "TON_GLM_PRODUCTION_SIGNER_ENDPOINT": bool(auto_transfer_config.get("production_signer_endpoint_configured")),
        "TON_GLM_PRODUCTION_SIGNER_TOKEN": bool(auto_transfer_config.get("production_signer_auth_configured")),
        "TON_GLM_PRODUCTION_LEGAL_APPROVED": bool(auto_transfer_config.get("production_legal_approved")),
        "TON_GLM_PRODUCTION_SECURITY_APPROVED": bool(auto_transfer_config.get("production_security_approved")),
        "TON_GLM_PRODUCTION_TREASURY_APPROVED": bool(auto_transfer_config.get("production_treasury_approved")),
        "TONCENTER_API_KEY": bool(settlement_config.get("has_toncenter_api_key")),
    }
    checks = [
        {
            "code": "network_configured",
            "ok": (policy.get("network") or "testnet") in {"testnet", "mainnet"},
            "message": "TON_NETWORK должен быть testnet или mainnet",
        },
        {
            "code": "metadata_url",
            "ok": bool(policy.get("metadata_url")),
            "message": "Jetton metadata URL должен быть задан",
        },
        {
            "code": "artifact_exists",
            "ok": bool(artifact.get("exists")) and not artifact.get("error"),
            "message": "Deployment artifact должен читаться",
        },
        {
            "code": "reference_lock",
            "ok": bool(reference.get("exists")) and not reference.get("error"),
            "message": "Reference Jetton lock должен читаться",
        },
        {
            "code": "reference_vendor",
            "ok": bool(reference.get("vendor_exists")),
            "message": "Pinned Jetton reference должен быть скачан через npm run reference:fetch",
        },
        {
            "code": "reference_commit",
            "ok": bool(reference.get("matches_lock")),
            "message": "Local Jetton reference checkout должен совпадать с lock commit",
        },
        {
            "code": "blueprint_script",
            "ok": bool(blueprint.get("deploy_script_exists")) and not blueprint.get("error"),
            "message": "GLM Blueprint deploy script должен быть создан через npm run blueprint:prepare",
        },
        {
            "code": "blueprint_metadata",
            "ok": bool(blueprint.get("metadata_matches_script")),
            "message": "Blueprint deploy script должен содержать актуальный GLM metadata URL",
        },
        {
            "code": "blueprint_admin",
            "ok": bool(blueprint.get("admin_matches_script")),
            "message": "Blueprint deploy script должен содержать GLAME testnet admin address",
        },
        {
            "code": "blueprint_mainnet_guard",
            "ok": bool(blueprint.get("mainnet_guard")),
            "message": "Blueprint deploy script должен запрещать mainnet deploy",
        },
        {
            "code": "build_minter",
            "ok": bool(build_status.get("minter_compiled")),
            "message": "JettonMinter должен быть скомпилирован через pinned reference",
        },
        {
            "code": "build_wallet",
            "ok": bool(build_status.get("wallet_compiled")),
            "message": "JettonWallet должен быть скомпилирован через pinned reference",
        },
        {
            "code": "wallet_library_hash",
            "ok": bool(build_status.get("wallet_library_hash")),
            "message": "JettonWallet compiled artifact должен содержать libraryHash",
        },
        {
            "code": "jetton_master_env",
            "ok": bool(policy.get("jetton_master_address")),
            "message": "TON_GLM_JETTON_MASTER_ADDRESS нужен после deploy",
        },
        {
            "code": "treasury_env",
            "ok": bool(policy.get("treasury_address")),
            "message": "TON_GLM_TREASURY_ADDRESS нужен для operator workflow",
        },
        {
            "code": "artifact_deployed",
            "ok": (
                bool(policy.get("jetton_master_address"))
                if (policy.get("network") or "testnet") == "mainnet"
                else artifact_deployment.get("status") == "testnet_deployed"
            ),
            "message": (
                "TON_GLM_JETTON_MASTER_ADDRESS должен указывать на mainnet Jetton master"
                if (policy.get("network") or "testnet") == "mainnet"
                else "glm-jetton.testnet.json должен быть записан через record:deploy после deploy"
            ),
        },
    ]
    runtime_blocker_codes = {"network_configured", "metadata_url", "jetton_master_env", "treasury_env", "artifact_deployed"}
    blockers = [
        item
        for item in checks
        if not item["ok"] and (network != "mainnet" or item["code"] in runtime_blocker_codes)
    ]
    legacy_deploy_blockers = [
        item
        for item in checks
        if not item["ok"] and network == "mainnet" and item["code"] not in runtime_blocker_codes
    ]
    next_steps = []
    if any(item["code"] == "artifact_deployed" for item in blockers):
        next_steps.append("Run contracts/ton/glm-jetton npm run blueprint:prepare with GLAME testnet admin address.")
        next_steps.append("Run contracts/ton/glm-jetton npm run blueprint:status before testnet deploy.")
        next_steps.append("Deploy GLM Jetton master to TON testnet using approved TEP-74 implementation.")
        next_steps.append("Run contracts/ton/glm-jetton npm run record:deploy with Jetton master, deploy tx, admin and treasury addresses.")
    if any(item["code"].startswith("blueprint_") for item in blockers):
        next_steps.append("Generate and verify GLM Blueprint deploy script with TON_JETTON_ADMIN_ADDRESS=EQ... npm run blueprint:prepare && npm run blueprint:status.")
    if any(item["code"] in {"build_minter", "build_wallet", "wallet_library_hash"} for item in blockers):
        next_steps.append("Compile pinned reference contracts and run cd contracts/ton/glm-jetton && npm run build:status.")
    if any(item["code"] in {"reference_lock", "reference_vendor", "reference_commit"} for item in blockers):
        next_steps.append("Run cd contracts/ton/glm-jetton && npm run reference:fetch && npm run reference:status before contract review/deploy.")
    if any(item["code"] == "jetton_master_env" for item in blockers):
        next_steps.append("Set TON_GLM_JETTON_MASTER_ADDRESS in backend/systemd env after deploy.")
    if any(item["code"] == "treasury_env" for item in blockers):
        next_steps.append("Set TON_GLM_TREASURY_ADDRESS in backend/systemd env for operator workflow.")
    if not settlement_config.get("lookup_addresses"):
        next_steps.append("Set TON_GLM_SETTLEMENT_LOOKUP_ADDRESSES to wallet addresses checked by TON Center settlement.")
    if not (os.getenv("TON_GLM_SETTLEMENT_ADMIN_USER_ID") or "").strip():
        next_steps.append("Set TON_GLM_SETTLEMENT_ADMIN_USER_ID before enabling background auto-settlement.")
    if auto_transfer_config.get("production_candidate_ready") and not auto_transfer_config.get("production_safe_signer"):
        next_steps.append("Connect TON_GLM_PRODUCTION_SIGNER_MODE and TON_GLM_PRODUCTION_SIGNER_ENDPOINT as KMS/Vault/external signer; keep production seed out of env/chat.")
    if auto_transfer_config.get("production_safe_signer") and not auto_transfer_config.get("production_approvals_ready"):
        next_steps.append("Collect TON_GLM_PRODUCTION_LEGAL_APPROVED, TON_GLM_PRODUCTION_SECURITY_APPROVED and TON_GLM_PRODUCTION_TREASURY_APPROVED before mainnet.")
    if not blockers and pending_claim_count > 0:
        next_steps.append("Export TON CSV, transfer existing GLM from treasury/bank to user TON wallet, then submit tx hash to ton-settlement endpoint.")
    if not blockers and pending_claim_count == 0:
        next_steps.append("Create a small verified test claim, then run TON CSV -> testnet treasury transfer workflow.")
    readiness_alerts: list[dict[str, Any]] = []
    if auto_transfer_config.get("override", {}).get("enabled") is False:
        readiness_alerts.append({
            "code": "auto_transfer_paused",
            "severity": "critical",
            "message": "points_to_glm auto-transfer поставлен на паузу override-файлом; новые заявки не будут отправляться в TON автоматически.",
        })
    if auto_transfer_health["blocked_count"]:
        readiness_alerts.append({
            "code": "points_to_glm_blocked",
            "severity": "warning",
            "message": f"{auto_transfer_health['blocked_count']} заявок points_to_glm заблокированы auto-transfer проверками на {auto_transfer_health['blocked_amount_glm']} GLM.",
        })
    if auto_transfer_health["waiting_settlement_count"]:
        readiness_alerts.append({
            "code": "points_to_glm_waiting_settlement",
            "severity": "warning",
            "message": f"{auto_transfer_health['waiting_settlement_count']} TON transfer ожидают settlement на {auto_transfer_health['waiting_settlement_amount_glm']} GLM.",
        })
    if int(auto_transfer_health["oldest_pending_age_minutes"] or 0) >= 60:
        readiness_alerts.append({
            "code": "points_to_glm_old_pending",
            "severity": "warning",
            "message": f"Самая старая pending-заявка points_to_glm ждет {auto_transfer_health['oldest_pending_age_minutes']} минут.",
        })
    if glm_to_points_health["tx_found_count"]:
        readiness_alerts.append({
            "code": "glm_to_points_tx_found",
            "severity": "info",
            "message": f"{glm_to_points_health['tx_found_count']} заявок GLM -> баллы имеют найденную TON-транзакцию на {glm_to_points_health['tx_found_amount_glm']} GLM и ждут закрытия/1С.",
        })
    if glm_to_points_health["onec_issue_count"]:
        readiness_alerts.append({
            "code": "glm_to_points_onec_issue",
            "severity": "warning",
            "message": f"{glm_to_points_health['onec_issue_count']} заявок GLM -> баллы требуют внимания 1С на {glm_to_points_health['onec_issue_amount_glm']} GLM.",
        })
    if int(glm_to_points_health["oldest_pending_age_minutes"] or 0) >= 60:
        readiness_alerts.append({
            "code": "glm_to_points_old_pending",
            "severity": "warning",
            "message": f"Самая старая pending-заявка GLM -> баллы ждет {glm_to_points_health['oldest_pending_age_minutes']} минут.",
        })
    if security_warnings:
        readiness_alerts.append({
            "code": "security_warnings",
            "severity": "warning",
            "message": f"Есть security warnings: {len(security_warnings)}. Mainnet readiness требует отдельной проверки.",
        })
    if int(bridge_operations_summary.get("missing_domain_count") or 0) > 0:
        readiness_alerts.append({
            "code": "bridge_operations_missing_domain_rows",
            "severity": "warning",
            "message": f"{bridge_operations_summary['missing_domain_count']} bridge ledger-записей еще не имеют строки в glame_token_bridge_operations.",
        })
    if int(bridge_operations_health.get("stale_pending_count") or 0) > 0:
        readiness_alerts.append({
            "code": "bridge_domain_stale_pending",
            "severity": "warning",
            "message": f"{bridge_operations_health['stale_pending_count']} domain bridge operations pending дольше {bridge_operation_stale_minutes} минут на {bridge_operations_health['stale_pending_amount_glm']} GLM.",
        })
    if int(bridge_operations_health.get("ton_waiting_count") or 0) > 0:
        readiness_alerts.append({
            "code": "bridge_domain_ton_waiting",
            "severity": "warning",
            "message": f"{bridge_operations_health['ton_waiting_count']} domain bridge operations ждут TON на {bridge_operations_health['ton_waiting_amount_glm']} GLM.",
        })
    if int(bridge_operations_health.get("onec_issue_count") or 0) > 0:
        readiness_alerts.append({
            "code": "bridge_domain_onec_issues",
            "severity": "warning",
            "message": f"{bridge_operations_health['onec_issue_count']} domain bridge operations имеют 1С issue на {bridge_operations_health['onec_issue_amount_glm']} GLM.",
        })
    for item in treasury_balances.get("alerts") or []:
        readiness_alerts.append({
            "code": item.get("code") or "treasury_balance_alert",
            "severity": item.get("severity") or "warning",
            "message": item.get("message") or "TON treasury balance требует проверки.",
        })
    go_no_go_checks = [
        {
            "code": "network_mainnet",
            "ok": str(policy.get("network") or "").strip() == "mainnet",
            "label": "Network mainnet",
            "message": "TON_NETWORK должен быть mainnet для публичного GLM режима.",
        },
        {
            "code": "jetton_mainnet_deployed",
            "ok": bool(policy.get("jetton_master_address")) and str(policy.get("network") or "").strip() == "mainnet",
            "label": "Mainnet Jetton",
            "message": "GLM Jetton master должен быть задан и опубликован в mainnet.",
        },
        {
            "code": "external_signer_ready",
            "ok": bool(auto_transfer_config.get("production_safe_signer")),
            "label": "External signer",
            "message": "Production hot-wallet должен подписывать через external signer/KMS/Vault, без seed в backend.",
        },
        {
            "code": "signer_limits_set",
            "ok": int(auto_transfer_config.get("max_amount_glm") or 0) > 0 and int(auto_transfer_config.get("daily_limit_glm") or 0) > 0,
            "label": "Signer limits",
            "message": "Должны быть заданы max per tx и daily cap для hot-wallet auto-transfer.",
        },
        {
            "code": "auto_transfer_enabled",
            "ok": bool(auto_transfer_config.get("enabled")),
            "label": "Auto-transfer enabled",
            "message": "Backend auto-transfer не должен быть на паузе перед публичным запуском.",
        },
        {
            "code": "hot_wallet_funded",
            "ok": hot_wallet_balance.get("status") in {"ok", "warning"} and float(hot_wallet_balance.get("glm_balance") or 0) > 0 and float(hot_wallet_balance.get("ton_balance") or 0) > 0,
            "label": "Hot-wallet funded",
            "message": "Hot-wallet должен иметь GLM и TON gas для заявок.",
        },
        {
            "code": "treasury_funded",
            "ok": treasury_balance.get("status") in {"ok", "warning"} and float(treasury_balance.get("glm_balance") or 0) > 0 and float(treasury_balance.get("ton_balance") or 0) > 0,
            "label": "Treasury funded",
            "message": "Treasury/bank должен иметь GLM и TON gas для refill/refund операций.",
        },
        {
            "code": "approvals_ready",
            "ok": bool(auto_transfer_config.get("production_approvals_ready")),
            "label": "Approvals",
            "message": "Нужны legal, security и treasury approval.",
        },
        {
            "code": "no_mainnet_blockers",
            "ok": not mainnet_blockers,
            "label": "No blockers",
            "message": "Readiness не должен иметь mainnet blockers.",
        },
        {
            "code": "no_bridge_attention",
            "ok": not bridge_operations_health.get("needs_attention") and not auto_transfer_health.get("needs_attention") and not glm_to_points_health.get("needs_attention"),
            "label": "Bridge health",
            "message": "Перед публичным запуском не должно быть зависших bridge/TON/1C операций.",
        },
        {
            "code": "token_verification_package",
            "ok": (PROJECT_ROOT_DIR / "contracts" / "ton" / "glm-jetton" / "ton-assets-verification" / "GLM.yaml").exists(),
            "label": "Token verification package",
            "message": "Пакет для Tonkeeper/asset-list должен быть готов; сам PR/merge остается внешним шагом.",
        },
    ]
    go_no_go_blockers = [item for item in go_no_go_checks if not item.get("ok")]
    go_no_go = {
        "status": "go" if not go_no_go_blockers else "blocked",
        "ready": not go_no_go_blockers,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "max_amount_glm": int(auto_transfer_config.get("max_amount_glm") or 0),
        "daily_limit_glm": int(auto_transfer_config.get("daily_limit_glm") or 0),
        "checks": go_no_go_checks,
        "blockers": go_no_go_blockers,
        "next_steps": [
            item["message"]
            for item in go_no_go_blockers[:6]
        ],
    }
    readiness_status = "ready_for_treasury_transfer" if not blockers else "blocked"
    if network == "mainnet":
        readiness_status = "mainnet_ready" if go_no_go.get("ready") and not blockers else "blocked"
    return {
        "status": readiness_status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": policy,
        "env_status": env_status,
        "artifact": {
            "exists": artifact.get("exists"),
            "path": artifact.get("path"),
            "error": artifact.get("error"),
            "deployment_status": artifact_deployment.get("status"),
            "jetton_master_address": artifact_contracts.get("jetton_master_address"),
            "treasury_address": artifact_contracts.get("treasury_address"),
            "deploy_tx_hash": artifact_deployment.get("deploy_tx_hash"),
            "deployed_at": artifact_deployment.get("deployed_at"),
        },
        "reference": {
            "exists": reference.get("exists"),
            "path": reference.get("path"),
            "error": reference.get("error"),
            "name": (reference.get("data") or {}).get("name") if isinstance(reference.get("data"), dict) else None,
            "repo": (reference.get("data") or {}).get("repo") if isinstance(reference.get("data"), dict) else None,
            "branch": (reference.get("data") or {}).get("branch") if isinstance(reference.get("data"), dict) else None,
            "expected_commit": reference.get("expected_commit"),
            "actual_commit": reference.get("actual_commit"),
            "vendor_exists": reference.get("vendor_exists"),
            "matches_lock": reference.get("matches_lock"),
        },
        "blueprint": {
            "deploy_script_path": blueprint.get("deploy_script_path"),
            "deploy_script_exists": blueprint.get("deploy_script_exists"),
            "error": blueprint.get("error"),
            "metadata_url": blueprint.get("metadata_url"),
            "has_admin_address": blueprint.get("has_admin_address"),
            "mainnet_guard": blueprint.get("mainnet_guard"),
            "metadata_matches_script": blueprint.get("metadata_matches_script"),
            "admin_matches_script": blueprint.get("admin_matches_script"),
        },
        "build": {
            "minter_compiled": build_status.get("minter_compiled"),
            "wallet_compiled": build_status.get("wallet_compiled"),
            "wallet_library_hash": build_status.get("wallet_library_hash"),
            "contracts": build_status.get("contracts"),
        },
        "pending_claims": {
            "count": pending_claim_count,
            "amount_glm": pending_claim_total,
            "auto_transfer_status_counts": auto_transfer_status_counts,
            "auto_transfer_amounts_by_status": auto_transfer_amounts_by_status,
            "auto_transfer_health": auto_transfer_health,
            "sample_limit": len(pending_claim_samples),
            "sample": pending_claim_samples,
            "operator_csv_url": "/api/referrals/admin/glm-claims/ton-operator.csv?status=pending&limit=1000",
        },
        "pending_glm_to_points": {
            "count": len(pending_glm_to_points_rows),
            "amount_glm": pending_glm_to_points_total,
            "deposit_status_counts": deposit_status_counts,
            "deposit_amounts_by_status": deposit_amounts_by_status,
            "health": glm_to_points_health,
            "sample_limit": len(pending_glm_to_points_samples),
            "sample": pending_glm_to_points_samples,
        },
        "bridge_operations": {
            **bridge_operations_summary,
            "health": bridge_operations_health,
            "list_endpoint": "/api/referrals/admin/glm-bridge/operations",
        },
        "settlement": {
            **settlement_config,
            "checks": settlement_checks,
            "manual_endpoint": "/api/referrals/admin/glm-claims/{claim_id}/ton-settlement",
            "background_ready": all(item["ok"] for item in settlement_checks),
        },
        "auto_transfer": {
            **auto_transfer_config,
            "run_endpoint": "/api/referrals/admin/glm-ton-auto-transfer/run",
            "ready": bool(
                auto_transfer_config.get("enabled")
                and auto_transfer_signer_ready
                and auto_transfer_config.get("admin_user_id")
            ),
        },
        "treasury_balances": treasury_balances,
        "wallet_cache_propagation": wallet_cache_propagation,
        "security": {
            "pilot_only": hot_wallet_secret_source == "env_mnemonic",
            "mainnet_ready": not mainnet_blockers,
            "production_hot_wallet_address": auto_transfer_config.get("production_hot_wallet_address"),
            "production_hot_wallet_bounceable": auto_transfer_config.get("production_hot_wallet_bounceable"),
            "production_hot_wallet_raw": auto_transfer_config.get("production_hot_wallet_raw"),
            "production_treasury_address": auto_transfer_config.get("production_treasury_address"),
            "production_treasury_bounceable": auto_transfer_config.get("production_treasury_bounceable"),
            "production_treasury_raw": auto_transfer_config.get("production_treasury_raw"),
            "production_treasury_ready": bool(auto_transfer_config.get("production_treasury_ready")),
            "production_candidate_ready": bool(auto_transfer_config.get("production_candidate_ready")),
            "production_ready": bool(auto_transfer_config.get("production_ready")),
            "production_signer_mode": auto_transfer_config.get("production_signer_mode"),
            "production_signer_endpoint_configured": bool(auto_transfer_config.get("production_signer_endpoint_configured")),
            "production_signer_pause_endpoint_configured": bool(auto_transfer_config.get("production_signer_pause_endpoint_configured")),
            "production_signer_auth_configured": bool(auto_transfer_config.get("production_signer_auth_configured")),
            "production_legal_approved": bool(auto_transfer_config.get("production_legal_approved")),
            "production_security_approved": bool(auto_transfer_config.get("production_security_approved")),
            "production_treasury_approved": bool(auto_transfer_config.get("production_treasury_approved")),
            "production_approvals_ready": bool(auto_transfer_config.get("production_approvals_ready")),
            "production_approvals_override": auto_transfer_config.get("production_approvals_override"),
            "warnings": security_warnings,
            "mainnet_blockers": mainnet_blockers,
        },
        "go_no_go": go_no_go,
        "alerts": readiness_alerts,
        "telegram_notifications": TelegramNotificationService.config_payload(),
        "schedulers": glm_token_scheduler_status(request.app),
        "commands": {
            "validate_env": "cd contracts/ton/glm-jetton && npm run validate:env",
            "reference_status": "cd contracts/ton/glm-jetton && npm run reference:status",
            "reference_fetch": "cd contracts/ton/glm-jetton && npm run reference:fetch",
            "deploy_handoff": "cd contracts/ton/glm-jetton && npm run deploy:handoff",
            "blueprint_prepare": "cd contracts/ton/glm-jetton && TON_JETTON_ADMIN_ADDRESS=EQ... npm run blueprint:prepare",
            "blueprint_status": "cd contracts/ton/glm-jetton && TON_JETTON_ADMIN_ADDRESS=EQ... npm run blueprint:status",
            "build_status": "cd contracts/ton/glm-jetton && npm run build:status",
            "record_deploy": "cd contracts/ton/glm-jetton && npm run record:deploy -- --jetton-master-address EQ... --deploy-tx-hash ... --admin-address EQ... --treasury-address EQ...",
            "prepare_claims": "cd contracts/ton/glm-jetton && npm run prepare:claims -- ./pending-claims.csv",
            "prepare_claim_transfer": "Open GLAME treasury wallet and transfer existing GLM to claim wallet from TON CSV.",
            "settle_claim": "POST /api/referrals/admin/glm-claims/{claim_id}/ton-settlement with { tx_hash, require_verified: true }",
            "auto_transfer_run": "POST /api/referrals/admin/glm-ton-auto-transfer/run with { limit: 20 }",
            "replay_idempotency_audit": "GET /api/referrals/admin/glm-replay-idempotency-audit",
        },
        "next_steps": next_steps,
        "checks": checks,
        "blockers": blockers,
        "legacy_deploy_blockers": legacy_deploy_blockers,
    }


@router.get("/admin/glm-replay-idempotency-audit")
async def admin_glm_replay_idempotency_audit(
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    return await _glm_replay_idempotency_audit_payload(db)


def _glm_policy_document_fingerprints() -> list[dict[str, Any]]:
    policy_dir = Path(__file__).resolve().parents[2] / "static" / "glm_policy"
    document_names = [
        "token-policy.md",
        "risk-disclosure.md",
        "bridge-rules.md",
        "emission-policy.md",
        "faq.md",
        "operator-runbook.md",
        "production-escalation-policy.md",
        "production-signer-contract.md",
        "security-review-checklist.md",
        "legal-accounting-approval.md",
        "treasury-approval.md",
        "launch-approval-packet.md",
        "p2p-marketplace-approval-packet.md",
        "exchange-desk-policy.md",
        "jetton-metadata-mainnet-v2.json",
    ]
    documents: list[dict[str, Any]] = []
    for document_name in document_names:
        path = policy_dir / document_name
        digest: str | None = None
        if path.exists() and path.is_file():
            hash_obj = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    hash_obj.update(chunk)
            digest = hash_obj.hexdigest()
        documents.append({
            "file": f"backend/static/glm_policy/{document_name}",
            "exists": path.exists(),
            "sha256": digest,
            "bytes": path.stat().st_size if path.exists() else None,
        })
    return documents


def _glm_production_approval_state() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "static" / "glm_policy" / "production-approvals.json"
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            raw_payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw_payload, dict):
                payload = raw_payload
        except json.JSONDecodeError as error:
            return {"exists": True, "valid_json": False, "error": str(error)}
    return {
        "exists": path.exists(),
        "valid_json": True,
        "legal_approved": bool(payload.get("legal_approved")),
        "security_approved": bool(payload.get("security_approved")),
        "treasury_approved": bool(payload.get("treasury_approved")),
        "updated_at": payload.get("updated_at"),
        "comment_present": bool(payload.get("comment")),
        "updated_by_present": bool(payload.get("updated_by")),
        "legal_evidence_ref": payload.get("legal_evidence_ref"),
        "security_evidence_ref": payload.get("security_evidence_ref"),
        "treasury_evidence_ref": payload.get("treasury_evidence_ref"),
        "public_wording_evidence_ref": payload.get("public_wording_evidence_ref"),
        "offline_evidence_ready": all(
            bool(str(payload.get(key) or "").strip())
            for key in (
                "legal_evidence_ref",
                "security_evidence_ref",
                "treasury_evidence_ref",
                "public_wording_evidence_ref",
            )
        ),
    }


def _run_glm_local_launch_checks() -> dict[str, Any]:
    script_path = PROJECT_ROOT_DIR / "scripts" / "security" / "run_crypto_glame_launch_checks.py"
    if not script_path.exists():
        return {
            "ok": False,
            "returncode": None,
            "error": "run_crypto_glame_launch_checks.py not found",
        }
    try:
        result = subprocess.run(
            ["python3", str(script_path.relative_to(PROJECT_ROOT_DIR)), "--skip-live"],
            cwd=PROJECT_ROOT_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "returncode": None,
            "error": "launch checks timed out",
        }
    payload: dict[str, Any] | None = None
    stdout = result.stdout.strip()
    if stdout:
        try:
            raw_payload = json.loads(stdout)
            if isinstance(raw_payload, dict):
                payload = raw_payload
        except json.JSONDecodeError:
            payload = None
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "payload": payload,
        "stderr_tail": result.stderr.strip()[-2000:],
    }


async def _glm_wallet_cache_propagation_payload(policy: dict[str, Any]) -> dict[str, Any]:
    expected_metadata_url = (
        os.getenv("TON_GLM_MAINNET_METADATA_URL")
        or "https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata-mainnet-v2.json"
    ).strip()
    expected_icon_url = "https://partner.glamejewelry.ru/static/glm_policy/glm-token-icon-v3.png"
    jetton_master = str(policy.get("jetton_master_address") or os.getenv("TON_GLM_JETTON_MASTER_ADDRESS") or "").strip()
    payload: dict[str, Any] = {
        "status": "not_configured",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source": "tonapi",
        "jetton_master_address": jetton_master or None,
        "metadata_url": expected_metadata_url,
        "expected": {
            "name": "GLAME Coin",
            "symbol": "GLM",
            "decimals": "9",
            "image": expected_icon_url,
            "verification": "whitelist",
        },
        "tonapi": None,
        "metadata": None,
        "checks": [],
        "errors": [],
    }
    if not jetton_master:
        payload["errors"].append("TON_GLM_JETTON_MASTER_ADDRESS is not configured")
        return payload

    timeout = float(os.getenv("TON_GLM_WALLET_CACHE_CHECK_TIMEOUT_SECONDS", "10") or 10)
    headers: dict[str, str] = {}
    tonapi_key = (os.getenv("TONAPI_API_KEY") or "").strip()
    if tonapi_key:
        headers["Authorization"] = f"Bearer {tonapi_key}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            tonapi_response = await client.get(f"https://tonapi.io/v2/jettons/{jetton_master}", headers=headers)
            tonapi_response.raise_for_status()
            tonapi_payload = tonapi_response.json()
            metadata_response = await client.get(expected_metadata_url)
            metadata_response.raise_for_status()
            metadata_payload = metadata_response.json()
    except Exception as error:
        payload["status"] = "error"
        payload["errors"].append(str(error)[:500])
        return payload

    tonapi_metadata = tonapi_payload.get("metadata") if isinstance(tonapi_payload, dict) else {}
    if not isinstance(tonapi_metadata, dict):
        tonapi_metadata = {}
    if not isinstance(metadata_payload, dict):
        metadata_payload = {}
    payload["tonapi"] = {
        "verification": tonapi_payload.get("verification") if isinstance(tonapi_payload, dict) else None,
        "name": tonapi_metadata.get("name"),
        "symbol": tonapi_metadata.get("symbol"),
        "decimals": str(tonapi_metadata.get("decimals")) if tonapi_metadata.get("decimals") is not None else None,
        "image": tonapi_metadata.get("image"),
        "description": tonapi_metadata.get("description"),
        "holders_count": tonapi_payload.get("holders_count") if isinstance(tonapi_payload, dict) else None,
        "preview": tonapi_payload.get("preview") if isinstance(tonapi_payload, dict) else None,
    }
    payload["metadata"] = {
        "name": metadata_payload.get("name"),
        "symbol": metadata_payload.get("symbol"),
        "decimals": str(metadata_payload.get("decimals")) if metadata_payload.get("decimals") is not None else None,
        "image": metadata_payload.get("image"),
        "description": metadata_payload.get("description"),
    }
    checks = [
        ("tonapi_name", payload["tonapi"].get("name") == "GLAME Coin", "TonAPI must show GLAME Coin"),
        ("tonapi_symbol", payload["tonapi"].get("symbol") == "GLM", "TonAPI must show GLM symbol"),
        ("tonapi_decimals", payload["tonapi"].get("decimals") == "9", "TonAPI must show 9 decimals"),
        ("tonapi_icon", payload["tonapi"].get("image") == expected_icon_url, "TonAPI must show production PNG icon"),
        ("tonapi_not_testnet", "testnet" not in str(payload["tonapi"].get("description") or "").lower(), "TonAPI description must not contain testnet wording"),
        ("tonapi_whitelist", payload["tonapi"].get("verification") == "whitelist", "TonAPI verification should be whitelist"),
        ("metadata_name", payload["metadata"].get("name") == "GLAME Coin", "Public metadata must show GLAME Coin"),
        ("metadata_icon", payload["metadata"].get("image") == expected_icon_url, "Public metadata must show production PNG icon"),
    ]
    payload["checks"] = [{"code": code, "ok": ok, "message": message} for code, ok, message in checks]
    failed = [item for item in payload["checks"] if not item.get("ok")]
    payload["status"] = "ok" if not failed else "warning"
    return payload


def _latest_glm_evidence_file(*patterns: str) -> dict[str, Any] | None:
    evidence_dir = Path(__file__).resolve().parents[2] / "data" / "crypto_glame_evidence"
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(evidence_dir.glob(pattern))
    files = [path for path in matches if path.exists() and path.is_file()]
    if not files:
        return None
    latest = max(files, key=lambda path: path.stat().st_mtime)
    return {
        "file": str(latest.relative_to(PROJECT_ROOT_DIR)),
        "bytes": latest.stat().st_size,
        "updated_at": datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat(),
        "sha256": hashlib.sha256(latest.read_bytes()).hexdigest(),
    }


async def _glm_launch_evidence_checklist(
    db: AsyncSession,
    *,
    replay_audit: dict[str, Any],
    launch_checks: dict[str, Any],
) -> list[dict[str, Any]]:
    approvals = _glm_production_approval_state()

    async def published_audit_hash() -> dict[str, Any] | None:
        row = (
            await db.execute(
                select(GlameTokenDailyAuditHash)
                .where(
                    GlameTokenDailyAuditHash.token_code == "GLM",
                    GlameTokenDailyAuditHash.public_status == "published",
                )
                .order_by(desc(GlameTokenDailyAuditHash.audit_date))
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "audit_date": row.audit_date.isoformat() if row.audit_date else None,
            "root_hash": row.root_hash,
            "public_reference": row.public_reference,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    items: list[dict[str, Any]] = [
        {
            "code": "launch_evidence_snapshot",
            "label": "Launch evidence snapshot",
            "status": "ok" if launch_checks.get("ok") else "todo",
            "href": "#production-approvals",
        },
        {
            "code": "replay_idempotency_audit",
            "label": "Replay/idempotency audit",
            "status": "ok" if replay_audit.get("status") == "ok" else "todo",
            "href": "#production-approvals",
        },
    ]
    file_checks = [
        ("bridge_reconciliation", "Bridge reconciliation evidence", "#glm-bridge-reconciliation", ("bridge-reconciliation-*", "glm-bridge-reconciliation-*")),
        ("treasury_turnover", "Treasury turnover evidence", "#ton-readiness", ("treasury-turnover-*", "glm-treasury-turnover-*", "treasury-balances-*")),
        ("points_to_glm_e2e", "Mainnet Баллы→GLM E2E evidence", "#ton-readiness", ("points-to-glm-e2e-*",)),
        ("glm_to_points_e2e", "Mainnet GLM→баллы E2E evidence", "#ton-readiness", ("glm-to-points-e2e-*",)),
        ("buy_glm_with_ton_e2e", "Mainnet Купить GLM за GRAM evidence", "#ton-readiness", ("buy-glm-with-ton-e2e-*",)),
        ("glm_store_checkout_e2e", "GLM Store checkout evidence", "#reward-store", ("glm-store-checkout-*",)),
        ("tonkeeper_verification", "Tonkeeper verification evidence", "/glm", ("tonkeeper-verification-*", "ton-assets-verification-*")),
    ]
    for code, label_text, href, patterns in file_checks:
        evidence_file = _latest_glm_evidence_file(*patterns)
        items.append({
            "code": code,
            "label": label_text,
            "status": "ok" if evidence_file else "todo",
            "href": href,
            "evidence": evidence_file,
        })

    audit_hash = await published_audit_hash()
    items.insert(4, {
        "code": "published_audit_hash",
        "label": "Published GLM audit hash",
        "status": "ok" if audit_hash else "todo",
        "href": "/glm/audit",
        "evidence": audit_hash,
    })
    items.insert(5, {
        "code": "signed_offline_approvals",
        "label": "Signed/offline approval evidence",
        "status": "ok" if approvals.get("offline_evidence_ready") else "todo",
        "href": "#production-approvals",
        "evidence": {
            "legal_evidence_ref": approvals.get("legal_evidence_ref"),
            "security_evidence_ref": approvals.get("security_evidence_ref"),
            "treasury_evidence_ref": approvals.get("treasury_evidence_ref"),
            "public_wording_evidence_ref": approvals.get("public_wording_evidence_ref"),
        },
    })
    return items


@router.get("/admin/glm-launch-evidence")
async def admin_glm_launch_evidence(
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    replay_audit = await _glm_replay_idempotency_audit_payload(db)
    signer_check = await TonGlmAutoTransferService.check_production_signer_health()
    launch_checks = _run_glm_local_launch_checks()
    ok = (
        bool(launch_checks.get("ok"))
        and replay_audit.get("status") == "ok"
        and str(signer_check.get("status") or "").lower() in {"ok", "warning"}
    )
    return {
        "schema": "glame_crypto_admin_launch_evidence_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "approvals": _glm_production_approval_state(),
        "policy_documents": _glm_policy_document_fingerprints(),
        "launch_checks": launch_checks,
        "signer_check": signer_check,
        "replay_idempotency_audit": replay_audit,
        "evidence_checklist": await _glm_launch_evidence_checklist(
            db,
            replay_audit=replay_audit,
            launch_checks=launch_checks,
        ),
        "manual_evidence_required": [
            "admin /admin/crypto readiness screenshot",
            "bridge reconciliation CSV",
            "treasury turnover CSV",
            "mainnet points_to_glm tx hash and 1C movement evidence",
            "mainnet glm_to_points tx hash and 1C movement evidence",
            "GLM Store checkout/fulfillment or checkout/refund evidence",
            "Tonkeeper asset-list PR review/merge/propagation evidence",
        ],
    }


@router.post("/admin/glm-production-signer/check")
async def admin_glm_production_signer_check(
    _current_user: User = Depends(require_admin()),
):
    return await TonGlmAutoTransferService.check_production_signer_health()


@router.post("/admin/glm-production-signer/emergency-pause")
async def admin_glm_production_signer_emergency_pause(
    payload: AdminGlmProductionSignerEmergencyPauseRequest,
    current_user: User = Depends(require_admin()),
):
    result = await TonGlmAutoTransferService.set_production_signer_emergency_pause(
        paused=payload.paused,
        reason=payload.reason,
        admin_user_id=current_user.id,
    )
    return {
        "status": "paused" if payload.paused else "ok",
        "result": result,
    }


@router.post("/admin/glm-production-approvals")
async def admin_glm_production_approvals(
    payload: AdminGlmProductionApprovalsRequest,
    current_user: User = Depends(require_admin()),
):
    approvals = TonGlmAutoTransferService.write_production_approvals(
        legal_approved=payload.legal_approved,
        security_approved=payload.security_approved,
        treasury_approved=payload.treasury_approved,
        comment=payload.comment,
        admin_user_id=current_user.id,
        legal_evidence_ref=payload.legal_evidence_ref,
        security_evidence_ref=payload.security_evidence_ref,
        treasury_evidence_ref=payload.treasury_evidence_ref,
        public_wording_evidence_ref=payload.public_wording_evidence_ref,
    )
    return {
        "status": "success",
        "approvals": approvals,
        "auto_transfer": TonGlmAutoTransferService.config_payload(),
    }


@router.get("/admin/glm-claims/ton-operator.csv")
async def admin_glm_claims_ton_operator_csv(
    status_filter: str | None = Query(default="pending", alias="status"),
    limit: int = Query(default=300, ge=1, le=1000),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(GlameTokenTransaction, ReferralProgramMember, User)
            .join(ReferralProgramMember, ReferralProgramMember.id == GlameTokenTransaction.referral_member_id)
            .join(User, User.id == ReferralProgramMember.user_id)
            .where(
                GlameTokenTransaction.transaction_type == "claim",
                GlameTokenTransaction.status == status_filter,
            )
            .order_by(GlameTokenTransaction.created_at.asc(), GlameTokenTransaction.id.asc())
            .limit(limit)
        )
    ).all()
    policy = GlameTokenService.policy_payload().get("onchain_policy") or {}
    output = io.StringIO()
    fieldnames = [
        "claim_id",
        "status",
        "amount_glm",
        "wallet_address",
        "wallet_app",
        "partner_name",
        "partner_phone",
        "created_at",
        "ton_network",
        "jetton_master_address",
        "treasury_address",
        "metadata_url",
        "operator_action",
        "after_tx_action",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for tx, _member, user in rows:
        meta = tx.meta if isinstance(tx.meta, dict) else {}
        writer.writerow({
            "claim_id": str(tx.id),
            "status": tx.status,
            "amount_glm": int(tx.amount or 0),
            "wallet_address": meta.get("wallet_address") or "",
            "wallet_app": meta.get("wallet_app") or "",
            "partner_name": user.full_name or "Партнер GLAME",
            "partner_phone": user.phone or "",
            "created_at": tx.created_at.isoformat() if tx.created_at else "",
            "ton_network": policy.get("network") or "testnet",
            "jetton_master_address": policy.get("jetton_master_address") or "",
            "treasury_address": policy.get("treasury_address") or "",
            "metadata_url": policy.get("metadata_url") or "",
            "operator_action": "transfer_testnet_glm_from_treasury_to_wallet",
            "after_tx_action": "paste_ton_tx_hash_and_mark_processed",
        })
    filename = f"glm-ton-operator-claims-{status_filter or 'all'}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/admin/glm-claims/{claim_id}")
async def admin_update_glm_claim(
    claim_id: UUID,
    payload: AdminGlmClaimStatusRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == claim_id,
                GlameTokenTransaction.transaction_type == "claim",
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="GLM claim не найден")
    try:
        tx = await GlameTokenService(db).update_claim_status(
            claim=tx,
            status=payload.status,
            admin_user_id=current_user.id,
            tx_hash=payload.tx_hash,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    return {"status": "success", "claim": _glm_claim_payload(tx)}


@router.post("/admin/glm-claims/{claim_id}/ton-settlement")
async def admin_settle_glm_claim_with_ton_tx(
    claim_id: UUID,
    payload: AdminGlmTonSettlementRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await TonGlmSettlementService(db).settle_claim_by_tx_hash(
            claim_id=claim_id,
            tx_hash=payload.tx_hash,
            admin_user_id=current_user.id,
            comment=payload.comment,
            require_verified=payload.require_verified,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    claim = result.get("claim")
    return {
        "status": result.get("status"),
        "claim": _glm_claim_payload(claim) if isinstance(claim, GlameTokenTransaction) else None,
        "verification": result.get("verification"),
    }


@router.get("/admin/glm-treasury-balances")
async def admin_glm_treasury_balances(
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    return await TonGlmTreasuryBalanceService(db).payload()


@router.post("/admin/glm-treasury-balances/check")
async def admin_check_glm_treasury_balances(
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    service = TonGlmTreasuryBalanceService(db)
    payload = await service.payload()
    item = await service.record_refill_check(payload, admin_user_id=current_user.id, event_type="balance_check")
    payload["refill_check"] = TonGlmTreasuryBalanceService.refill_check_payload(item)
    return payload


@router.get("/admin/glm-treasury-turnover")
async def admin_glm_treasury_turnover(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=30, ge=1, le=200),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    stats_start_at = _glm_operational_stats_start_at()
    network = _glm_operational_network()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    if stats_start_at and stats_start_at > since:
        since = stats_start_at
    tx_rows = (
        await db.execute(
            select(GlameTokenTransaction, ReferralProgramMember, User)
            .join(ReferralProgramMember, ReferralProgramMember.id == GlameTokenTransaction.referral_member_id, isouter=True)
            .join(User, User.id == GlameTokenTransaction.user_id, isouter=True)
            .where(
                GlameTokenTransaction.token_code == "GLM",
                GlameTokenTransaction.created_at >= since,
                or_(
                    and_(
                        GlameTokenTransaction.transaction_type == "redemption",
                        GlameTokenTransaction.reason == "glm_store_item",
                    ),
                    and_(
                        GlameTokenTransaction.transaction_type == "bridge",
                        GlameTokenTransaction.reason.in_(("glm_to_points_bridge", "buy_loyalty_points")),
                    ),
                ),
            )
            .order_by(desc(GlameTokenTransaction.created_at))
            .limit(max(limit * 3, 100))
        )
    ).all()
    await TonGlmTreasuryBalanceService(db).ensure_refill_check_table()
    refill_rows = (
        await db.execute(
            select(GlameTreasuryRefillCheck)
            .where(
                GlameTreasuryRefillCheck.event_type == "manual_refill",
                GlameTreasuryRefillCheck.created_at >= since,
                or_(GlameTreasuryRefillCheck.network == network, GlameTreasuryRefillCheck.network.is_(None)),
            )
            .order_by(desc(GlameTreasuryRefillCheck.created_at))
            .limit(max(limit, 50))
        )
    ).scalars().all()

    incoming_total = 0
    outgoing_total = 0
    refund_required_total = 0
    refund_required_count = 0
    by_source: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []

    def add_source(source: str, amount: int, count_delta: int = 1) -> None:
        bucket = by_source.setdefault(source, {"amount_glm": 0, "count": 0})
        bucket["amount_glm"] += int(amount or 0)
        bucket["count"] += count_delta

    for tx, _member, user in tx_rows:
        meta = tx.meta if isinstance(tx.meta, dict) else {}
        tx_network = _glm_tx_meta_network(meta)
        if tx_network and tx_network != network:
            continue
        amount = abs(int(tx.amount or 0))
        if amount <= 0:
            continue
        direction = None
        source = None
        title = None
        status = tx.status
        tx_hash = meta.get("deposit_tx_hash") or meta.get("tx_hash")
        if tx.transaction_type == "redemption" and tx.reason == "glm_store_item":
            if meta.get("payment_method") != "ton_glm":
                continue
            if tx.status in {"pending_fulfillment", "fulfilled"}:
                direction = "incoming"
                source = "glm_store"
            elif tx.status in {"canceled", "failed"} and meta.get("ton_refund_required"):
                direction = "obligation"
                source = "ton_refund_required"
                refund_required_total += amount
                refund_required_count += 1
            elif tx.status in {"canceled", "failed"} and meta.get("ton_refund_status") in {"submitted", "sent", "verified"}:
                direction = "outgoing"
                source = "ton_refund"
            else:
                continue
            title = (meta.get("item") or {}).get("title") if isinstance(meta.get("item"), dict) else meta.get("sku")
        elif tx.transaction_type == "bridge" and tx.reason in {"glm_to_points_bridge", "buy_loyalty_points"}:
            if tx.status != "processed" and not meta.get("deposit_tx_hash"):
                continue
            direction = "incoming"
            source = "buy_loyalty_points" if tx.reason == "buy_loyalty_points" else "glm_to_points"
            title = "Покупка баллов за GLM" if tx.reason == "buy_loyalty_points" else "GLM -> баллы 1C"
        if source is None:
            continue
        if direction == "incoming":
            incoming_total += amount
        elif direction == "outgoing":
            outgoing_total += amount
        add_source(source, amount)
        items.append({
            "id": str(tx.id),
            "direction": direction,
            "source": source,
            "amount_glm": amount,
            "status": status,
            "title": title,
            "partner_name": getattr(user, "full_name", None) or "Партнер GLAME",
            "partner_phone": getattr(user, "phone", None),
            "tx_hash": tx_hash,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        })

    refill_total = 0
    refill_ton_total = Decimal("0")
    for row in refill_rows:
        glm_amount = int(Decimal(row.manual_glm_amount or 0))
        ton_amount = Decimal(row.manual_ton_amount or 0)
        if glm_amount <= 0 and ton_amount <= 0:
            continue
        refill_total += max(0, glm_amount)
        refill_ton_total += max(Decimal("0"), ton_amount)
        outgoing_total += max(0, glm_amount)
        add_source("hot_wallet_refill", max(0, glm_amount))
        items.append({
            "id": str(row.id),
            "direction": "outgoing",
            "source": "hot_wallet_refill",
            "amount_glm": max(0, glm_amount),
            "amount_ton": float(ton_amount),
            "status": row.status,
            "title": "Пополнение hot-wallet",
            "partner_name": None,
            "partner_phone": None,
            "tx_hash": row.ton_tx_hash,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "comment": row.comment,
        })

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    balances = await TonGlmTreasuryBalanceService(db).payload()
    refill_plan = balances.get("refill_plan") if isinstance(balances.get("refill_plan"), dict) else {}
    return {
        "status": "success",
        "network": network,
        "period_days": days,
        "since": since.isoformat(),
        "operational_stats_start_at": stats_start_at.isoformat() if stats_start_at else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "incoming_glm": incoming_total,
        "outgoing_glm": outgoing_total,
        "net_glm": incoming_total - outgoing_total,
        "refill_glm": refill_total,
        "refill_ton": float(refill_ton_total),
        "refund_required_glm": refund_required_total,
        "refund_required_count": refund_required_count,
        "by_source": by_source,
        "refill_plan": refill_plan,
        "treasury_balance": {
            "glm": refill_plan.get("treasury_glm_balance"),
            "ton": refill_plan.get("treasury_ton_balance"),
        },
        "hot_wallet_balance": {
            "glm": refill_plan.get("hot_wallet_glm_balance"),
            "ton": refill_plan.get("hot_wallet_ton_balance"),
        },
        "items": items[:limit],
    }


@router.get("/admin/glm-treasury-turnover/export.csv")
async def admin_glm_treasury_turnover_export_csv(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    payload = await admin_glm_treasury_turnover(days=days, limit=limit, _current_user=current_user, db=db)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["GLAME treasury turnover export"])
    writer.writerow(["generated_at", payload.get("generated_at")])
    writer.writerow(["network", payload.get("network")])
    writer.writerow(["since", payload.get("since")])
    writer.writerow(["period_days", payload.get("period_days")])
    writer.writerow(["operational_stats_start_at", payload.get("operational_stats_start_at") or ""])
    writer.writerow(["incoming_glm", payload.get("incoming_glm")])
    writer.writerow(["outgoing_glm", payload.get("outgoing_glm")])
    writer.writerow(["net_glm", payload.get("net_glm")])
    writer.writerow(["refill_glm", payload.get("refill_glm")])
    writer.writerow(["refill_ton", payload.get("refill_ton")])
    writer.writerow(["refund_required_glm", payload.get("refund_required_glm")])
    writer.writerow(["refund_required_count", payload.get("refund_required_count")])
    writer.writerow([])
    writer.writerow(["source", "amount_glm", "count"])
    for source, source_payload in sorted((payload.get("by_source") or {}).items()):
        writer.writerow([
            source,
            source_payload.get("amount_glm") if isinstance(source_payload, dict) else "",
            source_payload.get("count") if isinstance(source_payload, dict) else "",
        ])
    writer.writerow([])
    writer.writerow([
        "created_at",
        "direction",
        "source",
        "amount_glm",
        "amount_ton",
        "status",
        "title",
        "partner_name",
        "partner_phone",
        "tx_hash",
        "comment",
        "id",
    ])
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        writer.writerow([
            item.get("created_at") or "",
            item.get("direction") or "",
            item.get("source") or "",
            item.get("amount_glm") if item.get("amount_glm") is not None else "",
            item.get("amount_ton") if item.get("amount_ton") is not None else "",
            item.get("status") or "",
            item.get("title") or "",
            item.get("partner_name") or "",
            item.get("partner_phone") or "",
            item.get("tx_hash") or "",
            item.get("comment") or "",
            item.get("id") or "",
        ])
    filename_date = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"glm-treasury-turnover-{payload.get('network') or 'ton'}-{filename_date}.csv"
    content = output.getvalue().encode("utf-8-sig")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/admin/glm-hot-wallet-refill-checks")
async def admin_glm_hot_wallet_refill_checks(
    limit: int = Query(default=50, ge=1, le=200),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    return await TonGlmTreasuryBalanceService(db).refill_check_history(limit=limit)


@router.post("/admin/glm-hot-wallet-refill-checks/refill-record")
async def admin_record_glm_hot_wallet_refill(
    payload: AdminGlmHotWalletRefillRecordRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    service = TonGlmTreasuryBalanceService(db)
    balances = await service.payload()
    item = await service.record_refill_check(
        balances,
        admin_user_id=current_user.id,
        event_type="manual_refill",
        manual_glm_amount=payload.manual_glm_amount,
        manual_ton_amount=payload.manual_ton_amount,
        ton_tx_hash=payload.ton_tx_hash,
        comment=payload.comment,
    )
    return {
        "status": "recorded",
        "item": TonGlmTreasuryBalanceService.refill_check_payload(item),
        "treasury_balances": balances,
    }


@router.post("/admin/glm-hot-wallet-refill-approvals")
async def admin_create_glm_hot_wallet_refill_approval(
    payload: AdminGlmHotWalletRefillApprovalRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await TonGlmTreasuryBalanceService(db).create_refill_approval(
            admin_user_id=current_user.id,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "status": "pending",
        "item": TonGlmTreasuryBalanceService.refill_check_payload(item),
    }


@router.post("/admin/glm-hot-wallet-refill-approvals/{approval_id}/decision")
async def admin_decide_glm_hot_wallet_refill_approval(
    approval_id: UUID,
    payload: AdminGlmHotWalletRefillApprovalDecisionRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await TonGlmTreasuryBalanceService(db).decide_refill_approval(
            approval_id,
            admin_user_id=current_user.id,
            approved=payload.approved,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "status": item.status,
        "item": TonGlmTreasuryBalanceService.refill_check_payload(item),
    }


@router.get("/admin/glm-hot-wallet-refill-plan")
async def admin_glm_hot_wallet_refill_plan(
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    payload = await TonGlmTreasuryBalanceService(db).payload()
    return {
        "status": payload.get("refill_plan", {}).get("status") or "unknown",
        "refill_plan": payload.get("refill_plan"),
        "treasury_balances": payload,
    }


@router.post("/admin/glm-hot-wallet-refill-plan/ton-transaction")
async def admin_glm_hot_wallet_refill_ton_transaction(
    approval_id: UUID | None = Query(default=None),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await TonGlmTreasuryBalanceService(db).prepare_refill_ton_connect_transaction(approval_id=approval_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/admin/glm-ton-settlement/status")
async def admin_glm_ton_settlement_status(
    _current_user: User = Depends(require_admin()),
):
    return {
        "status": "configured" if TonGlmSettlementService.config_payload().get("enabled") else "manual",
        "settlement": TonGlmSettlementService.config_payload(),
        "next_steps": [
            "Set TON_GLM_SETTLEMENT_LOOKUP_ADDRESSES to treasury/admin/Jetton wallet addresses used by operator workflow.",
            "After treasury transfer, call POST /api/referrals/admin/glm-claims/{claim_id}/ton-settlement with tx_hash.",
            "Keep require_verified=true for normal operations; false is only a break-glass manual override.",
        ],
    }


@router.get("/admin/telegram-notifications/status")
async def admin_telegram_notifications_status(
    _current_user: User = Depends(require_admin()),
):
    config = TelegramNotificationService.config_payload()
    return {
        "status": "configured" if config.get("enabled") and config.get("bot_token_configured") else "needs_token",
        "telegram_notifications": config,
        "next_steps": [
            "Create or rotate bot token via @BotFather.",
            "Set TELEGRAM_BOT_TOKEN in server env/secret, not in chat history.",
            "Set TELEGRAM_ADMIN_CHAT_IDS to admin Telegram chat IDs.",
            "For partners, store telegram_chat_id in referral member meta or user preferences after opt-in.",
        ],
    }


@router.post("/admin/telegram-notifications/test")
async def admin_send_telegram_notification_test(
    payload: AdminTelegramNotificationTestRequest,
    _current_user: User = Depends(require_admin()),
):
    result = await TelegramNotificationService().notify_admin(
        title="GLAME Telegram notifications test",
        lines=[payload.message or "Тестовое служебное уведомление GLAME."],
        severity="info",
    )
    return {
        "status": result.get("status"),
        "result": result,
        "telegram_notifications": TelegramNotificationService.config_payload(),
    }


def _telegram_chat_id_from_partner(user: User | None, member: ReferralProgramMember | None) -> str | None:
    member_meta = member.meta if member is not None and isinstance(member.meta, dict) else {}
    user_preferences = user.preferences if user is not None and isinstance(user.preferences, dict) else {}
    candidates = [
        member_meta.get("telegram_chat_id"),
        (member_meta.get("telegram") or {}).get("chat_id") if isinstance(member_meta.get("telegram"), dict) else None,
        user_preferences.get("telegram_chat_id"),
        (user_preferences.get("telegram") or {}).get("chat_id") if isinstance(user_preferences.get("telegram"), dict) else None,
    ]
    for item in candidates:
        value = str(item or "").strip()
        if value:
            return value
    return None


def _telegram_preferences_from_partner(member: ReferralProgramMember | None) -> dict[str, Any]:
    member_meta = member.meta if member is not None and isinstance(member.meta, dict) else {}
    telegram_meta = member_meta.get("telegram") if isinstance(member_meta.get("telegram"), dict) else {}
    subscriptions = telegram_meta.get("subscriptions") if isinstance(telegram_meta.get("subscriptions"), dict) else {}
    chat_id = _telegram_chat_id_from_partner(None, member)
    return {
        "chat_id": chat_id,
        "notifications_enabled": bool(telegram_meta.get("notifications_enabled", bool(chat_id))),
        "subscriptions": {
            "partner_updates": bool(subscriptions.get("partner_updates", True)),
            "referrals": bool(subscriptions.get("referrals", True)),
            "crypto": bool(subscriptions.get("crypto", True)),
            "marketing": bool(subscriptions.get("marketing", True)),
        },
        "linked_at": telegram_meta.get("linked_at"),
        "source": telegram_meta.get("source"),
    }


def _telegram_partner_allows(member: ReferralProgramMember, category: str) -> bool:
    preferences = _telegram_preferences_from_partner(member)
    if not preferences.get("notifications_enabled"):
        return False
    subscriptions = preferences.get("subscriptions") if isinstance(preferences.get("subscriptions"), dict) else {}
    return bool(subscriptions.get(category, True))


async def _ensure_referral_feedback_schema(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS referral_feedback_messages (
                id UUID PRIMARY KEY,
                ticket_code VARCHAR(32) NOT NULL,
                source VARCHAR(32) NOT NULL DEFAULT 'partner',
                direction VARCHAR(16) NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'new',
                user_id UUID NULL REFERENCES users(id),
                member_id UUID NULL REFERENCES referral_program_members(id),
                admin_chat_id VARCHAR(64) NULL,
                telegram_message_id VARCHAR(64) NULL,
                name VARCHAR(255) NULL,
                email VARCHAR(255) NULL,
                contact VARCHAR(255) NULL,
                subject VARCHAR(255) NULL,
                message TEXT NOT NULL,
                meta JSONB NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                answered_at TIMESTAMPTZ NULL
            )
            """
        )
    )
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_referral_feedback_ticket ON referral_feedback_messages(ticket_code)"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_referral_feedback_user_created ON referral_feedback_messages(user_id, created_at DESC)"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_referral_feedback_source_created ON referral_feedback_messages(source, created_at DESC)"))


def _support_ticket_code() -> str:
    return f"{SUPPORT_TICKET_PREFIX}-{secrets.token_hex(3).upper()}"


def _support_row_payload(row: Any) -> dict[str, Any]:
    item = row._mapping if hasattr(row, "_mapping") else row
    created_at = item.get("created_at")
    answered_at = item.get("answered_at")
    return {
        "id": str(item.get("id")),
        "ticket_code": item.get("ticket_code"),
        "source": item.get("source"),
        "direction": item.get("direction"),
        "status": item.get("status"),
        "name": item.get("name"),
        "email": item.get("email"),
        "contact": item.get("contact"),
        "subject": item.get("subject"),
        "message": item.get("message"),
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or ""),
        "answered_at": answered_at.isoformat() if hasattr(answered_at, "isoformat") else None,
    }


async def _send_support_email(db: AsyncSession, recipient: str, ticket_code: str, reply_text: str) -> bool:
    recipient_norm = str(recipient or "").strip().lower()
    if not recipient_norm or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", recipient_norm):
        return False
    settings, _source = await load_smtp_settings(db)
    if not settings:
        logger.warning("SMTP is not configured; support email was not sent to %s", recipient_norm)
        return False
    message = EmailMessage()
    message["Subject"] = f"Ответ GLAME по обращению {ticket_code}"
    message["From"] = formataddr((settings.from_name, settings.from_email))
    message["To"] = recipient_norm
    message.set_content(
        f"Здравствуйте!\n\nОтвет по обращению {ticket_code}:\n\n{reply_text}\n\nGLAME Jewelry"
    )
    escaped_reply = html.escape(reply_text).replace("\n", "<br>")
    message.add_alternative(
        f"""<!doctype html>
<html>
  <body style="margin:0;background:#111;color:#f1f2f3;font-family:Arial,sans-serif;">
    <div style="max-width:620px;margin:0 auto;padding:32px 20px;">
      <div style="font-size:26px;letter-spacing:6px;margin-bottom:24px;">GLAME</div>
      <div style="background:#fff;color:#111;padding:28px;">
        <h2 style="margin:0 0 16px;">Ответ по обращению {html.escape(ticket_code)}</h2>
        <p style="line-height:1.55;">{escaped_reply}</p>
      </div>
    </div>
  </body>
</html>""",
        subtype="html",
    )
    await asyncio.to_thread(GiftCertificateEmailService(db)._send_message, settings, message)
    return True


async def _notify_admin_about_support_message(
    *,
    ticket_code: str,
    source: str,
    name: str | None,
    phone: str | None,
    email: str | None,
    subject: str | None,
    message: str,
) -> dict[str, Any]:
    lines = [
        f"Код: {ticket_code}",
        f"Источник: {source}",
        f"Имя: {name or '—'}",
        f"Телефон/контакт: {phone or '—'}",
        f"Email: {email or '—'}",
        f"Тема: {subject or '—'}",
        "",
        message,
        "",
        f"Ответить: /reply {ticket_code} текст ответа",
        SUPPORT_ADMIN_URL,
    ]
    return await TelegramNotificationService().notify_admin(
        title="GLAME partner support",
        lines=lines,
        severity="info",
    )


async def _handle_support_reply(db: AsyncSession, *, chat_id: str, text_value: str, message: dict[str, Any]) -> dict[str, Any]:
    notification_service = TelegramNotificationService()
    admin_chat_ids = {str(item) for item in notification_service.admin_chat_ids}
    if admin_chat_ids and chat_id not in admin_chat_ids:
        return {"status": "ignored", "reason": "not_admin_chat"}

    parts = text_value.split(maxsplit=2)
    if len(parts) < 3:
        async with TelegramService() as telegram:
            await telegram.send_message(chat_id=chat_id, text="Формат ответа: /reply GLSUP-ABC123 текст ответа")
        return {"status": "missing_reply_text"}

    ticket_code = parts[1].strip().upper()
    reply_text = parts[2].strip()
    if not ticket_code or not reply_text:
        async with TelegramService() as telegram:
            await telegram.send_message(chat_id=chat_id, text="Формат ответа: /reply GLSUP-ABC123 текст ответа")
        return {"status": "missing_reply_text"}

    await _ensure_referral_feedback_schema(db)
    original = (
        await db.execute(
            text(
                """
                SELECT *
                FROM referral_feedback_messages
                WHERE ticket_code = :ticket_code AND direction = 'user_to_admin'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"ticket_code": ticket_code},
        )
    ).first()
    if original is None:
        async with TelegramService() as telegram:
            await telegram.send_message(chat_id=chat_id, text=f"Обращение {ticket_code} не найдено.")
        return {"status": "not_found"}

    item = original._mapping
    message_id = str(message.get("message_id") or "").strip() or None
    await db.execute(
        text(
            """
            INSERT INTO referral_feedback_messages (
                id, ticket_code, source, direction, status, user_id, member_id,
                admin_chat_id, telegram_message_id, name, email, contact, subject,
                message, meta, answered_at
            )
            VALUES (
                :id, :ticket_code, :source, 'admin_to_user', 'sent', :user_id, :member_id,
                :admin_chat_id, :telegram_message_id, :name, :email, :contact, :subject,
                :message, CAST(:meta AS JSONB), now()
            )
            """
        ),
        {
            "id": uuid4(),
            "ticket_code": ticket_code,
            "source": item.get("source"),
            "user_id": item.get("user_id"),
            "member_id": item.get("member_id"),
            "admin_chat_id": chat_id,
            "telegram_message_id": message_id,
            "name": item.get("name"),
            "email": item.get("email"),
            "contact": item.get("contact"),
            "subject": item.get("subject"),
            "message": reply_text,
            "meta": json.dumps({"reply_source": "telegram_admin"}),
        },
    )
    await db.execute(
        text(
            """
            UPDATE referral_feedback_messages
            SET status = 'answered', answered_at = now()
            WHERE ticket_code = :ticket_code AND direction = 'user_to_admin'
            """
        ),
        {"ticket_code": ticket_code},
    )
    await db.commit()

    delivered: list[str] = []
    user_id = item.get("user_id")
    member_id = item.get("member_id")
    if user_id and member_id:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        member = (await db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == member_id))).scalar_one_or_none()
        partner_chat_id = _telegram_chat_id_from_partner(user, member)
        if partner_chat_id:
            try:
                async with TelegramService() as telegram:
                    await telegram.send_message(
                        chat_id=partner_chat_id,
                        text=f"Ответ GLAME по обращению {ticket_code}\n\n{reply_text}\n\nИстория доступна в разделе «Связь» партнерского кабинета.",
                    )
                delivered.append("partner_telegram")
            except Exception as error:  # noqa: BLE001
                logger.warning("Failed to send support reply to partner telegram: %s", error)
        if getattr(user, "email", None):
            try:
                if await _send_support_email(db, str(user.email), ticket_code, reply_text):
                    delivered.append("partner_email")
            except Exception as error:  # noqa: BLE001
                logger.warning("Failed to send support reply email: %s", error)
    elif item.get("email"):
        try:
            if await _send_support_email(db, str(item.get("email")), ticket_code, reply_text):
                delivered.append("email")
        except Exception as error:  # noqa: BLE001
            logger.warning("Failed to send public support reply email: %s", error)

    delivery_label = ", ".join(delivered) if delivered else "сохранено в истории, прямой канал не найден"
    async with TelegramService() as telegram:
        await telegram.send_message(chat_id=chat_id, text=f"Ответ по {ticket_code} принят: {delivery_label}.")
    return {"status": "ok", "ticket_code": ticket_code, "delivered": delivered}


@router.get("/me/support-messages")
async def get_my_support_messages(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_referral_feedback_schema(db)
    rows = (
        await db.execute(
            text(
                """
                SELECT *
                FROM referral_feedback_messages
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 80
                """
            ),
            {"user_id": current_user.id},
        )
    ).fetchall()
    return {"messages": [_support_row_payload(row) for row in reversed(rows)]}


@router.post("/me/support-messages")
async def create_my_support_message(
    payload: PartnerSupportMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    member = (
        await db.execute(select(ReferralProgramMember).where(ReferralProgramMember.user_id == current_user.id))
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=403, detail="Партнерская программа не подключена")

    message_text = payload.message.strip()
    subject = payload.subject.strip() if payload.subject else None
    ticket_code = _support_ticket_code()
    await _ensure_referral_feedback_schema(db)
    row_id = uuid4()
    await db.execute(
        text(
            """
            INSERT INTO referral_feedback_messages (
                id, ticket_code, source, direction, status, user_id, member_id,
                name, email, contact, subject, message, meta
            )
            VALUES (
                :id, :ticket_code, :source, 'user_to_admin', 'new', :user_id, :member_id,
                :name, :email, :contact, :subject, :message, CAST(:meta AS JSONB)
            )
            """
        ),
        {
            "id": row_id,
            "ticket_code": ticket_code,
            "source": "partner",
            "user_id": current_user.id,
            "member_id": member.id,
            "name": current_user.full_name,
            "email": current_user.email,
            "contact": current_user.phone,
            "subject": subject,
            "message": message_text,
            "meta": json.dumps({"category": payload.category or "partner"}),
        },
    )
    await db.commit()
    notify_result = await _notify_admin_about_support_message(
        ticket_code=ticket_code,
        source="partner",
        name=current_user.full_name,
        phone=current_user.phone,
        email=current_user.email,
        subject=subject,
        message=message_text,
    )
    return {
        "status": "ok",
        "ticket_code": ticket_code,
        "message": {
            "id": str(row_id),
            "ticket_code": ticket_code,
            "source": "partner",
            "direction": "user_to_admin",
            "status": "new",
            "name": current_user.full_name,
            "email": current_user.email,
            "contact": current_user.phone,
            "subject": subject,
            "message": message_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "answered_at": None,
        },
        "telegram": notify_result,
    }


@router.post("/public/support-messages")
async def create_public_support_message(
    payload: PublicSupportMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    email_norm = payload.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_norm):
        raise HTTPException(status_code=400, detail="Некорректный email")
    message_text = payload.message.strip()
    subject = payload.subject.strip() if payload.subject else "CryptoGLAME"
    ticket_code = _support_ticket_code()
    await _ensure_referral_feedback_schema(db)
    row_id = uuid4()
    await db.execute(
        text(
            """
            INSERT INTO referral_feedback_messages (
                id, ticket_code, source, direction, status,
                name, email, contact, subject, message, meta
            )
            VALUES (
                :id, :ticket_code, :source, 'user_to_admin', 'new',
                :name, :email, :contact, :subject, :message, CAST(:meta AS JSONB)
            )
            """
        ),
        {
            "id": row_id,
            "ticket_code": ticket_code,
            "source": "glm_public",
            "name": payload.name.strip() if payload.name else None,
            "email": email_norm,
            "contact": payload.contact.strip() if payload.contact else None,
            "subject": subject,
            "message": message_text,
            "meta": json.dumps({"page": payload.page or "glm"}),
        },
    )
    await db.commit()
    notify_result = await _notify_admin_about_support_message(
        ticket_code=ticket_code,
        source="glm_public",
        name=payload.name,
        phone=payload.contact,
        email=email_norm,
        subject=subject,
        message=message_text,
    )
    return {"status": "ok", "ticket_code": ticket_code, "telegram": notify_result}


@router.post("/admin/telegram-notifications/broadcast")
async def admin_send_telegram_notification_broadcast(
    payload: AdminTelegramBroadcastRequest,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    config = TelegramNotificationService.config_payload()
    if not payload.dry_run and (not config.get("enabled") or not config.get("bot_token_configured")):
        raise HTTPException(status_code=400, detail="Telegram notifications are not configured")

    conditions = []
    if payload.audience == "active_connected":
        conditions.append(ReferralProgramMember.status == "active")
    rows = (
        await db.execute(
            select(ReferralProgramMember, User)
            .join(User, User.id == ReferralProgramMember.user_id)
            .where(*conditions)
            .order_by(desc(ReferralProgramMember.created_at))
        )
    ).all()

    recipients_by_chat: dict[str, dict[str, Any]] = {}
    for member, user in rows:
        if not _telegram_partner_allows(member, "marketing"):
            continue
        chat_id = _telegram_chat_id_from_partner(user, member)
        if not chat_id:
            continue
        recipients_by_chat.setdefault(
            chat_id,
            {
                "chat_id": chat_id,
                "member_id": str(member.id),
                "partner_name": user.full_name or user.phone or "Партнер GLAME",
                "status": member.status,
            },
        )

    recipients = list(recipients_by_chat.values())
    if payload.dry_run:
        return {
            "status": "dry_run",
            "audience": payload.audience,
            "recipients_count": len(recipients),
            "sample": recipients[:10],
            "telegram_notifications": config,
        }

    text = "\n".join(
        [
            "GLAME Partner",
            payload.title.strip(),
            "",
            payload.message.strip(),
            "",
            os.getenv("TELEGRAM_PARTNER_PORTAL_URL", "https://partner.glamejewelry.ru/referral"),
        ]
    )[:3900]

    sent = 0
    failed = 0
    errors: list[dict[str, str]] = []
    async with TelegramService() as telegram:
        for recipient in recipients:
            try:
                await telegram.send_message(chat_id=recipient["chat_id"], text=text)
                sent += 1
            except Exception as error:  # noqa: BLE001 - broadcast must continue for other partners
                failed += 1
                errors.append(
                    {
                        "member_id": recipient["member_id"],
                        "partner_name": recipient["partner_name"],
                        "error": str(error)[:300],
                    }
                )
                logger.warning("Telegram partner broadcast failed for member %s: %s", recipient["member_id"], error)

    await TelegramNotificationService().notify_admin(
        title="Рассылка партнерам отправлена",
        lines=[
            f"Тема: {payload.title.strip()}",
            f"Аудитория: {payload.audience}",
            f"Отправлено: {sent}",
            f"Ошибок: {failed}",
        ],
        severity="success" if failed == 0 else "warning",
    )
    return {
        "status": "success" if failed == 0 else "partial",
        "audience": payload.audience,
        "recipients_count": len(recipients),
        "sent": sent,
        "failed": failed,
        "errors": errors[:20],
        "telegram_notifications": config,
    }


@router.get("/admin/telegram-notifications/bridge-alerts/status")
async def admin_telegram_bridge_alerts_status(
    request: Request,
    _current_user: User = Depends(require_admin()),
):
    return {
        "status": "configured" if GlmTelegramAlertService.config_payload().get("enabled") else "disabled",
        "alerts": GlmTelegramAlertService.config_payload(),
        "telegram_notifications": TelegramNotificationService.config_payload(),
        "scheduler": glm_token_scheduler_status(request.app).get("telegram_alerts"),
        "next_steps": [
            "Scheduler sends admin Telegram alerts for stale bridge pending, TON waiting and 1C issues.",
            "Cooldown prevents repeated messages for unchanged alerts.",
            "Critical alerts go out immediately; warning/non-critical alerts can be grouped into digest mode.",
            "TON treasury balance reconciliation and low-balance alerts are included in the same escalation flow.",
        ],
    }


@router.post("/admin/telegram-notifications/bridge-alerts/run")
async def admin_run_telegram_bridge_alerts(
    payload: AdminTelegramAlertsRunRequest,
    _current_user: User = Depends(require_admin()),
):
    result = await run_glm_telegram_alerts(force=payload.force)
    return {
        "status": result.get("status"),
        "result": result,
        "alerts": GlmTelegramAlertService.config_payload(),
        "telegram_notifications": TelegramNotificationService.config_payload(),
    }


@router.post("/admin/glm-ton-settlement/run")
async def admin_run_glm_ton_settlement(
    payload: AdminGlmTonSettlementRunRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    result = await TonGlmSettlementService(db).settle_pending_claims(
        admin_user_id=current_user.id,
        limit=payload.limit,
        require_verified=payload.require_verified,
    )
    await db.commit()
    return {
        "status": "success",
        "result": result,
    }


@router.post("/admin/glm-ton-auto-transfer/run")
async def admin_run_glm_ton_auto_transfer(
    payload: AdminGlmTonAutoTransferRunRequest,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    result = await TonGlmAutoTransferService(db).process_pending_claims(limit=payload.limit)
    await db.commit()
    return {
        "status": "success",
        "result": result,
    }


@router.post("/admin/glm-ton-auto-transfer/override")
async def admin_set_glm_ton_auto_transfer_override(
    payload: AdminGlmTonAutoTransferOverrideRequest,
    current_user: User = Depends(require_admin()),
):
    override = TonGlmAutoTransferService.write_override(
        enabled=payload.enabled,
        reason=payload.reason,
        admin_user_id=current_user.id,
    )
    return {
        "status": "enabled" if payload.enabled else "disabled",
        "override": override,
        "config": TonGlmAutoTransferService.config_payload(),
    }


@router.get("/admin/glm-hot-wallet-limits")
async def admin_get_glm_hot_wallet_limits(
    _current_user: User = Depends(require_admin()),
):
    return {
        "status": "success",
        "config": TonGlmTreasuryBalanceService.config_payload(),
    }


@router.post("/admin/glm-hot-wallet-limits")
async def admin_set_glm_hot_wallet_limits(
    payload: AdminGlmHotWalletLimitsRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    if payload.hot_wallet_refill_ton_target < payload.hot_wallet_refill_ton_threshold:
        raise HTTPException(status_code=400, detail="TON target должен быть не меньше TON threshold")
    override = TonGlmTreasuryBalanceService.write_limits_override(
        hot_wallet_refill_glm_threshold=payload.hot_wallet_refill_glm_threshold,
        hot_wallet_refill_ton_threshold=payload.hot_wallet_refill_ton_threshold,
        hot_wallet_refill_glm_target=payload.hot_wallet_refill_glm_target,
        hot_wallet_refill_ton_target=payload.hot_wallet_refill_ton_target,
        admin_user_id=current_user.id,
    )
    return {
        "status": "success",
        "override": override,
        "config": TonGlmTreasuryBalanceService.config_payload(),
        "treasury_balances": await TonGlmTreasuryBalanceService(db).payload(),
    }


@router.get("/admin/glm-redemptions")
async def admin_list_glm_redemptions(
    status_filter: str | None = Query(default="pending_fulfillment", alias="status"),
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(GlameTokenTransaction, ReferralProgramMember, User)
        .join(ReferralProgramMember, ReferralProgramMember.id == GlameTokenTransaction.referral_member_id)
        .join(User, User.id == ReferralProgramMember.user_id)
        .where(GlameTokenTransaction.transaction_type == "redemption")
        .order_by(desc(GlameTokenTransaction.created_at))
        .offset(offset)
        .limit(limit)
    )
    count_stmt = select(func.count(GlameTokenTransaction.id)).where(
        GlameTokenTransaction.transaction_type == "redemption"
    )
    if status_filter:
        stmt = stmt.where(GlameTokenTransaction.status == status_filter)
        count_stmt = count_stmt.where(GlameTokenTransaction.status == status_filter)
    rows = (await db.execute(stmt)).all()
    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    return {
        "redemptions": [_glm_transaction_payload(tx, member, user) for tx, member, user in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.patch("/admin/glm-redemptions/{redemption_id}")
async def admin_update_glm_redemption(
    redemption_id: UUID,
    payload: AdminGlmRedemptionStatusRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == redemption_id,
                GlameTokenTransaction.transaction_type == "redemption",
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="GLM redemption не найден")
    try:
        tx = await GlameTokenService(db).update_redemption_status(
            redemption=tx,
            status=payload.status,
            admin_user_id=current_user.id,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    return {"status": "success", "redemption": _glm_transaction_payload(tx)}


@router.post("/admin/glm-redemptions/{redemption_id}/ton-refund-transaction")
async def admin_prepare_glm_redemption_ton_refund(
    redemption_id: UUID,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == redemption_id,
                GlameTokenTransaction.transaction_type == "redemption",
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="GLM redemption не найден")
    try:
        payload = await GlameTokenService(db).prepare_redemption_ton_refund_transaction(redemption=tx)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    return {"status": "success", **payload}


@router.post("/admin/glm-redemptions/{redemption_id}/ton-refund-record")
async def admin_record_glm_redemption_ton_refund(
    redemption_id: UUID,
    payload: AdminGlmRedemptionTonRefundRecordRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == redemption_id,
                GlameTokenTransaction.transaction_type == "redemption",
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="GLM redemption не найден")
    try:
        tx = await GlameTokenService(db).record_redemption_ton_refund(
            redemption=tx,
            admin_user_id=current_user.id,
            tx_hash=payload.tx_hash,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    return {"status": "success", "redemption": _glm_transaction_payload(tx)}


@router.post("/admin/glm-redemptions/{redemption_id}/ton-refund-settlement")
async def admin_settle_glm_redemption_ton_refund(
    redemption_id: UUID,
    payload: AdminGlmRedemptionTonRefundSettlementRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await TonGlmSettlementService(db).settle_redemption_ton_refund_by_tx_hash(
            redemption_id=redemption_id,
            tx_hash=payload.tx_hash,
            admin_user_id=current_user.id,
            comment=payload.comment,
            require_verified=payload.require_verified,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    return {
        "status": result.get("status"),
        "redemption": _glm_transaction_payload(result["redemption"]),
        "verification": result.get("verification"),
    }


@router.get("/admin/glm-bridge/glm-to-points")
async def admin_list_glm_to_points_bridge(
    status_filter: str | None = Query(default="pending", alias="status"),
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    conditions = [
        GlameTokenTransaction.transaction_type == "bridge",
        GlameTokenTransaction.reason.in_(("glm_to_points_bridge", "buy_loyalty_points")),
    ]
    if status_filter:
        conditions.append(GlameTokenTransaction.status == status_filter)
    stmt = (
        select(GlameTokenTransaction, ReferralProgramMember, User, GlameTokenBridgeOperation)
        .join(ReferralProgramMember, ReferralProgramMember.id == GlameTokenTransaction.referral_member_id)
        .join(User, User.id == ReferralProgramMember.user_id)
        .outerjoin(GlameTokenBridgeOperation, GlameTokenBridgeOperation.transaction_id == GlameTokenTransaction.id)
        .where(*conditions)
        .order_by(desc(GlameTokenTransaction.created_at))
        .offset(offset)
        .limit(limit)
    )
    count_stmt = select(func.count(GlameTokenTransaction.id)).where(*conditions)
    rows = (await db.execute(stmt)).all()
    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    return {
        "bridges": [_glm_transaction_payload(tx, member, user, operation) for tx, member, user, operation in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.patch("/admin/glm-bridge/glm-to-points/{bridge_id}")
async def admin_update_glm_to_points_bridge(
    bridge_id: UUID,
    payload: AdminGlmToPointsBridgeStatusRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == bridge_id,
                GlameTokenTransaction.transaction_type == "bridge",
                GlameTokenTransaction.reason.in_(("glm_to_points_bridge", "buy_loyalty_points")),
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="GLM -> баллы bridge не найден")
    try:
        tx = await GlameTokenService(db).update_glm_to_points_bridge_status(
            bridge=tx,
            status=payload.status,
            admin_user_id=current_user.id,
            points=payload.points,
            comment=payload.comment,
            onec_document_id=payload.onec_document_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    return {"status": "success", "bridge": _glm_transaction_payload(tx)}


@router.post("/admin/glm-bridge/glm-to-points/{bridge_id}/ton-deposit")
async def admin_settle_glm_to_points_bridge_with_ton_deposit(
    bridge_id: UUID,
    payload: AdminGlmTonSettlementRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await TonGlmSettlementService(db).settle_glm_to_points_bridge_by_deposit_tx_hash(
            bridge_id=bridge_id,
            tx_hash=payload.tx_hash,
            admin_user_id=current_user.id,
            comment=payload.comment,
            require_verified=payload.require_verified,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    bridge = result.get("bridge")
    return {
        "status": result.get("status"),
        "bridge": _glm_transaction_payload(bridge) if isinstance(bridge, GlameTokenTransaction) else None,
        "verification": result.get("verification"),
    }


@router.get("/admin/glm-bridge/operations")
async def admin_list_glm_bridge_operations(
    direction: str | None = Query(default=None, pattern="^(points_to_glm|glm_to_points|buy_glm_with_ton|sell_glm_for_ton)$"),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=1000),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    conditions = [GlameTokenBridgeOperation.token_code == "GLM"]
    if direction:
        conditions.append(GlameTokenBridgeOperation.direction == direction)
    if status_filter:
        conditions.append(GlameTokenBridgeOperation.status == status_filter)
    rows = (
        await db.execute(
            select(GlameTokenBridgeOperation, ReferralProgramMember, User)
            .outerjoin(ReferralProgramMember, ReferralProgramMember.id == GlameTokenBridgeOperation.referral_member_id)
            .outerjoin(User, User.id == GlameTokenBridgeOperation.user_id)
            .where(*conditions)
            .order_by(desc(GlameTokenBridgeOperation.created_at), desc(GlameTokenBridgeOperation.id))
            .limit(limit)
        )
    ).all()
    total = (
        await db.execute(select(func.count(GlameTokenBridgeOperation.id)).where(*conditions))
    ).scalar_one() or 0
    return {
        "count": int(total or 0),
        "limit": limit,
        "operations": [_glm_bridge_operation_payload(operation, member, user) for operation, member, user in rows],
    }


async def _glm_operations_attention_payload(db: AsyncSession, *, limit: int = 50) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    stale_minutes = int(os.getenv("TON_GLM_OPERATIONS_ATTENTION_STALE_MINUTES", "60") or 60)
    stale_before = now - timedelta(minutes=stale_minutes)
    bridge_ton_waiting_statuses = {
        "sent",
        "sent_waiting_settlement",
        "wallet_request_prepared",
        "waiting_for_deposit",
        "not_found",
    }
    bridge_onec_issue_statuses = {
        "failed",
        "missing_discount_card",
        "ready_for_1c",
        "ready_for_1c_spend",
        "posted_without_balance_change",
        "created_without_ref_key",
    }
    closed_statuses = {"processed", "canceled", "cancelled", "superseded", "failed_reviewed", "manual_reviewed"}

    def normalize_dt(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def age_minutes(value: datetime | None) -> int:
        normalized = normalize_dt(value)
        if normalized is None:
            return 0
        return max(0, int((now - normalized).total_seconds() // 60))

    def append_item(items: list[dict[str, Any]], item: dict[str, Any]) -> None:
        item["created_at"] = normalize_dt(item.get("created_at")).isoformat() if item.get("created_at") else None
        item["updated_at"] = normalize_dt(item.get("updated_at")).isoformat() if item.get("updated_at") else None
        item["checked_at"] = now.isoformat()
        items.append(item)

    def operator_events_from_meta(meta: Any, keys: list[str]) -> list[dict[str, Any]]:
        if not isinstance(meta, dict):
            return []
        events: list[dict[str, Any]] = []
        for key in keys:
            history = meta.get(key)
            if not isinstance(history, list):
                continue
            for raw_event in history:
                if not isinstance(raw_event, dict):
                    continue
                event = {
                    "source": key,
                    "action": raw_event.get("action"),
                    "at": raw_event.get("at"),
                    "admin_user_id": raw_event.get("admin_user_id"),
                    "comment": raw_event.get("comment"),
                    "onec_status": raw_event.get("onec_sync_status") or raw_event.get("onec_spend_sync_status"),
                    "onec_document_id": raw_event.get("onec_document_id") or raw_event.get("onec_spend_document_id"),
                }
                events.append(event)
        events.sort(key=lambda event: str(event.get("at") or ""), reverse=True)
        return events[:5]

    def latest_operator_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
        return events[0] if events else None

    items: list[dict[str, Any]] = []
    bridge_rows = (
        await db.execute(
            select(GlameTokenBridgeOperation, GlameTokenTransaction, ReferralProgramMember, User)
            .join(GlameTokenTransaction, GlameTokenTransaction.id == GlameTokenBridgeOperation.transaction_id)
            .outerjoin(ReferralProgramMember, ReferralProgramMember.id == GlameTokenBridgeOperation.referral_member_id)
            .outerjoin(User, User.id == GlameTokenBridgeOperation.user_id)
            .where(GlameTokenBridgeOperation.token_code == "GLM")
            .order_by(desc(GlameTokenBridgeOperation.updated_at), desc(GlameTokenBridgeOperation.created_at))
            .limit(500)
        )
    ).all()
    for operation, tx, _member, user in bridge_rows:
        requested_at = normalize_dt(operation.requested_at or operation.created_at)
        updated_at = normalize_dt(operation.updated_at or operation.created_at)
        op_status = str(operation.status or "")
        ton_status = str(operation.ton_status or "")
        onec_status = str(operation.onec_status or "")
        is_open = op_status not in closed_statuses
        is_stale = op_status == "pending" and requested_at is not None and requested_at < stale_before
        is_ton_waiting = op_status == "pending" and ton_status in bridge_ton_waiting_statuses
        is_onec_issue = is_open and onec_status in bridge_onec_issue_statuses
        if not (is_stale or is_ton_waiting or is_onec_issue):
            continue

        kind = "bridge_stale_pending"
        severity = "warning"
        title = "Зависшая bridge-операция"
        action_code = "mark_reviewed"
        action_hint = "Проверьте историю операции, TON tx и 1C документ; если все корректно, отметьте как проверенную."
        if is_onec_issue:
            kind = "bridge_onec_issue"
            severity = "critical"
            title = "Bridge требует действия в 1C"
            action_code = "retry_onec_spend" if operation.direction == "points_to_glm" else "retry_onec_bridge"
            action_hint = "Повторите 1C sync/repair. Для ручного документа укажите ID документа 1C в поле repair."
        elif is_ton_waiting:
            kind = "bridge_ton_waiting"
            severity = "critical" if age_minutes(requested_at) >= stale_minutes else "warning"
            title = "Bridge ждет TON-подтверждение"
            action_code = "settle_ton_transfer" if operation.direction == "points_to_glm" else "settle_glm_deposit"
            action_hint = (
                "Проверьте TON settlement. Если tx hash уже есть, можно повторить проверку TON."
                if operation.ton_tx_hash
                else "Дождитесь TON tx или внесите tx hash вручную в соответствующей очереди."
            )
        tx_meta = tx.meta if isinstance(tx.meta, dict) else {}
        operator_events = operator_events_from_meta(
            tx_meta,
            ["onec_spend_repair_history", "repair_history", "onec_cancel_spend_repair_history"],
        )
        append_item(
            items,
            {
                "id": str(operation.id),
                "operation_id": str(operation.id),
                "transaction_id": str(operation.transaction_id),
                "account_id": str(operation.account_id),
                "member_id": str(operation.referral_member_id) if operation.referral_member_id else None,
                "user_id": str(operation.user_id),
                "kind": kind,
                "severity": severity,
                "title": title,
                "partner_name": getattr(user, "full_name", None) or "Партнер GLAME",
                "partner_phone": getattr(user, "phone", None),
                "direction": operation.direction,
                "status": operation.status,
                "glm_amount": int(operation.glm_amount or tx.amount or 0),
                "points_amount": int(operation.points_amount or 0),
                "ton_status": operation.ton_status,
                "ton_tx_hash": operation.ton_tx_hash,
                "onec_status": operation.onec_status,
                "onec_document_id": operation.onec_document_id,
                "message": operation.onec_error or action_hint,
                "action_code": action_code,
                "action_hint": action_hint,
                "operator_events": operator_events,
                "latest_operator_event": latest_operator_event(operator_events),
                "age_minutes": age_minutes(requested_at),
                "created_at": requested_at,
                "updated_at": updated_at,
            },
        )

    refund_rows = (
        await db.execute(
            select(GlameTokenTransaction, ReferralProgramMember, User)
            .outerjoin(ReferralProgramMember, ReferralProgramMember.id == GlameTokenTransaction.referral_member_id)
            .outerjoin(User, User.id == GlameTokenTransaction.user_id)
            .where(
                GlameTokenTransaction.token_code == "GLM",
                GlameTokenTransaction.transaction_type == "redemption",
                GlameTokenTransaction.status.in_(("canceled", "cancelled", "failed", "refund_pending", "refund_required")),
            )
            .order_by(desc(GlameTokenTransaction.created_at))
            .limit(200)
        )
    ).all()
    for tx, _member, user in refund_rows:
        meta = tx.meta if isinstance(tx.meta, dict) else {}
        refund_required = bool(meta.get("ton_refund_required"))
        refund_status = str(meta.get("ton_refund_status") or "")
        if not refund_required and refund_status not in {"required", "submitted", "pending", "sent"}:
            continue
        created_at = normalize_dt(tx.created_at)
        has_refund_tx = bool(_normalize_ton_tx_hash(meta.get("ton_refund_tx_hash")))
        refund_events: list[dict[str, Any]] = []
        if meta.get("ton_refund_submitted_at") or meta.get("ton_refund_processed_by") or meta.get("ton_refund_comment"):
            refund_events.append(
                {
                    "source": "ton_refund",
                    "action": "record_ton_refund",
                    "at": meta.get("ton_refund_submitted_at"),
                    "admin_user_id": meta.get("ton_refund_processed_by"),
                    "comment": meta.get("ton_refund_comment"),
                    "ton_status": meta.get("ton_refund_status"),
                    "ton_tx_hash": meta.get("ton_refund_tx_hash"),
                }
            )
        append_item(
            items,
            {
                "id": str(tx.id),
                "operation_id": None,
                "transaction_id": str(tx.id),
                "account_id": str(tx.account_id),
                "member_id": str(tx.referral_member_id) if tx.referral_member_id else None,
                "user_id": str(tx.user_id),
                "kind": "refund_attention",
                "severity": "critical" if not has_refund_tx else "warning",
                "title": "GLM Store refund требует проверки",
                "partner_name": getattr(user, "full_name", None) or "Партнер GLAME",
                "partner_phone": getattr(user, "phone", None),
                "direction": "refund",
                "status": tx.status,
                "glm_amount": abs(int(tx.amount or 0)),
                "points_amount": int(meta.get("refunded_points") or 0),
                "ton_status": refund_status or None,
                "ton_tx_hash": meta.get("ton_refund_tx_hash"),
                "onec_status": meta.get("onec_spend_sync_status"),
                "onec_document_id": meta.get("onec_spend_document_id"),
                "message": meta.get("ton_refund_error") or "Проверьте refund: TON возврат, 1C/points rollback и статус заказа.",
                "action_code": "settle_refund" if has_refund_tx else "refund_review",
                "action_hint": (
                    "Проверьте уже записанный TON refund tx hash и закройте обязательство."
                    if has_refund_tx
                    else "Подготовьте TON refund из treasury wallet и подтвердите отправку в кошельке."
                ),
                "operator_events": refund_events,
                "latest_operator_event": latest_operator_event(refund_events),
                "age_minutes": age_minutes(created_at),
                "created_at": created_at,
                "updated_at": created_at,
            },
        )

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    items.sort(key=lambda item: (severity_rank.get(str(item.get("severity")), 9), -int(item.get("age_minutes") or 0)))
    limited_items = items[:limit]
    by_kind: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for item in items:
        by_kind[str(item.get("kind") or "unknown")] = by_kind.get(str(item.get("kind") or "unknown"), 0) + 1
        by_severity[str(item.get("severity") or "info")] = by_severity.get(str(item.get("severity") or "info"), 0) + 1
    return {
        "generated_at": now.isoformat(),
        "stale_minutes": stale_minutes,
        "count": len(items),
        "limit": limit,
        "by_kind": by_kind,
        "by_severity": by_severity,
        "items": limited_items,
    }


@router.get("/admin/glm-operations-attention")
async def admin_glm_operations_attention(
    limit: int = Query(default=50, ge=1, le=200),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    return await _glm_operations_attention_payload(db, limit=limit)


@router.get("/admin/glm-operations-attention/export.csv")
async def admin_glm_operations_attention_export_csv(
    limit: int = Query(default=500, ge=1, le=1000),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    payload = await _glm_operations_attention_payload(db, limit=limit)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["GLAME operations attention export"])
    writer.writerow(["generated_at", payload.get("generated_at")])
    writer.writerow(["stale_minutes", payload.get("stale_minutes")])
    writer.writerow(["total_count", payload.get("count")])
    writer.writerow(["export_limit", payload.get("limit")])
    writer.writerow([])
    writer.writerow(["severity", "count"])
    for severity, count in sorted((payload.get("by_severity") or {}).items()):
        writer.writerow([severity, count])
    writer.writerow([])
    writer.writerow(["kind", "count"])
    for kind, count in sorted((payload.get("by_kind") or {}).items()):
        writer.writerow([kind, count])
    writer.writerow([])
    writer.writerow([
        "severity",
        "kind",
        "title",
        "partner_name",
        "partner_phone",
        "direction",
        "status",
        "glm_amount",
        "points_amount",
        "ton_status",
        "ton_tx_hash",
        "onec_status",
        "onec_document_id",
        "age_minutes",
        "action_code",
        "action_hint",
        "message",
        "latest_operator_action",
        "latest_operator_at",
        "latest_operator_admin_user_id",
        "latest_operator_comment",
        "operator_events_json",
        "operation_id",
        "transaction_id",
        "account_id",
        "member_id",
        "user_id",
        "created_at",
        "updated_at",
        "checked_at",
    ])
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        latest_event = item.get("latest_operator_event") if isinstance(item.get("latest_operator_event"), dict) else {}
        writer.writerow([
            item.get("severity") or "",
            item.get("kind") or "",
            item.get("title") or "",
            item.get("partner_name") or "",
            item.get("partner_phone") or "",
            item.get("direction") or "",
            item.get("status") or "",
            item.get("glm_amount") if item.get("glm_amount") is not None else "",
            item.get("points_amount") if item.get("points_amount") is not None else "",
            item.get("ton_status") or "",
            item.get("ton_tx_hash") or "",
            item.get("onec_status") or "",
            item.get("onec_document_id") or "",
            item.get("age_minutes") if item.get("age_minutes") is not None else "",
            item.get("action_code") or "",
            item.get("action_hint") or "",
            item.get("message") or "",
            latest_event.get("action") or "",
            latest_event.get("at") or "",
            latest_event.get("admin_user_id") or "",
            latest_event.get("comment") or "",
            json.dumps(item.get("operator_events") or [], ensure_ascii=False),
            item.get("operation_id") or "",
            item.get("transaction_id") or "",
            item.get("account_id") or "",
            item.get("member_id") or "",
            item.get("user_id") or "",
            item.get("created_at") or "",
            item.get("updated_at") or "",
            item.get("checked_at") or "",
        ])
    filename_date = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"glm-operations-attention-{filename_date}.csv"
    content = output.getvalue().encode("utf-8-sig")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/admin/glm-bridge/operations/{operation_id}/claim")
async def admin_update_glm_claim_by_bridge_operation(
    operation_id: UUID,
    payload: AdminGlmClaimStatusRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    operation = await _get_glm_bridge_operation_or_404(db, operation_id, direction="points_to_glm")
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == operation.transaction_id,
                GlameTokenTransaction.transaction_type == "claim",
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="GLM claim transaction не найдена")
    try:
        tx = await GlameTokenService(db).update_claim_status(
            claim=tx,
            status=payload.status,
            admin_user_id=current_user.id,
            tx_hash=payload.tx_hash,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    operation = await _get_glm_bridge_operation_or_404(db, operation_id, direction="points_to_glm")
    await db.commit()
    return {
        "status": "success",
        "claim": _glm_claim_payload(tx, operation=operation),
        "operation": _glm_bridge_operation_payload(operation),
    }


@router.post("/admin/glm-bridge/operations/{operation_id}/claim-ton-settlement")
async def admin_settle_glm_claim_by_bridge_operation(
    operation_id: UUID,
    payload: AdminGlmTonSettlementRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    operation = await _get_glm_bridge_operation_or_404(db, operation_id, direction="points_to_glm")
    try:
        result = await TonGlmSettlementService(db).settle_claim_by_tx_hash(
            claim_id=operation.transaction_id,
            tx_hash=payload.tx_hash,
            admin_user_id=current_user.id,
            comment=payload.comment,
            require_verified=payload.require_verified,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    operation = await _get_glm_bridge_operation_or_404(db, operation_id, direction="points_to_glm")
    await db.commit()
    claim = result.get("claim")
    return {
        "status": result.get("status"),
        "claim": _glm_claim_payload(claim, operation=operation) if isinstance(claim, GlameTokenTransaction) else None,
        "operation": _glm_bridge_operation_payload(operation),
        "verification": result.get("verification"),
    }


@router.patch("/admin/glm-bridge/operations/{operation_id}/glm-to-points")
async def admin_update_glm_to_points_bridge_by_operation(
    operation_id: UUID,
    payload: AdminGlmToPointsBridgeStatusRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    operation = await _get_glm_bridge_operation_or_404(db, operation_id, direction="glm_to_points")
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == operation.transaction_id,
                GlameTokenTransaction.transaction_type == "bridge",
                GlameTokenTransaction.reason.in_(("glm_to_points_bridge", "buy_loyalty_points")),
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="GLM -> баллы bridge transaction не найдена")
    try:
        tx = await GlameTokenService(db).update_glm_to_points_bridge_status(
            bridge=tx,
            status=payload.status,
            admin_user_id=current_user.id,
            points=payload.points,
            comment=payload.comment,
            onec_document_id=payload.onec_document_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    operation = await _get_glm_bridge_operation_or_404(db, operation_id, direction="glm_to_points")
    await db.commit()
    return {
        "status": "success",
        "bridge": _glm_transaction_payload(tx, operation=operation),
        "operation": _glm_bridge_operation_payload(operation),
    }


@router.post("/admin/glm-bridge/operations/{operation_id}/glm-to-points-ton-deposit")
async def admin_settle_glm_to_points_bridge_by_operation(
    operation_id: UUID,
    payload: AdminGlmTonSettlementRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    operation = await _get_glm_bridge_operation_or_404(db, operation_id, direction="glm_to_points")
    try:
        result = await TonGlmSettlementService(db).settle_glm_to_points_bridge_by_deposit_tx_hash(
            bridge_id=operation.transaction_id,
            tx_hash=payload.tx_hash,
            admin_user_id=current_user.id,
            comment=payload.comment,
            require_verified=payload.require_verified,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    operation = await _get_glm_bridge_operation_or_404(db, operation_id, direction="glm_to_points")
    await db.commit()
    bridge = result.get("bridge")
    return {
        "status": result.get("status"),
        "bridge": _glm_transaction_payload(bridge, operation=operation) if isinstance(bridge, GlameTokenTransaction) else None,
        "operation": _glm_bridge_operation_payload(operation),
        "verification": result.get("verification"),
    }


@router.post("/admin/glm-bridge/operations/{operation_id}/repair")
async def admin_repair_glm_bridge_by_operation(
    operation_id: UUID,
    payload: AdminGlmBridgeRepairRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    operation = await _get_glm_bridge_operation_or_404(db, operation_id, direction="glm_to_points")
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == operation.transaction_id,
                GlameTokenTransaction.transaction_type == "bridge",
                GlameTokenTransaction.reason.in_(("glm_to_points_bridge", "buy_loyalty_points")),
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="GLM bridge transaction не найдена")
    try:
        tx = await GlameTokenService(db).repair_glm_bridge_onec_sync(
            bridge=tx,
            action=payload.action,
            admin_user_id=current_user.id,
            onec_document_id=payload.onec_document_id,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    operation = await _get_glm_bridge_operation_or_404(db, operation_id, direction="glm_to_points")
    await db.commit()
    return {
        "status": "success",
        "bridge": _glm_transaction_payload(tx, operation=operation),
        "operation": _glm_bridge_operation_payload(operation),
    }


@router.patch("/admin/glm-exchange-desk/{exchange_id}")
async def admin_update_glm_exchange_desk(
    exchange_id: UUID,
    payload: AdminGlmExchangeDeskUpdateRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    exchange = (
        await db.execute(
            select(GlameTokenTransaction)
            .where(
                GlameTokenTransaction.id == exchange_id,
                GlameTokenTransaction.transaction_type == "bridge",
                GlameTokenTransaction.reason == "sell_glm_for_ton",
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if exchange is None:
        raise HTTPException(status_code=404, detail="GLM -> GRAM exchange desk request не найдена")
    if exchange.status != "pending":
        raise HTTPException(status_code=400, detail="Можно закрыть только pending exchange desk request")
    if payload.status == "processed" and not (payload.payout_tx_hash or "").strip():
        raise HTTPException(status_code=400, detail="Для processed нужен GRAM payout tx hash")

    meta = exchange.meta if isinstance(exchange.meta, dict) else {}
    now_iso = datetime.now(timezone.utc).isoformat()
    exchange.status = payload.status
    exchange.meta = {
        **meta,
        "gram_payout_status": "sent" if payload.status == "processed" else payload.status,
        "gram_payout_tx_hash": (payload.payout_tx_hash or "").strip() or None,
        "tx_hash": (payload.payout_tx_hash or "").strip() or meta.get("tx_hash"),
        "admin_comment": (payload.comment or "").strip() or meta.get("admin_comment"),
        "admin_user_id": str(current_user.id),
        "processed_at": now_iso if payload.status == "processed" else meta.get("processed_at"),
        "closed_at": now_iso,
    }
    flag_modified(exchange, "meta")
    await db.flush()
    operation = await GlameTokenService(db).sync_bridge_operation(exchange)
    await db.commit()
    return {
        "status": "success",
        "exchange": _glm_transaction_payload(exchange, operation=operation),
        "operation": _glm_bridge_operation_payload(operation) if operation else None,
    }


@router.post("/admin/glm-bridge/operations/{operation_id}/points-to-glm-spend-repair")
async def admin_repair_points_to_glm_spend_by_operation(
    operation_id: UUID,
    payload: AdminPointsToGlmSpendRepairRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    operation = await _get_glm_bridge_operation_or_404(db, operation_id, direction="points_to_glm")
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == operation.transaction_id,
                GlameTokenTransaction.transaction_type.in_(("claim", "conversion")),
                GlameTokenTransaction.reason.in_(("points_to_ton_bridge", "points_to_glm_bridge")),
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="Points -> GLM transaction не найдена")
    try:
        tx = await GlameTokenService(db).repair_points_to_glm_spend_sync(
            transaction=tx,
            action=payload.action,
            admin_user_id=current_user.id,
            onec_document_id=payload.onec_document_id,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    operation = await _get_glm_bridge_operation_or_404(db, operation_id, direction="points_to_glm")
    await db.commit()
    return {
        "status": "success",
        "transaction": _glm_transaction_payload(tx, operation=operation),
        "operation": _glm_bridge_operation_payload(operation),
    }


@router.post("/admin/glm-bridge/operations/{operation_id}/reconciliation-action")
async def admin_run_glm_bridge_reconciliation_action_by_operation(
    operation_id: UUID,
    payload: AdminGlmBridgeIssueActionRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    operation = await _get_glm_bridge_operation_or_404(db, operation_id)
    transaction_id = operation.transaction_id
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(GlameTokenTransaction.id == transaction_id)
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="GLM transaction не найдена")

    try:
        if payload.action == "settle_ton_transfer":
            tx_hash = (payload.tx_hash or "").strip()
            if tx_hash:
                result = await TonGlmSettlementService(db).settle_claim_by_tx_hash(
                    claim_id=transaction_id,
                    tx_hash=tx_hash,
                    admin_user_id=current_user.id,
                    comment=payload.comment or "Reconciliation action: settle TON transfer.",
                    require_verified=True,
                )
            else:
                result = await TonGlmAutoTransferService(db).process_claim(claim=tx)
            operation = await _get_glm_bridge_operation_or_404(db, operation_id)
            await db.commit()
            claim = result.get("claim") if isinstance(result, dict) else None
            return {
                "status": result.get("status") if isinstance(result, dict) else "success",
                "result": result,
                "operation": _glm_bridge_operation_payload(operation),
                "transaction": _glm_transaction_payload(claim, operation=operation) if isinstance(claim, GlameTokenTransaction) else None,
            }

        if payload.action == "cancel_onec_spend":
            tx = await GlameTokenService(db).repair_points_to_glm_cancel_spend_sync(
                transaction_id=transaction_id,
                admin_user_id=current_user.id,
                comment=payload.comment,
            )
            operation = await _get_glm_bridge_operation_or_404(db, operation_id)
            await db.commit()
            return {
                "status": "success",
                "operation": _glm_bridge_operation_payload(operation),
                "transaction": _glm_transaction_payload(tx, operation=operation),
            }

        tx = await GlameTokenService(db).mark_points_to_glm_reconciliation_review(
            transaction_id=transaction_id,
            action=payload.action,
            admin_user_id=current_user.id,
            issue_code=payload.issue_code,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    operation = await _get_glm_bridge_operation_or_404(db, operation_id)
    await db.commit()
    return {
        "status": "success",
        "operation": _glm_bridge_operation_payload(operation),
        "transaction": _glm_transaction_payload(tx, operation=operation),
    }


@router.get("/admin/glm-bridge/reconciliation")
async def admin_glm_bridge_reconciliation(
    stale_hours: int = Query(default=48, ge=1, le=720),
    limit: int = Query(default=500, ge=1, le=5000),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    return await GlameTokenService(db).reconcile_bridge_operations(stale_hours=stale_hours, limit=limit)


@router.get("/admin/glm-loyalty-reconciliation")
async def admin_glm_loyalty_reconciliation(
    limit: int = Query(default=50, ge=1, le=200),
    only_issues: bool = Query(default=False),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(ReferralProgramMember, User)
            .join(User, User.id == ReferralProgramMember.user_id)
            .where(User.discount_card_id_1c.is_not(None))
            .order_by(desc(ReferralProgramMember.created_at))
            .limit(limit)
        )
    ).all()
    items: list[dict[str, Any]] = []
    checked_at = datetime.now(timezone.utc).isoformat()
    lots_alerts_enabled = bool(GlmTelegramAlertService.config_payload().get("loyalty_lots_alerts_enabled"))
    async with OneCCustomersService() as onec:
        for member, user in rows:
            platform_points = int(getattr(user, "loyalty_points", 0) or 0)
            onec_working_balance: int | None = None
            onec_lots_balance: int | None = None
            errors: list[str] = []
            try:
                payload = await onec.fetch_loyalty_balance(
                    getattr(user, "customer_id_1c", None),
                    getattr(user, "discount_card_id_1c", None),
                )
                if payload and payload.get("balance") is not None:
                    onec_working_balance = int(payload.get("balance") or 0)
            except Exception as error:
                errors.append(f"working_balance: {str(error)[:500]}")
            if lots_alerts_enabled:
                try:
                    lots_payload = await onec.fetch_loyalty_lots_balance(
                        getattr(user, "customer_id_1c", None),
                        getattr(user, "discount_card_id_1c", None),
                    )
                    if lots_payload and lots_payload.get("balance") is not None:
                        onec_lots_balance = int(lots_payload.get("balance") or 0)
                except Exception as error:
                    errors.append(f"lots_balance: {str(error)[:500]}")
            elif onec_working_balance is not None:
                onec_lots_balance = onec_working_balance

            platform_vs_working = (
                None if onec_working_balance is None else platform_points - onec_working_balance
            )
            working_vs_lots = (
                None if onec_working_balance is None or onec_lots_balance is None else onec_working_balance - onec_lots_balance
            )
            status = "ok"
            if errors:
                status = "error"
            elif platform_vs_working not in (None, 0):
                status = "error"
            elif working_vs_lots not in (None, 0):
                status = "warning"
            item = {
                "member_id": str(member.id),
                "user_id": str(user.id),
                "partner_name": user.full_name or "Партнер GLAME",
                "partner_phone": user.phone,
                "discount_card_id_1c": user.discount_card_id_1c,
                "discount_card_number": user.discount_card_number,
                "customer_id_1c": user.customer_id_1c,
                "platform_points": platform_points,
                "onec_working_balance": onec_working_balance,
                "onec_lots_balance": onec_lots_balance,
                "platform_vs_working_delta": platform_vs_working,
                "working_vs_lots_delta": working_vs_lots,
                "status": status,
                "errors": errors,
            }
            if not only_issues or status != "ok":
                items.append(item)
    return {
        "generated_at": checked_at,
        "checked": len(rows),
        "count": len(items),
        "issues_count": sum(1 for item in items if item.get("status") != "ok"),
        "items": items,
    }


@router.post("/admin/partners/{member_id}/glm-loyalty-reconciliation/repair-lots")
async def admin_repair_glm_loyalty_lots(
    member_id: UUID,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    if os.getenv("GLM_LOYALTY_LOT_REPAIR_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "y", "on"}:
        raise HTTPException(
            status_code=409,
            detail=(
                "Lot repair is disabled: OData lots are diagnostic only. "
                "Use platform vs 1C К списанию as the spendable balance source."
            ),
        )
    member = (
        await db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == member_id))
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Партнер не найден")
    user = (
        await db.execute(select(User).where(User.id == member.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь партнера не найден")
    card_ref_key = str(getattr(user, "discount_card_id_1c", None) or "").strip()
    if not card_ref_key:
        raise HTTPException(status_code=400, detail="У партнера нет discount_card_id_1c")

    async with OneCCustomersService() as onec:
        working_payload = await onec.fetch_loyalty_balance(
            getattr(user, "customer_id_1c", None),
            card_ref_key,
        )
        lots_payload = await onec.fetch_loyalty_lots_balance(
            getattr(user, "customer_id_1c", None),
            card_ref_key,
        )
    platform_points = int(getattr(user, "loyalty_points", 0) or 0)
    working_points = int((working_payload or {}).get("balance") or 0)
    lots_points = int((lots_payload or {}).get("balance") or 0)
    if platform_points != working_points:
        raise HTTPException(
            status_code=400,
            detail=f"Нельзя выравнивать лоты: платформа={platform_points}, 1С к списанию={working_points}",
        )
    repair_points = lots_points - working_points
    if repair_points <= 0:
        return {
            "status": "skipped",
            "message": "Лоты не выше рабочего остатка, ремонт не нужен",
            "platform_points": platform_points,
            "onec_working_balance": working_points,
            "onec_lots_balance": lots_points,
            "repair_points": 0,
        }

    bonus_program_key = (
        os.getenv("ONEC_GLM_BRIDGE_SPEND_BONUS_PROGRAM_KEY")
        or os.getenv("ONEC_BONUS_PROGRAM_KEY")
        or os.getenv("ONEC_GLM_BRIDGE_BONUS_PROGRAM_KEY")
        or os.getenv("ONEC_WELCOME_BONUS_PROGRAM_KEY")
        or "ffa42f0e-ba53-11f0-836e-fa163e4cc04e"
    )
    comment = f"crypto_glame_lot_repair:{member.id}:{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}"
    async with OneCOutboundService() as onec_out:
        created = await onec_out.create_bonus_lot_repair_doc(
            bonus_program_key=bonus_program_key,
            card_ref_key=card_ref_key,
            points=repair_points,
            comment=comment,
        )
        doc_ref = str(created.get("Ref_Key") or "")
        if doc_ref:
            await onec_out.post_welcome_bonus_doc(doc_ref)

    async with OneCCustomersService() as onec:
        working_after = await onec.fetch_loyalty_balance(
            getattr(user, "customer_id_1c", None),
            card_ref_key,
        )
        lots_after = await onec.fetch_loyalty_lots_balance(
            getattr(user, "customer_id_1c", None),
            card_ref_key,
        )
    return {
        "status": "processed",
        "document_id": doc_ref or None,
        "document_number": created.get("Number"),
        "repair_points": repair_points,
        "platform_points": platform_points,
        "before": {
            "onec_working_balance": working_points,
            "onec_lots_balance": lots_points,
        },
        "after": {
            "onec_working_balance": int((working_after or {}).get("balance") or 0),
            "onec_lots_balance": int((lots_after or {}).get("balance") or 0),
        },
        "comment": comment,
        "admin_user_id": str(current_user.id),
    }


@router.get("/admin/glm-bridge/reconciliation.csv")
async def admin_glm_bridge_reconciliation_csv(
    stale_hours: int = Query(default=48, ge=1, le=720),
    limit: int = Query(default=500, ge=1, le=5000),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    report = await GlameTokenService(db).reconcile_bridge_operations(stale_hours=stale_hours, limit=limit)
    issues = report.get("issues") if isinstance(report, dict) else []
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["GLAME bridge reconciliation export"])
    writer.writerow(["generated_at", report.get("generated_at") if isinstance(report, dict) else None])
    writer.writerow(["stale_hours", report.get("stale_hours") if isinstance(report, dict) else stale_hours])
    writer.writerow(["bridge_operations_source", report.get("bridge_operations_source") if isinstance(report, dict) else ""])
    writer.writerow(["checked_bridge_operations", report.get("checked_bridge_operations") if isinstance(report, dict) else ""])
    writer.writerow(["bridge_operations_total", report.get("bridge_operations_total") if isinstance(report, dict) else ""])
    writer.writerow(["bridge_operations_missing_domain_count", report.get("bridge_operations_missing_domain_count") if isinstance(report, dict) else ""])
    writer.writerow(["bridge_operations_stale_pending_count", report.get("bridge_operations_stale_pending_count") if isinstance(report, dict) else ""])
    writer.writerow(["bridge_operations_consistency_issue_count", report.get("bridge_operations_consistency_issue_count") if isinstance(report, dict) else ""])
    writer.writerow(["checked_total_transactions", report.get("checked_total_transactions") if isinstance(report, dict) else ""])
    writer.writerow(["checked_bridge_transactions", report.get("checked_bridge_transactions") if isinstance(report, dict) else ""])
    writer.writerow(["checked_points_to_glm_transactions", report.get("checked_points_to_glm_transactions") if isinstance(report, dict) else ""])
    writer.writerow(["pending_count", report.get("pending_count") if isinstance(report, dict) else ""])
    writer.writerow(["pending_reserved_glm", report.get("pending_reserved_glm") if isinstance(report, dict) else ""])
    writer.writerow(["processed_count", report.get("processed_count") if isinstance(report, dict) else ""])
    writer.writerow(["processed_points", report.get("processed_points") if isinstance(report, dict) else ""])
    writer.writerow(["points_to_glm_pending_count", report.get("points_to_glm_pending_count") if isinstance(report, dict) else ""])
    writer.writerow(["points_to_glm_processed_count", report.get("points_to_glm_processed_count") if isinstance(report, dict) else ""])
    writer.writerow(["points_to_glm_canceled_count", report.get("points_to_glm_canceled_count") if isinstance(report, dict) else ""])
    writer.writerow(["ton_sent_waiting_count", report.get("ton_sent_waiting_count") if isinstance(report, dict) else ""])
    writer.writerow(["ton_processed_without_tx_count", report.get("ton_processed_without_tx_count") if isinstance(report, dict) else ""])
    writer.writerow(["onec_ready_count", report.get("onec_ready_count") if isinstance(report, dict) else ""])
    writer.writerow(["onec_failed_count", report.get("onec_failed_count") if isinstance(report, dict) else ""])
    writer.writerow(["onec_spend_ready_count", report.get("onec_spend_ready_count") if isinstance(report, dict) else ""])
    writer.writerow(["onec_spend_failed_count", report.get("onec_spend_failed_count") if isinstance(report, dict) else ""])
    writer.writerow(["onec_cancel_spend_failed_count", report.get("onec_cancel_spend_failed_count") if isinstance(report, dict) else ""])
    writer.writerow(["negative_accounts_count", report.get("negative_accounts_count") if isinstance(report, dict) else ""])
    writer.writerow(["issues_count", report.get("issues_count") if isinstance(report, dict) else ""])
    writer.writerow([])

    writer.writerow(["direction", "count", "amount_glm", "statuses"])
    by_direction = report.get("bridge_operations_by_direction") if isinstance(report, dict) else {}
    for direction, payload in sorted((by_direction or {}).items()):
        writer.writerow([
            direction,
            payload.get("count") if isinstance(payload, dict) else "",
            payload.get("amount_glm") if isinstance(payload, dict) else "",
            json.dumps(payload.get("statuses") or {}, ensure_ascii=False, sort_keys=True) if isinstance(payload, dict) else "",
        ])
    writer.writerow([])

    writer.writerow(["status", "count", "amount_glm"])
    by_status = report.get("bridge_operations_by_status") if isinstance(report, dict) else {}
    for status_key, payload in sorted((by_status or {}).items()):
        writer.writerow([
            status_key,
            payload.get("count") if isinstance(payload, dict) else "",
            payload.get("amount_glm") if isinstance(payload, dict) else "",
        ])
    writer.writerow([])
    writer.writerow(["issues"])
    fieldnames = [
        "severity",
        "code",
        "operation",
        "bridge_operation_id",
        "transaction_id",
        "account_id",
        "onec_document_id",
        "ton_tx_hash",
        "ton_status",
        "message",
        "checked_at",
    ]
    issue_writer = csv.DictWriter(output, fieldnames=fieldnames)
    issue_writer.writeheader()
    for issue in issues if isinstance(issues, list) else []:
        if not isinstance(issue, dict):
            continue
        issue_writer.writerow({
            "severity": issue.get("severity"),
            "code": issue.get("code"),
            "operation": issue.get("operation"),
            "bridge_operation_id": issue.get("bridge_operation_id"),
            "transaction_id": issue.get("transaction_id"),
            "account_id": issue.get("account_id"),
            "onec_document_id": issue.get("onec_document_id"),
            "ton_tx_hash": issue.get("ton_tx_hash"),
            "ton_status": issue.get("ton_status"),
            "message": issue.get("message"),
            "checked_at": report.get("generated_at") if isinstance(report, dict) else None,
        })
    filename = f"glm-bridge-reconciliation-{datetime.now(timezone.utc).date().isoformat()}.csv"
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/admin/glm-bridge/reconciliation/{transaction_id}/action")
async def admin_run_glm_bridge_reconciliation_action(
    transaction_id: UUID,
    payload: AdminGlmBridgeIssueActionRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(GlameTokenTransaction.id == transaction_id)
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="GLM transaction не найдена")

    try:
        if payload.action == "settle_ton_transfer":
            tx_hash = (payload.tx_hash or "").strip()
            if tx_hash:
                result = await TonGlmSettlementService(db).settle_claim_by_tx_hash(
                    claim_id=transaction_id,
                    tx_hash=tx_hash,
                    admin_user_id=current_user.id,
                    comment=payload.comment or "Reconciliation action: settle TON transfer.",
                    require_verified=True,
                )
            else:
                result = await TonGlmAutoTransferService(db).process_claim(claim=tx)
            await db.commit()
            claim = result.get("claim") if isinstance(result, dict) else None
            return {
                "status": result.get("status") if isinstance(result, dict) else "success",
                "result": result,
                "transaction": _glm_transaction_payload(claim) if isinstance(claim, GlameTokenTransaction) else None,
            }

        if payload.action == "cancel_onec_spend":
            tx = await GlameTokenService(db).repair_points_to_glm_cancel_spend_sync(
                transaction_id=transaction_id,
                admin_user_id=current_user.id,
                comment=payload.comment,
            )
            await db.commit()
            return {"status": "success", "transaction": _glm_transaction_payload(tx)}

        tx = await GlameTokenService(db).mark_points_to_glm_reconciliation_review(
            transaction_id=transaction_id,
            action=payload.action,
            admin_user_id=current_user.id,
            issue_code=payload.issue_code,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    return {"status": "success", "transaction": _glm_transaction_payload(tx)}


@router.get("/admin/glm-audit-hashes")
async def admin_glm_audit_hashes(
    limit: int = Query(default=30, ge=1, le=365),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    rows = await GlameTokenService(db).list_daily_audit_hashes(limit=limit)
    return {"hashes": [_glm_daily_audit_hash_payload(row) for row in rows]}


@router.get("/glm-audit-hashes/public")
async def public_glm_audit_hashes(
    limit: int = Query(default=90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(GlameTokenDailyAuditHash)
            .where(
                GlameTokenDailyAuditHash.token_code == "GLM",
                GlameTokenDailyAuditHash.public_status == "published",
            )
            .order_by(desc(GlameTokenDailyAuditHash.audit_date))
            .limit(limit)
        )
    ).scalars().all()
    return {
        "schema": "glame_token_public_audit_journal_v1",
        "token_code": "GLM",
        "journal_url": f"{GLM_AUDIT_JOURNAL_PUBLIC_PATH}/index.json",
        "jsonl_url": f"{GLM_AUDIT_JOURNAL_PUBLIC_PATH}/glame-audit-hashes.jsonl",
        "hashes": [_glm_public_audit_hash_payload(row) for row in rows],
    }


@router.post("/admin/glm-audit-hashes/generate")
async def admin_generate_glm_audit_hash(
    payload: AdminGlmAuditHashGenerateRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    row = await GlameTokenService(db).generate_daily_audit_hash(
        audit_date=payload.audit_date,
        admin_user_id=current_user.id,
    )
    await db.commit()
    return {"status": "success", "audit_hash": _glm_daily_audit_hash_payload(row)}


@router.post("/admin/glm-audit-hashes/publish")
async def admin_publish_glm_audit_hash(
    payload: AdminGlmAuditHashPublishRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    target_date = payload.audit_date or datetime.now(timezone.utc).date()
    row = await GlameTokenService(db).publish_daily_audit_hash(
        audit_date=target_date,
        admin_user_id=current_user.id,
        publisher="admin",
    )
    await db.commit()
    return {
        "status": "success",
        "audit_hash": _glm_daily_audit_hash_payload(row),
        "public": _glm_public_audit_hash_payload(row),
        "journal_url": f"{GLM_AUDIT_JOURNAL_PUBLIC_PATH}/index.json",
        "jsonl_url": f"{GLM_AUDIT_JOURNAL_PUBLIC_PATH}/glame-audit-hashes.jsonl",
    }


@router.post("/admin/glm-bridge/{bridge_id}/repair")
async def admin_repair_glm_bridge(
    bridge_id: UUID,
    payload: AdminGlmBridgeRepairRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == bridge_id,
                GlameTokenTransaction.transaction_type == "bridge",
                GlameTokenTransaction.reason.in_(("glm_to_points_bridge", "buy_loyalty_points")),
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="GLM bridge не найден")
    try:
        tx = await GlameTokenService(db).repair_glm_bridge_onec_sync(
            bridge=tx,
            action=payload.action,
            admin_user_id=current_user.id,
            onec_document_id=payload.onec_document_id,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    return {"status": "success", "bridge": _glm_transaction_payload(tx)}


@router.post("/admin/glm-bridge/points-to-glm/{transaction_id}/spend-repair")
async def admin_repair_points_to_glm_spend(
    transaction_id: UUID,
    payload: AdminPointsToGlmSpendRepairRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    tx = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == transaction_id,
                GlameTokenTransaction.transaction_type.in_(("claim", "conversion")),
                GlameTokenTransaction.reason.in_(("points_to_ton_bridge", "points_to_glm_bridge")),
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="Points -> GLM transaction не найдена")
    try:
        tx = await GlameTokenService(db).repair_points_to_glm_spend_sync(
            transaction=tx,
            action=payload.action,
            admin_user_id=current_user.id,
            onec_document_id=payload.onec_document_id,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    return {"status": "success", "transaction": _glm_transaction_payload(tx)}


@router.post("/admin/partners/{member_id}/payouts")
async def admin_create_referral_payout(
    member_id: UUID,
    payload: AdminPayoutCreateRequest,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    member = (await db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == member_id))).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Партнер не найден")
    payout = ReferralPayout(
        member_id=member.id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        amount_kopecks=payload.amount_kopecks,
        status=payload.status,
        onec_payment_document_id=payload.onec_payment_document_id,
        meta={"admin_comment": payload.comment} if payload.comment else {},
    )
    now = datetime.utcnow()
    if payload.status in {"approved", "paid"}:
        payout.approved_at = now
    if payload.status == "paid":
        payout.paid_at = now
    db.add(payout)
    await db.commit()
    await db.refresh(payout)
    return {"payout": (await _recent_payouts(db, member.id, limit=1))[0]}


@router.patch("/admin/payouts/{payout_id}")
async def admin_update_referral_payout(
    payout_id: UUID,
    payload: AdminPayoutStatusRequest,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    payout = (await db.execute(select(ReferralPayout).where(ReferralPayout.id == payout_id))).scalar_one_or_none()
    if payout is None:
        raise HTTPException(status_code=404, detail="Выплата не найдена")
    payout.status = payload.status
    if payload.onec_payment_document_id is not None:
        payout.onec_payment_document_id = payload.onec_payment_document_id.strip() or None
    if payload.comment is not None:
        payout.meta = {**(payout.meta or {}), "admin_comment": payload.comment}
    now = datetime.utcnow()
    if payload.status in {"approved", "paid"} and not payout.approved_at:
        payout.approved_at = now
    if payload.status == "paid":
        payout.paid_at = now
    await db.commit()
    await db.refresh(payout)
    return {"status": "success", "payout": (await _recent_payouts(db, payout.member_id, limit=1))[0]}


@router.patch("/admin/cash-requests/{request_id}")
async def admin_review_cash_upgrade(
    request_id: UUID,
    payload: AdminCashReviewRequest,
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    request = (await db.execute(select(ReferralCashUpgradeRequest).where(ReferralCashUpgradeRequest.id == request_id))).scalar_one_or_none()
    if request is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    member = (await db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == request.member_id))).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Партнер не найден")

    request.status = payload.status
    request.reviewer_user_id = current_user.id
    request.reviewed_at = datetime.utcnow()
    request.review_comment = payload.review_comment
    if payload.status == "approved":
        member.reward_mode = "cash"
        member.cash_status = "approved"
        member.legal_status = request.legal_status
        member.inn = request.inn
        member.passport_data = request.passport_data
        member.payout_details = request.payout_details
        member.tax_responsibility_confirmed_at = request.tax_responsibility_confirmed_at
        if payload.onec_agency_contract_id:
            member.onec_agency_contract_id = payload.onec_agency_contract_id.strip()
    else:
        member.cash_status = "rejected"
    await db.commit()
    return {"status": "success"}


@router.post("/me/join", response_model=ReferralDashboardResponse)
async def join_referral_program(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    try:
        member, code = await service.get_or_create_member(current_user)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return await _dashboard_payload(db, service, member, code, current_user)


@router.post("/register", response_model=ReferralRegisterResponse)
async def register_referral_partner(payload: ReferralRegisterRequest, db: AsyncSession = Depends(get_db)):
    phone_norm = normalize_phone(payload.phone)
    last_name = (payload.last_name or "").strip()
    first_name = (payload.first_name or "").strip()
    middle_name = (payload.middle_name or "").strip()
    full_name = (payload.full_name or "").strip() or " ".join(part for part in (last_name, first_name, middle_name) if part)
    if (not last_name or not first_name) and full_name:
        name_parts = full_name.split()
        last_name = last_name or (name_parts[0] if len(name_parts) > 0 else "")
        first_name = first_name or (name_parts[1] if len(name_parts) > 1 else "")
        middle_name = middle_name or (" ".join(name_parts[2:]) if len(name_parts) > 2 else "")
    email_norm = str(payload.email).strip().lower()
    if not re.fullmatch(r"7\d{10}", phone_norm or ""):
        raise HTTPException(status_code=400, detail="Некорректный телефон")
    if not last_name or not first_name:
        raise HTTPException(status_code=400, detail="Укажите фамилию и имя")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_norm):
        raise HTTPException(status_code=400, detail="Некорректный email")
    if not payload.offer_accepted:
        raise HTTPException(status_code=400, detail="Для регистрации нужно ознакомиться с офертой")

    offer_preferences = {
        "referral_offer_accepted_at": datetime.utcnow().isoformat(),
        "referral_offer_version": "v2",
        "referral_offer_file": "glame-referral-offer-v2.docx",
        "referral_last_name": last_name,
        "referral_first_name": first_name,
        "referral_middle_name": middle_name or None,
    }

    user = (await db.execute(select(User).where(User.phone == phone_norm))).scalar_one_or_none()
    if user is not None:
        if user.password_hash and not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=409, detail="Телефон уже зарегистрирован. Введите пароль от существующего аккаунта.")
        if email_norm and user.email and user.email.lower() != email_norm:
            raise HTTPException(status_code=409, detail="У этого телефона уже указан другой email")
        if email_norm and not user.email:
            email_existing = (await db.execute(select(User).where(User.email == email_norm, User.id != user.id))).scalar_one_or_none()
            if email_existing is not None:
                raise HTTPException(status_code=409, detail="Email уже зарегистрирован")
            user.email = email_norm
        if not user.password_hash:
            user.password_hash = hash_password(payload.password)
        if full_name and not user.full_name:
            user.full_name = full_name
        if not user.role:
            user.role = "customer"
        user.preferences = {**(user.preferences or {}), **offer_preferences}
        await db.commit()
        await db.refresh(user)
    else:
        if email_norm:
            email_existing = (await db.execute(select(User).where(User.email == email_norm))).scalar_one_or_none()
            if email_existing is not None:
                raise HTTPException(status_code=409, detail="Email уже зарегистрирован")

        user = User(
            phone=phone_norm,
            email=email_norm,
            password_hash=hash_password(payload.password),
            full_name=full_name,
            role="customer",
            is_customer=False,
            preferences=offer_preferences,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    service = ReferralService(db)
    member, code = await service.get_or_create_member(user)
    dashboard = await _dashboard_payload(db, service, member, code, user)
    return ReferralRegisterResponse(
        access_token=create_access_token({"sub": str(user.id)}),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
        dashboard=dashboard,
    )


@router.get("/me/dashboard", response_model=ReferralDashboardResponse)
async def get_my_referral_dashboard(
    period: str = Query("30d"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        member, code = await service.get_or_create_member(current_user)
    else:
        code = await service.get_active_code(member.id)
        if code is None:
            member, code = await service.get_or_create_member(current_user)
    return await _dashboard_payload(db, service, member, code, current_user)


@router.post("/me/sync-referrals", response_model=ManualReferralSyncResponse)
async def sync_my_referrals_from_onec(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None or member.status != "active":
        raise HTTPException(status_code=404, detail="Активная партнерская программа не найдена")
    code = await service.get_active_code(member.id)
    if code is None:
        raise HTTPException(status_code=404, detail="Активный реферальный код не найден")

    partner_repair_message = ""
    try:
        await service.ensure_partner_customer_in_1c(current_user, member, code)
        repair_job = (
            await db.execute(
                select(OneCUserSyncJob)
                .where(
                    OneCUserSyncJob.user_id == current_user.id,
                    OneCUserSyncJob.status == "pending",
                    OneCUserSyncJob.request_payload.op("->>")("source") == "referral_partner",
                )
                .order_by(desc(OneCUserSyncJob.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if repair_job:
            repair_job = await OneCUserSyncService(db).process_job(repair_job.id)
            if repair_job.status == "success":
                partner_repair_message = " Карточка партнера в 1С проверена и восстановлена."
            elif repair_job.last_error:
                partner_repair_message = f" Карточку партнера в 1С не удалось восстановить: {repair_job.last_error}"
    except Exception as error:
        logger.warning("Не удалось проверить карточку партнера в 1С перед ручной синхронизацией: %s", error)
        partner_repair_message = f" Карточку партнера в 1С не удалось проверить: {error}"

    sync_stats = await CustomerSyncService(db).sync_referrals_by_code(code.code)
    matched = int(sync_stats.get("matched", 0) or 0)
    created = int(sync_stats.get("created", 0) or 0)
    updated = int(sync_stats.get("updated", 0) or 0)
    errors = int(sync_stats.get("errors", 0) or 0)
    purchase_sync_created = 0
    purchase_sync_updated = 0
    purchase_sync_errors = 0
    referee_ids = (
        await db.execute(
            select(ReferralAttribution.referee_user_id)
            .where(
                ReferralAttribution.referrer_member_id == member.id,
                ReferralAttribution.referee_user_id.isnot(None),
                ReferralAttribution.status.in_(["pending", "active"]),
            )
            .distinct()
        )
    ).scalars().all()
    purchase_sync_service = CustomerSyncService(db)
    for referee_id in referee_ids:
        purchase_stats = await purchase_sync_service.sync_purchase_history(
            user_id=referee_id,
            days=days,
            prefer_discount_card=True,
        )
        purchase_sync_created += int(purchase_stats.get("created", 0) or 0)
        purchase_sync_updated += int(purchase_stats.get("updated", 0) or 0)
        purchase_sync_errors += int(purchase_stats.get("errors", 0) or 0)
    if matched:
        message = f"Найдено {matched} покупателей в 1С. Создано {created}, обновлено {updated}."
    else:
        message = "Новых покупателей по вашему коду в 1С пока не найдено."
    if referee_ids:
        message = f"{message} Покупки рефералов за {days} дней: создано {purchase_sync_created}, обновлено {purchase_sync_updated}."
    if partner_repair_message:
        message = f"{message}{partner_repair_message}"
    return ManualReferralSyncResponse(
        status="success" if errors == 0 and purchase_sync_errors == 0 else "partial",
        code=code.code,
        total_loaded=int(sync_stats.get("total_loaded", 0) or 0),
        matched=matched,
        created=created,
        updated=updated,
        errors=errors + purchase_sync_errors,
        message=message,
    )


@router.post("/validate-code", response_model=ValidateCodeResponse)
async def validate_referral_code(payload: ValidateCodeRequest, db: AsyncSession = Depends(get_db)):
    service = ReferralService(db)
    code = await service.validate_code(payload.code)
    if code is None:
        return ValidateCodeResponse(valid=False)
    member = (
        await db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == code.member_id))
    ).scalar_one_or_none()
    partner = None
    if member is not None:
        partner = (await db.execute(select(User).where(User.id == member.user_id))).scalar_one_or_none()
    return ValidateCodeResponse(
        valid=True,
        code=code.code,
        partner_name=(partner.full_name if partner else None),
        reward_hint="После первой покупки бонусы начисляются по правилам программы GLAME.",
    )


@router.post("/attributions", response_model=AttributionResponse)
async def create_referral_attribution(
    payload: CreateAttributionRequest,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    code = await service.validate_code(payload.code)
    if code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral code not found")

    referee_user_id = payload.referee_user_id or (current_user.id if current_user else None)
    if referee_user_id:
        member = (
            await db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == code.member_id))
        ).scalar_one_or_none()
        if member and member.user_id == referee_user_id:
            raise HTTPException(status_code=400, detail="Partner cannot use own referral code")

    try:
        attribution = await service.create_attribution(
            code=code,
            referee_user_id=referee_user_id,
            referee_phone_hash=payload.referee_phone_hash,
            source=payload.source,
            meta=payload.meta,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return AttributionResponse(
        id=str(attribution.id),
        status=attribution.status,
        source=attribution.source,
        created_at=attribution.created_at.isoformat() if attribution.created_at else None,
    )


@router.post("/me/cash-upgrade", response_model=CashUpgradeRequestResponse)
async def request_cash_upgrade(
    payload: CashUpgradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")
    member_id = member.id
    try:
        request = await service.request_cash_upgrade(
            member,
            legal_status=payload.legal_status,
            inn=payload.inn,
            passport_data=payload.passport_data,
            payout_details=payload.payout_details,
        )
    except ValueError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    return CashUpgradeRequestResponse(
        id=str(request.id),
        status=request.status,
        onec_sync_status=request.onec_sync_status,
    )


@router.post("/me/crypto-wallet/challenge", response_model=CryptoWalletChallengeResponse)
async def create_crypto_wallet_challenge(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")

    payload, expires_at = _challenge_payload_for_member(member)
    await db.commit()
    return CryptoWalletChallengeResponse(status="success", payload=payload, expires_at=expires_at)


@router.post("/me/telegram-notifications/link")
async def create_my_telegram_notifications_link(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")
    bot_username = (os.getenv("TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    if not bot_username:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_USERNAME не настроен")
    token = secrets.token_urlsafe(24)
    expires_at = datetime.utcnow() + timedelta(minutes=15)
    meta = dict(member.meta or {})
    meta["telegram_link"] = {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.utcnow().isoformat(),
        "source": "partner_profile",
    }
    member.meta = meta
    flag_modified(member, "meta")
    await db.commit()
    return {
        "status": "success",
        "bot_username": bot_username,
        "connect_url": f"https://t.me/{bot_username}?start={token}",
        "expires_at": expires_at.isoformat(),
    }


@router.post("/me/telegram-notifications")
async def bind_my_telegram_notifications(
    payload: PartnerTelegramBindRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(
        status_code=410,
        detail="Ручная привязка Telegram отключена. Используйте одноразовую ссылку из профиля партнера.",
    )
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")
    chat_id = payload.chat_id.strip()
    if not re.fullmatch(r"-?\d{3,32}", chat_id):
        raise HTTPException(status_code=400, detail="Укажите числовой Telegram chat id")
    meta = dict(member.meta or {})
    telegram_meta = meta.get("telegram") if isinstance(meta.get("telegram"), dict) else {}
    meta["telegram_chat_id"] = chat_id
    meta["telegram"] = {
        **telegram_meta,
        "chat_id": chat_id,
        "notifications_enabled": True,
        "subscriptions": {
            **(telegram_meta.get("subscriptions") if isinstance(telegram_meta.get("subscriptions"), dict) else {}),
            "partner_updates": True,
            "referrals": True,
            "crypto": True,
            "marketing": True,
        },
        "linked_at": datetime.utcnow().isoformat(),
        "source": "partner_profile",
    }
    member.meta = meta
    flag_modified(member, "meta")
    await db.commit()
    await db.refresh(member)
    test_result = await TelegramNotificationService().notify_partner(
        user=current_user,
        member=member,
        title="Telegram-уведомления GLAME подключены",
        lines=[
            "Теперь сюда могут приходить уведомления о рефералах, начислениях и CryptoGLAME-операциях.",
        ],
    )
    return {
        "status": "success",
        "telegram_chat_id": chat_id,
        "telegram_notifications_enabled": True,
        "test_notification": test_result,
        "profile": {
            "telegram_chat_id": chat_id,
            "telegram_notifications_enabled": True,
        },
    }


@router.post("/telegram/webhook")
async def telegram_referral_webhook(
    payload: TelegramWebhookUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    expected_secret = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    if expected_secret:
        actual_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if actual_secret != expected_secret:
            raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")
    message = payload.message if isinstance(payload.message, dict) else {}
    text = str(message.get("text") or "").strip()
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = str(chat.get("id") or "").strip()
    if text.startswith("/reply") and chat_id:
        return await _handle_support_reply(db, chat_id=chat_id, text_value=text, message=message)
    if not text.startswith("/start") or not chat_id:
        return {"status": "ignored"}
    parts = text.split(maxsplit=1)
    token = parts[1].strip() if len(parts) > 1 else ""
    if not token:
        try:
            async with TelegramService() as telegram:
                await telegram.send_message(
                    chat_id=chat_id,
                    text="Откройте партнерский сайт GLAME и подключите Telegram в разделе Профиль.",
                )
        except Exception as error:  # noqa: BLE001
            logger.warning("Failed to send Telegram start-without-token response: %s", error)
        return {"status": "missing_token"}
    member = (
        await db.execute(
            select(ReferralProgramMember).where(
                ReferralProgramMember.meta["telegram_link"]["token"].as_string() == token
            )
        )
    ).scalar_one_or_none()
    if member is None:
        try:
            async with TelegramService() as telegram:
                await telegram.send_message(
                    chat_id=chat_id,
                    text="Ссылка устарела или не найдена. Создайте новую ссылку в профиле партнера GLAME.",
                )
        except Exception as error:  # noqa: BLE001
            logger.warning("Failed to send Telegram invalid-token response: %s", error)
        return {"status": "invalid_token"}
    meta = dict(member.meta or {})
    link = meta.get("telegram_link") if isinstance(meta.get("telegram_link"), dict) else {}
    try:
        expires_at = datetime.fromisoformat(str(link.get("expires_at")))
    except ValueError:
        expires_at = datetime.utcnow() - timedelta(seconds=1)
    if expires_at < datetime.utcnow():
        try:
            async with TelegramService() as telegram:
                await telegram.send_message(
                    chat_id=chat_id,
                    text="Ссылка истекла. Вернитесь в профиль партнера GLAME и создайте новую ссылку.",
                )
        except Exception as error:  # noqa: BLE001
            logger.warning("Failed to send Telegram expired-token response: %s", error)
        return {"status": "expired_token"}
    user = (await db.execute(select(User).where(User.id == member.user_id))).scalar_one_or_none()
    telegram_meta = meta.get("telegram") if isinstance(meta.get("telegram"), dict) else {}
    meta["telegram_chat_id"] = chat_id
    meta["telegram"] = {
        **telegram_meta,
        "chat_id": chat_id,
        "notifications_enabled": True,
        "subscriptions": {
            **(telegram_meta.get("subscriptions") if isinstance(telegram_meta.get("subscriptions"), dict) else {}),
            "partner_updates": True,
            "referrals": True,
            "crypto": True,
            "marketing": True,
        },
        "linked_at": datetime.utcnow().isoformat(),
        "source": "telegram_webhook_start_token",
        "telegram_user": message.get("from") if isinstance(message.get("from"), dict) else None,
    }
    meta["telegram_link"] = None
    member.meta = meta
    flag_modified(member, "meta")
    await db.commit()
    await TelegramNotificationService().notify_partner(
        user=user,
        member=member,
        title="Telegram-уведомления GLAME подключены",
        lines=["Связь подтверждена через партнерский сайт."],
    )
    return {"status": "success", "member_id": str(member.id)}


@router.patch("/me/telegram-notifications/preferences")
async def update_my_telegram_notification_preferences(
    payload: PartnerTelegramPreferencesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")
    meta = dict(member.meta or {})
    telegram_meta = meta.get("telegram") if isinstance(meta.get("telegram"), dict) else {}
    subscriptions = telegram_meta.get("subscriptions") if isinstance(telegram_meta.get("subscriptions"), dict) else {}
    updated_subscriptions = {
        "partner_updates": bool(subscriptions.get("partner_updates", True)),
        "referrals": bool(subscriptions.get("referrals", True)),
        "crypto": bool(subscriptions.get("crypto", True)),
        "marketing": bool(subscriptions.get("marketing", True)),
    }
    for key in ("partner_updates", "referrals", "crypto", "marketing"):
        value = getattr(payload, key)
        if value is not None:
            updated_subscriptions[key] = bool(value)
    notifications_enabled = (
        bool(payload.notifications_enabled)
        if payload.notifications_enabled is not None
        else bool(telegram_meta.get("notifications_enabled", meta.get("telegram_chat_id")))
    )
    meta["telegram"] = {
        **telegram_meta,
        "chat_id": telegram_meta.get("chat_id") or meta.get("telegram_chat_id"),
        "notifications_enabled": notifications_enabled,
        "subscriptions": updated_subscriptions,
        "preferences_updated_at": datetime.utcnow().isoformat(),
    }
    member.meta = meta
    flag_modified(member, "meta")
    await db.commit()
    await db.refresh(member)
    preferences = _telegram_preferences_from_partner(member)
    return {
        "status": "success",
        "telegram": preferences,
        "profile": {
            "telegram_chat_id": preferences.get("chat_id"),
            "telegram_notifications_enabled": preferences.get("notifications_enabled"),
            "telegram_notification_subscriptions": preferences.get("subscriptions"),
        },
    }


@router.post("/me/crypto-wallet/ton-connect", response_model=CryptoWalletBindResponse)
async def verify_crypto_wallet_ton_connect(
    payload: CryptoWalletTonProofRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")

    address = _validate_raw_ton_wallet_address(payload.address)
    meta = member.meta or {}
    challenge = meta.get("crypto_wallet_challenge") if isinstance(meta, dict) else None
    if not isinstance(challenge, dict) or not challenge.get("payload"):
        raise HTTPException(status_code=400, detail="Сначала запросите TON Connect challenge")
    try:
        expires_at = datetime.fromisoformat(str(challenge.get("expires_at")))
    except ValueError as error:
        raise HTTPException(status_code=400, detail="TON Connect challenge поврежден") from error
    if expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="TON Connect challenge истек")

    verified_proof = _verify_ton_proof(
        address=address,
        public_key=payload.public_key,
        wallet_state_init=payload.wallet_state_init,
        proof=payload.proof,
        expected_payload=str(challenge.get("payload")),
    )
    now = datetime.utcnow().isoformat()
    previous_wallet = meta.get("crypto_wallet") if isinstance(meta.get("crypto_wallet"), dict) else {}
    inherit_claim_access = bool(previous_wallet.get("status") == "verified" and previous_wallet.get("glm_claim_enabled"))
    crypto_wallet = {
        "network": "ton",
        "address": address,
        "raw_address": address,
        "label": payload.wallet_app or "TON Wallet",
        "status": "verified",
        "linked_at": now,
        "verified_at": now,
        "verification": "ton_connect_ton_proof",
        "domain": verified_proof["domain"],
        "wallet_app": payload.wallet_app,
        "public_key": payload.public_key.lower(),
        "wallet_state_init": payload.wallet_state_init,
        "wallet_state_init_verified": True,
        "wallet_state_init_hash": verified_proof["wallet_state_init_hash"],
        "wallet_state_init_public_key": verified_proof["wallet_state_init_public_key"],
        "proof_timestamp": verified_proof["timestamp"],
        "next_step": "glm_claim",
    }
    if inherit_claim_access:
        crypto_wallet.update(
            {
                "glm_claim_enabled": True,
                "glm_claim_enabled_at": previous_wallet.get("glm_claim_enabled_at") or now,
                "glm_claim_updated_at": now,
                "glm_claim_updated_by": previous_wallet.get("glm_claim_updated_by") or "system_reconnect_inherit",
                "glm_claim_comment": previous_wallet.get("glm_claim_comment") or "Inherited after verified TON wallet reconnect",
            }
        )
    member.meta = {
        **(member.meta or {}),
        "crypto_wallet": crypto_wallet,
        "crypto_wallet_challenge": None,
        "crypto_wallet_last_proof": verified_proof,
        "crypto_wallet_previous": previous_wallet or None,
    }
    flag_modified(member, "meta")
    await db.commit()
    await db.refresh(member)
    try:
        await TelegramNotificationService().notify_admin_and_partner(
            user=current_user,
            member=member,
            admin_title="Партнер получил CryptoGLAME TON verified",
            partner_title="TON-кошелек CryptoGLAME подтвержден",
            lines=[
                f"Партнер: {current_user.full_name or current_user.phone or current_user.id}",
                f"Wallet app: {payload.wallet_app or 'TON Wallet'}",
                f"Address: {address[:12]}...{address[-8:]}",
            ],
            severity="success",
            partner_category="crypto",
        )
    except Exception as error:  # noqa: BLE001
        logger.warning("Failed to send Telegram TON verified notification: %s", error)
    return CryptoWalletBindResponse(status="success", crypto_wallet=crypto_wallet)


@router.post("/me/crypto-wallet", response_model=CryptoWalletBindResponse)
async def bind_crypto_wallet(
    payload: CryptoWalletBindRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")

    address = _validate_ton_wallet_address(payload.address)
    now = datetime.utcnow().isoformat()
    crypto_wallet = {
        "network": "ton",
        "address": address,
        "label": (payload.label or "TON Wallet").strip() or "TON Wallet",
        "status": "linked",
        "linked_at": now,
        "verification": "manual_address",
        "next_step": "ton_connect_signature",
    }
    member.meta = {
        **(member.meta or {}),
        "crypto_wallet": crypto_wallet,
    }
    flag_modified(member, "meta")
    await db.commit()
    await db.refresh(member)
    return CryptoWalletBindResponse(status="success", crypto_wallet=crypto_wallet)


@router.post("/me/glm-claim", response_model=GlmClaimResponse)
async def request_glm_claim(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")

    wallet = _crypto_wallet_meta(member)
    if not wallet or wallet.get("status") != "verified":
        raise HTTPException(status_code=400, detail="Сначала подтвердите TON-кошелек через TON Connect")
    if not wallet.get("glm_claim_enabled"):
        raise HTTPException(status_code=403, detail="GLM claim еще не разрешен администратором")

    token_service = GlameTokenService(db)
    try:
        tx = await token_service.request_ton_claim(member=member, wallet=wallet)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    token = await token_service.summary_for_member(member.id)
    return GlmClaimResponse(
        status="success",
        claim={
            "id": str(tx.id),
            "amount": int(tx.amount or 0),
            "status": tx.status,
            "wallet_address": wallet.get("address"),
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        },
        token={
            **token,
            "claim_enabled": bool(wallet.get("glm_claim_enabled")),
            "claim_allowed": bool(wallet.get("glm_claim_enabled")) and wallet.get("status") == "verified",
            "claim_wallet_address": wallet.get("address"),
        },
    )


@router.post("/me/glm-store/redeem")
async def redeem_glm_store_item(
    payload: GlmStoreRedeemRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")

    wallet = _crypto_wallet_meta(member) or {}
    if wallet.get("status") != "verified" or not wallet.get("address"):
        raise HTTPException(status_code=400, detail="Сначала подтвердите TON-кошелек через TON Connect")

    token_service = GlameTokenService(db)
    try:
        tx = await token_service.request_store_item_ton_checkout(
            member=member,
            sku=payload.sku,
            wallet=wallet,
            delivery_note=payload.delivery_note,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    token = await token_service.summary_for_member(member.id)
    return {
        "status": "success",
        "redemption": _glm_transaction_payload(tx),
        "token": {
            **token,
            "claim_enabled": bool(wallet.get("glm_claim_enabled")),
            "claim_allowed": bool(wallet.get("status") == "verified" and wallet.get("glm_claim_enabled")),
            "claim_wallet_address": wallet.get("address"),
        },
    }


@router.post("/me/glm-store/redemptions/{redemption_id}/ton-transaction")
async def prepare_glm_store_ton_transaction(
    redemption_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")
    wallet = _crypto_wallet_meta(member) or {}
    if wallet.get("status") != "verified" or not wallet.get("address"):
        raise HTTPException(status_code=400, detail="Сначала подтвердите TON-кошелек через TON Connect")

    redemption = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == redemption_id,
                GlameTokenTransaction.referral_member_id == member.id,
                GlameTokenTransaction.transaction_type == "redemption",
                GlameTokenTransaction.reason == "glm_store_item",
                GlameTokenTransaction.status == "pending_ton_payment",
            )
        )
    ).scalar_one_or_none()
    if redemption is None:
        raise HTTPException(status_code=404, detail="Pending GLM Store TON-заказ не найден")

    try:
        payload = await GlameTokenService(db).prepare_reward_store_ton_transaction(
            redemption=redemption,
            sender_wallet_address=wallet.get("address"),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    return {"status": "success", **payload}


@router.post("/me/glm-store/redemptions/{redemption_id}/cancel")
async def cancel_glm_store_ton_redemption(
    redemption_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")

    token_service = GlameTokenService(db)
    try:
        tx = await token_service.cancel_pending_store_ton_checkout(
            member=member,
            redemption_id=redemption_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    token = await token_service.summary_for_member(member.id)
    return {
        "status": "success",
        "redemption": _glm_transaction_payload(tx),
        "token": token,
    }


@router.post("/me/reward-store/redeem-points")
async def redeem_reward_store_item_with_points(
    payload: GlmStoreRedeemRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")

    token_service = GlameTokenService(db)
    try:
        tx = await token_service.redeem_store_item_with_points(
            member=member,
            sku=payload.sku,
            delivery_note=payload.delivery_note,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    await db.refresh(current_user)
    token = await token_service.summary_for_member(member.id)
    wallet = _crypto_wallet_meta(member) or {}
    return {
        "status": "success",
        "redemption": _glm_transaction_payload(tx),
        "profile": {
            "loyalty_points": int(current_user.loyalty_points or 0),
        },
        "token": {
            **token,
            "claim_enabled": bool(wallet.get("glm_claim_enabled")),
            "claim_allowed": bool(wallet.get("status") == "verified" and wallet.get("glm_claim_enabled")),
            "claim_wallet_address": wallet.get("address"),
        },
    }


async def _bridge_points_to_glm_response(
    payload: GlmBonusConvertRequest,
    current_user: User,
    db: AsyncSession,
) -> dict[str, Any]:
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")

    token_service = GlameTokenService(db)
    try:
        tx = await token_service.bridge_points_to_glm(member=member, points=payload.points)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    await db.refresh(current_user)
    token = await token_service.summary_for_member(member.id)
    wallet = _crypto_wallet_meta(member) or {}
    bridge_payload = _glm_transaction_payload(tx)
    return {
        "status": "success",
        "bridge": bridge_payload,
        "conversion": bridge_payload,
        "profile": {
            "loyalty_points": int(current_user.loyalty_points or 0),
        },
        "token": {
            **token,
            "claim_enabled": bool(wallet.get("glm_claim_enabled")),
            "claim_allowed": bool(wallet.get("status") == "verified" and wallet.get("glm_claim_enabled")),
            "claim_wallet_address": wallet.get("address"),
        },
    }


@router.post("/me/glm-bridge/points-to-glm")
async def bridge_points_to_glm(
    payload: GlmBonusConvertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _bridge_points_to_glm_response(payload, current_user, db)


@router.post("/me/glm-bridge/points-to-ton")
async def bridge_points_to_ton_withdrawal(
    payload: GlmBonusConvertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")

    wallet = _crypto_wallet_meta(member) or {}
    if wallet.get("status") != "verified":
        raise HTTPException(status_code=400, detail="Сначала подтвердите TON-кошелек через TON Connect")
    if not wallet.get("glm_claim_enabled"):
        raise HTTPException(status_code=403, detail="Вывод GLM в TON еще не разрешен администратором")

    token_service = GlameTokenService(db)
    try:
        withdrawal_tx = await token_service.request_points_to_ton_bridge(
            member=member,
            wallet=wallet,
            points=payload.points,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    auto_transfer_result: dict[str, Any] | None = None
    withdrawal_tx_id = withdrawal_tx.id
    try:
        auto_transfer_result = await TonGlmAutoTransferService(db).process_claim(claim=withdrawal_tx)
        await db.commit()
    except Exception as error:
        await db.rollback()
        auto_transfer_result = {"status": "failed", "error": str(error)}
    withdrawal_tx = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == withdrawal_tx_id,
                GlameTokenTransaction.referral_member_id == member.id,
            )
        )
    ).scalar_one_or_none()
    if withdrawal_tx is None:
        raise HTTPException(status_code=500, detail="GLM withdrawal transaction не найдена после создания")
    await db.refresh(current_user)
    token = await token_service.summary_for_member(member.id)
    return {
        "status": "success",
        "bridge": _glm_transaction_payload(withdrawal_tx),
        "withdrawal": _glm_transaction_payload(withdrawal_tx),
        "auto_transfer": auto_transfer_result,
        "profile": {
            "loyalty_points": int(current_user.loyalty_points or 0),
        },
        "token": {
            **token,
            "claim_enabled": bool(wallet.get("glm_claim_enabled")),
            "claim_allowed": bool(wallet.get("status") == "verified" and wallet.get("glm_claim_enabled")),
            "claim_wallet_address": wallet.get("address"),
        },
    }


@router.post("/me/glm-bridge/glm-to-points")
async def request_glm_to_points_bridge(
    payload: GlmToPointsBridgeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")

    token_service = GlameTokenService(db)
    wallet = _crypto_wallet_meta(member) or {}
    try:
        tx = await token_service.request_glm_to_points_bridge(
            member=member,
            amount=payload.amount,
            target_points=payload.target_points,
            note=payload.note,
            wallet=wallet,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    token = await token_service.summary_for_member(member.id)
    return {
        "status": "success",
        "bridge": _glm_transaction_payload(tx),
        "token": {
            **token,
            "claim_enabled": bool(wallet.get("glm_claim_enabled")),
            "claim_allowed": bool(wallet.get("status") == "verified" and wallet.get("glm_claim_enabled")),
            "claim_wallet_address": wallet.get("address"),
        },
    }


@router.post("/me/glm-bridge/glm-to-points/{bridge_id}/ton-transaction")
async def prepare_glm_to_points_ton_transaction(
    bridge_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")
    wallet = _crypto_wallet_meta(member) or {}
    if wallet.get("status") != "verified" or not wallet.get("address"):
        raise HTTPException(status_code=400, detail="Сначала подтвердите TON-кошелек через TON Connect")

    bridge = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == bridge_id,
                GlameTokenTransaction.referral_member_id == member.id,
                GlameTokenTransaction.transaction_type == "bridge",
                GlameTokenTransaction.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if bridge is None:
        raise HTTPException(status_code=404, detail="Pending GLM -> баллы bridge не найден")

    try:
        payload = await GlameTokenService(db).prepare_glm_to_points_ton_transaction(
            bridge=bridge,
            sender_wallet_address=wallet.get("address"),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"status": "success", **payload}


@router.post("/me/glm-bridge/glm-to-points/{bridge_id}/cancel")
async def cancel_my_glm_to_points_bridge(
    bridge_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")
    bridge = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == bridge_id,
                GlameTokenTransaction.referral_member_id == member.id,
                GlameTokenTransaction.transaction_type == "bridge",
                GlameTokenTransaction.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if bridge is None:
        raise HTTPException(status_code=404, detail="Pending GLM -> баллы bridge не найден")
    try:
        bridge = await GlameTokenService(db).update_glm_to_points_bridge_status(
            bridge=bridge,
            status="canceled",
            admin_user_id=current_user.id,
            comment="Canceled by partner before TON transfer confirmation.",
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    token = await GlameTokenService(db).summary_for_member(member.id)
    wallet = _crypto_wallet_meta(member) or {}
    return {
        "status": "success",
        "bridge": _glm_transaction_payload(bridge),
        "token": {
            **token,
            "claim_enabled": bool(wallet.get("glm_claim_enabled")),
            "claim_allowed": bool(wallet.get("status") == "verified" and wallet.get("glm_claim_enabled")),
            "claim_wallet_address": wallet.get("address"),
        },
    }


@router.post("/me/glm-bridge/buy-loyalty-points")
async def request_buy_loyalty_points(
    payload: BuyLoyaltyPointsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")

    token_service = GlameTokenService(db)
    wallet = _crypto_wallet_meta(member) or {}
    try:
        tx = await token_service.request_buy_loyalty_points(
            member=member,
            points=payload.points,
            note=payload.note,
            wallet=wallet,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    token = await token_service.summary_for_member(member.id)
    return {
        "status": "success",
        "bridge": _glm_transaction_payload(tx),
        "token": {
            **token,
            "claim_enabled": bool(wallet.get("glm_claim_enabled")),
            "claim_allowed": bool(wallet.get("status") == "verified" and wallet.get("glm_claim_enabled")),
            "claim_wallet_address": wallet.get("address"),
        },
    }


@router.post("/me/glm-primary-sale/buy")
async def request_buy_glm_with_ton(
    payload: BuyGlmWithTonRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")
    wallet = _crypto_wallet_meta(member) or {}
    if wallet.get("status") != "verified" or not wallet.get("address"):
        raise HTTPException(status_code=400, detail="Сначала подтвердите TON-кошелек через TON Connect")
    if not wallet.get("glm_claim_enabled"):
        raise HTTPException(status_code=403, detail="Покупка GLM в TON еще не разрешена для вашего кошелька")

    token_service = GlameTokenService(db)
    try:
        tx = await token_service.request_buy_glm_with_ton(
            member=member,
            amount_glm=payload.amount_glm,
            wallet=wallet,
            note=payload.note,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    token = await token_service.summary_for_member(member.id)
    return {
        "status": "success",
        "sale": _glm_transaction_payload(tx),
        "token": {
            **token,
            "claim_enabled": bool(wallet.get("glm_claim_enabled")),
            "claim_allowed": bool(wallet.get("status") == "verified" and wallet.get("glm_claim_enabled")),
            "claim_wallet_address": wallet.get("address"),
        },
    }


@router.post("/me/glm-primary-sale/{sale_id}/ton-transaction")
async def prepare_buy_glm_with_ton_transaction(
    sale_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")
    wallet = _crypto_wallet_meta(member) or {}
    if wallet.get("status") != "verified" or not wallet.get("address"):
        raise HTTPException(status_code=400, detail="Сначала подтвердите TON-кошелек через TON Connect")
    sale = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == sale_id,
                GlameTokenTransaction.referral_member_id == member.id,
                GlameTokenTransaction.transaction_type == "claim",
                GlameTokenTransaction.reason == "buy_glm_with_ton",
                GlameTokenTransaction.status == "pending_payment",
            )
        )
    ).scalar_one_or_none()
    if sale is None:
        raise HTTPException(status_code=404, detail="Pending покупка GLM за TON не найдена")
    try:
        payload = await GlameTokenService(db).prepare_buy_glm_with_ton_transaction(
            sale=sale,
            sender_wallet_address=wallet.get("address"),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    return {"status": "success", **payload}


@router.post("/me/glm-exchange-desk/sell-for-ton")
async def request_sell_glm_for_ton(
    payload: SellGlmForTonRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")
    wallet = _crypto_wallet_meta(member) or {}
    if wallet.get("status") != "verified" or not wallet.get("address"):
        raise HTTPException(status_code=400, detail="Сначала подтвердите TON-кошелек через TON Connect")
    if not wallet.get("glm_claim_enabled"):
        raise HTTPException(status_code=403, detail="Обмен GLM в GRAM еще не разрешен для вашего кошелька")

    token_service = GlameTokenService(db)
    try:
        tx = await token_service.request_sell_glm_for_ton(
            member=member,
            amount_glm=payload.amount_glm,
            wallet=wallet,
            note=payload.note,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    token = await token_service.summary_for_member(member.id)
    return {
        "status": "success",
        "exchange": _glm_transaction_payload(tx),
        "token": {
            **token,
            "claim_enabled": bool(wallet.get("glm_claim_enabled")),
            "claim_allowed": bool(wallet.get("status") == "verified" and wallet.get("glm_claim_enabled")),
            "claim_wallet_address": wallet.get("address"),
        },
    }


@router.post("/me/glm-exchange-desk/sell-for-ton/{exchange_id}/ton-transaction")
async def prepare_sell_glm_for_ton_transaction(
    exchange_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")
    wallet = _crypto_wallet_meta(member) or {}
    if wallet.get("status") != "verified" or not wallet.get("address"):
        raise HTTPException(status_code=400, detail="Сначала подтвердите TON-кошелек через TON Connect")
    exchange = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == exchange_id,
                GlameTokenTransaction.referral_member_id == member.id,
                GlameTokenTransaction.transaction_type == "bridge",
                GlameTokenTransaction.reason == "sell_glm_for_ton",
                GlameTokenTransaction.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if exchange is None:
        raise HTTPException(status_code=404, detail="Pending заявка GLM -> GRAM не найдена")
    try:
        payload = await GlameTokenService(db).prepare_glm_to_points_ton_transaction(
            bridge=exchange,
            sender_wallet_address=wallet.get("address"),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await db.commit()
    return {"status": "success", **payload}


@router.post("/me/glm-exchange-desk/sell-for-ton/{exchange_id}/cancel")
async def cancel_sell_glm_for_ton(
    exchange_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReferralService(db)
    member = await service.get_member_by_user_id(current_user.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Partner profile not found")
    exchange = (
        await db.execute(
            select(GlameTokenTransaction).where(
                GlameTokenTransaction.id == exchange_id,
                GlameTokenTransaction.referral_member_id == member.id,
                GlameTokenTransaction.transaction_type == "bridge",
                GlameTokenTransaction.reason == "sell_glm_for_ton",
                GlameTokenTransaction.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if exchange is None:
        raise HTTPException(status_code=404, detail="Pending заявка GLM -> GRAM не найдена")
    meta = exchange.meta if isinstance(exchange.meta, dict) else {}
    exchange.status = "canceled"
    exchange.meta = {
        **meta,
        "admin_comment": "Canceled by partner before GLM deposit confirmation.",
        "canceled_at": datetime.now(timezone.utc).isoformat(),
    }
    flag_modified(exchange, "meta")
    await db.flush()
    await GlameTokenService(db).sync_bridge_operation(exchange)
    await db.commit()
    token = await GlameTokenService(db).summary_for_member(member.id)
    wallet = _crypto_wallet_meta(member) or {}
    return {
        "status": "success",
        "exchange": _glm_transaction_payload(exchange),
        "token": {
            **token,
            "claim_enabled": bool(wallet.get("glm_claim_enabled")),
            "claim_allowed": bool(wallet.get("status") == "verified" and wallet.get("glm_claim_enabled")),
            "claim_wallet_address": wallet.get("address"),
        },
    }


@router.post("/me/glm-convert-bonuses")
async def convert_bonus_points_to_glm(
    payload: GlmBonusConvertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _bridge_points_to_glm_response(payload, current_user, db)


async def _dashboard_payload(
    db: AsyncSession,
    service: ReferralService,
    member: ReferralProgramMember,
    code: ReferralCode,
    user: User,
) -> ReferralDashboardResponse:
    eligibility = await service.sync_cash_eligibility(member)
    summary = await service.dashboard_summary(member)
    token = await GlameTokenService(db).summary_for_member(member.id)
    wallet = _crypto_wallet_meta(member)
    token = {
        **token,
        "claim_enabled": bool(wallet and wallet.get("glm_claim_enabled")),
        "claim_allowed": bool(wallet and wallet.get("status") == "verified" and wallet.get("glm_claim_enabled")),
        "claim_wallet_address": wallet.get("address") if wallet else None,
    }
    telegram_preferences = _telegram_preferences_from_partner(member)
    return ReferralDashboardResponse(
        member=_member_response(member),
        referral_code=_code_response(code),
        profile={
            "full_name": user.full_name,
            "phone": user.phone,
            "email": user.email,
            "loyalty_points": int(user.loyalty_points or 0),
            "customer_id_1c": user.customer_id_1c,
            "discount_card_id_1c": user.discount_card_id_1c,
            "discount_card_number": user.discount_card_number,
            "telegram_chat_id": telegram_preferences.get("chat_id"),
            "telegram_notifications_enabled": telegram_preferences.get("notifications_enabled"),
            "telegram_notification_subscriptions": telegram_preferences.get("subscriptions"),
        },
        summary=summary,
        token=token,
        rate_promotion=_public_rate_promotion_payload(),
        cash_upgrade=CashUpgradeStatus(
            eligible=eligibility.eligible,
            active_referrals=eligibility.active_referrals,
            referral_revenue=eligibility.referral_revenue,
            annual_referral_turnover=eligibility.annual_referral_turnover,
            current_level=_level_payload(eligibility.level),
            levels=[_level_payload(level) for level in service.referral_levels()],
            thresholds=service.cash_upgrade_thresholds(),
            reason=eligibility.reason,
        ),
        referrals=await _recent_referrals(db, member.id),
        commissions=await _recent_commissions(db, member.id),
        payouts=await _recent_payouts(db, member.id),
        glm_transactions=await _recent_glm_transactions(db, member),
    )
