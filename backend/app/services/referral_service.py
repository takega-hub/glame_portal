from __future__ import annotations

import random
import string
import os
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.referral import (
    ReferralAttribution,
    ReferralCashUpgradeRequest,
    ReferralCode,
    ReferralCommission,
    ReferralProgramMember,
    ReferralPayout,
)
from app.models.purchase_history import PurchaseHistory
from app.models.onec_user_sync_job import OneCUserSyncJob
from app.models.user import User
from app.services.onec_user_registration_payload import OneCUserRegistrationPayload
from app.services.onec_user_sync_service import OneCUserSyncService
from app.services.telegram_notification_service import TelegramNotificationService


logger = logging.getLogger(__name__)


REFERRAL_LEVELS = [
    {
        "code": "stylish_start",
        "name": "Stylish Start",
        "title": "Стильный старт",
        "min_annual_turnover": 0,
        "rate_percent": Decimal("3.00"),
    },
    {
        "code": "stylish_pro",
        "name": "Stylish Pro",
        "title": "Стильный профи",
        "min_annual_turnover": 5_000_001,
        "rate_percent": Decimal("5.00"),
    },
    {
        "code": "stylish_expert",
        "name": "Stylish Expert",
        "title": "Стильный эксперт",
        "min_annual_turnover": 15_000_001,
        "rate_percent": Decimal("7.00"),
    },
    {
        "code": "stylish_prive",
        "name": "Stylish Privé",
        "title": "Стильный привилегированный",
        "min_annual_turnover": 30_000_001,
        "rate_percent": Decimal("10.00"),
    },
]

CASH_UNLOCK_LEVEL_CODE = "stylish_pro"
CASH_REVENUE_THRESHOLD = 5_000_001
DEFAULT_REFERRAL_RATE_PERCENT = Decimal("3.00")
REFERRED_CLIENT_WELCOME_BONUS_POINTS = 1000
REFERRED_CLIENT_MIN_PURCHASE_KOPECKS = 700_000
REFERRED_CLIENT_BONUS_VALID_DAYS = 7
REFERRED_CLIENT_MAX_BONUS_PAYMENT_SHARE = Decimal("0.30")
REWARD_HOLD_DAYS = 15
REFERRAL_RATE_PROMOTIONS_FILE = Path(__file__).resolve().parents[2] / "static" / "referral_rate_promotions.json"
REFERRAL_PARTNER_CUSTOMER_GROUP_KEY = os.getenv(
    "ONEC_REFERRAL_PARTNER_CUSTOMER_GROUP_KEY",
    "fcd4ff72-72f6-11f1-876b-fa163e4cc04e",
)
REFERRAL_PARTNER_LOYALTY_PROGRAM_KEY = (
    os.getenv("ONEC_REFERRAL_PARTNER_LOYALTY_PROGRAM_KEY")
    or os.getenv("ONEC_LOYALTY_PROGRAM_KEY")
    or os.getenv("ONEC_BONUS_PROGRAM_KEY")
)


@dataclass(frozen=True)
class PartnerEligibility:
    eligible: bool
    active_referrals: int
    referral_revenue: int
    annual_referral_turnover: int
    level: dict[str, Any]
    reason: str


class ReferralService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_member_by_user_id(self, user_id: UUID) -> ReferralProgramMember | None:
        result = await self.db.execute(
            select(ReferralProgramMember).where(ReferralProgramMember.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_member(self, user: User) -> tuple[ReferralProgramMember, ReferralCode]:
        member = await self.get_member_by_user_id(user.id)
        created_member = member is None
        if member is None:
            member = ReferralProgramMember(
                user_id=user.id,
                status="active",
                reward_mode="points",
                program_level="stylish_start",
                points_rate_percent=DEFAULT_REFERRAL_RATE_PERCENT,
                cash_rate_percent=DEFAULT_REFERRAL_RATE_PERCENT,
                cash_status="unavailable",
                approved_at=datetime.now(timezone.utc),
            )
            self.db.add(member)
            await self.db.flush()

        code = await self.get_active_code(member.id)
        if code is None:
            code = ReferralCode(member_id=member.id, code=await self.generate_unique_code(user), status="active")
            self.db.add(code)

        await self.db.commit()
        await self.db.refresh(member)
        await self.db.refresh(code)
        await self.ensure_partner_customer_in_1c(user, member, code)
        await self.db.refresh(member)
        if created_member:
            await self._notify_partner_created(user=user, member=member, code=code)
        return member, code

    async def _notify_partner_created(self, *, user: User, member: ReferralProgramMember, code: ReferralCode) -> None:
        try:
            await TelegramNotificationService().notify_admin(
                title="Новый партнер GLAME",
                lines=[
                    f"Партнер: {user.full_name or 'без имени'}",
                    f"Телефон: {user.phone or 'не указан'}",
                    f"Код: {code.code}",
                    f"Member ID: {member.id}",
                ],
                severity="success",
            )
        except Exception as error:  # noqa: BLE001
            logger.warning("Failed to send Telegram partner-created notification: %s", error)

    async def ensure_partner_customer_in_1c(
        self,
        user: User,
        member: ReferralProgramMember,
        code: ReferralCode | None = None,
    ) -> None:
        if getattr(user, "customer_id_1c", None) and member.onec_counterparty_id != user.customer_id_1c:
            member.onec_counterparty_id = user.customer_id_1c
            await self.db.commit()

        full_name = (getattr(user, "full_name", None) or "").strip()
        phone = (getattr(user, "phone", None) or "").strip()
        if not full_name or not phone:
            raise ValueError("Для регистрации партнера в 1С нужны ФИО и телефон")

        existing_job = (
            await self.db.execute(
                select(OneCUserSyncJob).where(
                    OneCUserSyncJob.user_id == user.id,
                    OneCUserSyncJob.status.in_(["pending", "in_progress"]),
                    OneCUserSyncJob.request_payload.op("->>")("source") == "referral_partner",
                )
            )
        ).scalar_one_or_none()
        if existing_job:
            if member.onec_sync_status != existing_job.status:
                member.onec_sync_status = existing_job.status
                await self.db.commit()
            return

        payload = OneCUserRegistrationPayload(
            phone=phone,
            full_name=full_name,
            email=getattr(user, "email", None),
            inn=None,
            birth_date=getattr(user, "birth_date", None),
            loyalty_program_key=REFERRAL_PARTNER_LOYALTY_PROGRAM_KEY,
            source="referral_partner",
            customer_group_key=REFERRAL_PARTNER_CUSTOMER_GROUP_KEY,
            skip_welcome_bonus=True,
            referral_code=(code.code if code else None),
            referral_url=None,
        )
        job = await OneCUserSyncService(self.db).enqueue_registration(user, payload)
        if job:
            member.onec_sync_status = job.status
            member.onec_last_error = None
            await self.db.commit()

    async def get_active_code(self, member_id: UUID) -> ReferralCode | None:
        result = await self.db.execute(
            select(ReferralCode)
            .where(
                ReferralCode.member_id == member_id,
                ReferralCode.status == "active",
            )
            .order_by(ReferralCode.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def generate_unique_code(self, user: User) -> str:
        base = "GLAME"
        if user.phone:
            suffix = "".join(ch for ch in user.phone if ch.isdigit())[-4:]
            base = f"GL{suffix}"
        elif user.full_name:
            letters = [ch for ch in user.full_name.upper() if "A" <= ch <= "Z" or "А" <= ch <= "Я"]
            if letters:
                base = "GL" + "".join(letters[:4])

        alphabet = string.ascii_uppercase + string.digits
        for _ in range(50):
            code = f"{base}{''.join(random.choice(alphabet) for _ in range(4))}"[:16]
            result = await self.db.execute(select(ReferralCode.id).where(func.lower(ReferralCode.code) == code.lower()))
            if result.scalar_one_or_none() is None:
                return code
        raise RuntimeError("Could not generate unique referral code")

    async def validate_code(self, code: str) -> ReferralCode | None:
        normalized = (code or "").strip()
        if not normalized:
            return None
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(ReferralCode)
            .join(ReferralProgramMember, ReferralProgramMember.id == ReferralCode.member_id)
            .where(
                func.lower(ReferralCode.code) == normalized.lower(),
                ReferralCode.status == "active",
                ReferralProgramMember.status == "active",
                (ReferralCode.expires_at.is_(None)) | (ReferralCode.expires_at > now),
            )
        )
        return result.scalar_one_or_none()

    async def calculate_cash_eligibility(self, member_id: UUID) -> PartnerEligibility:
        active_referrals = int(
            (
                await self.db.execute(
                    select(func.count(ReferralAttribution.id)).where(
                        ReferralAttribution.referrer_member_id == member_id,
                        ReferralAttribution.status == "active",
                    )
                )
            ).scalar_one()
            or 0
        )
        referral_revenue = int(
            (
                await self.db.execute(
                    select(func.coalesce(func.sum(ReferralCommission.commission_base), 0)).where(
                        ReferralCommission.referrer_member_id == member_id,
                        ReferralCommission.status.in_(["hold", "approved", "accrued_in_1c", "paid"]),
                    )
                )
            ).scalar_one()
            or 0
        )
        since = datetime.now(timezone.utc) - timedelta(days=365)
        annual_referral_turnover = int(
            (
                await self.db.execute(
                    select(func.coalesce(func.sum(ReferralCommission.commission_base), 0)).where(
                        ReferralCommission.referrer_member_id == member_id,
                        ReferralCommission.status.in_(["hold", "approved", "accrued_in_1c", "paid"]),
                        ReferralCommission.created_at >= since,
                    )
                )
            ).scalar_one()
            or 0
        )

        level = self.level_for_turnover(annual_referral_turnover)
        eligible = annual_referral_turnover >= CASH_REVENUE_THRESHOLD
        reason = f"{level['code']} annual referral turnover" if eligible else "stylish_pro_threshold_not_reached"
        return PartnerEligibility(eligible, active_referrals, referral_revenue, annual_referral_turnover, level, reason)

    async def sync_cash_eligibility(self, member: ReferralProgramMember) -> PartnerEligibility:
        eligibility = await self.calculate_cash_eligibility(member.id)
        level = eligibility.level
        needs_update = (
            member.program_level != level["code"]
            or Decimal(str(member.points_rate_percent or 0)) != level["rate_percent"]
            or Decimal(str(member.cash_rate_percent or 0)) != level["rate_percent"]
        )
        member.program_level = level["code"]
        member.points_rate_percent = level["rate_percent"]
        member.cash_rate_percent = level["rate_percent"]
        if eligibility.eligible and not member.cash_eligible:
            member.cash_eligible = True
            member.cash_eligible_at = datetime.now(timezone.utc)
            member.cash_eligibility_reason = eligibility.reason
            member.cash_status = "eligible"
            await self.db.commit()
            await self.db.refresh(member)
        elif needs_update:
            await self.db.commit()
            await self.db.refresh(member)
        return eligibility

    def effective_reward_rate(self, member: ReferralProgramMember) -> tuple[Decimal, dict[str, Any] | None]:
        reward_mode = member.reward_mode or "points"
        if reward_mode == "points":
            promotion = self.active_points_rate_promotion()
            if promotion:
                return Decimal(str(promotion["rate_percent"])), promotion
            return Decimal(str(member.points_rate_percent or 0)), None
        return Decimal(str(member.cash_rate_percent or 0)), None

    async def ensure_commission_for_purchase(
        self,
        *,
        referee_user_id: UUID,
        purchase: PurchaseHistory,
        source: str = "onec_purchase_sync",
    ) -> ReferralCommission | None:
        attribution = (
            await self.db.execute(
                select(ReferralAttribution)
                .where(
                    ReferralAttribution.referee_user_id == referee_user_id,
                    ReferralAttribution.status.in_(["pending", "active"]),
                )
                .order_by(ReferralAttribution.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if attribution is None:
            return None

        purchase_date = purchase.purchase_date
        if purchase_date and attribution.created_at:
            normalized_purchase_date = purchase_date if purchase_date.tzinfo else purchase_date.replace(tzinfo=timezone.utc)
            normalized_attribution_date = attribution.created_at if attribution.created_at.tzinfo else attribution.created_at.replace(tzinfo=timezone.utc)
            if normalized_purchase_date < normalized_attribution_date:
                return None

        member = (
            await self.db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == attribution.referrer_member_id))
        ).scalar_one_or_none()
        if member is None or member.status != "active":
            return None

        existing_commission = (
            await self.db.execute(
                select(ReferralCommission).where(
                    ReferralCommission.purchase_id == purchase.id,
                    ReferralCommission.referrer_member_id == member.id,
                )
            )
        ).scalar_one_or_none()
        if existing_commission is not None:
            return existing_commission

        reward_mode = member.reward_mode or "points"
        rate, rate_promotion = self.effective_reward_rate(member)
        commission_base = max(0, int(purchase.total_amount or 0))
        amount_kopecks = int(commission_base * rate / Decimal("100"))
        points = amount_kopecks // 100 if reward_mode == "points" else 0
        commission_meta = {
            "source": source,
            "document_id_1c": purchase.document_id_1c,
            "product_id_1c": purchase.product_id_1c,
        }
        if rate_promotion:
            commission_meta["rate_promotion"] = {
                "id": rate_promotion.get("id"),
                "title": rate_promotion.get("title"),
                "rate_percent": rate_promotion.get("rate_percent"),
                "starts_at": rate_promotion.get("starts_at"),
                "ends_at": rate_promotion.get("ends_at"),
            }
        commission = ReferralCommission(
            attribution_id=attribution.id,
            referrer_member_id=member.id,
            referee_user_id=referee_user_id,
            purchase_id=purchase.id,
            reward_mode=reward_mode,
            commission_base=commission_base,
            rate_percent=rate,
            amount_kopecks=amount_kopecks,
            points=points,
            status="hold",
            hold_until=self.default_hold_until(),
            meta=commission_meta,
        )
        self.db.add(commission)
        await self.db.flush()

        if attribution.status == "pending":
            now = datetime.now(timezone.utc)
            attribution.status = "active"
            attribution.first_purchase_id = purchase.id
            attribution.first_purchase_at = purchase.purchase_date or now
            attribution.activated_at = now

        from app.services.glame_token_service import GlameTokenService

        await GlameTokenService(self.db).issue_referral_commission_hold(
            commission=commission,
            member=member,
        )
        return commission

    async def create_attribution(
        self,
        *,
        code: ReferralCode,
        referee_user_id: UUID | None = None,
        referee_phone_hash: str | None = None,
        source: str = "web",
        meta: dict[str, Any] | None = None,
    ) -> ReferralAttribution:
        if referee_user_id:
            existing = await self.db.execute(
                select(ReferralAttribution).where(
                    ReferralAttribution.referee_user_id == referee_user_id,
                    ReferralAttribution.status.in_(["pending", "active"]),
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise ValueError("Referee already has active referral attribution")

        attribution = ReferralAttribution(
            referrer_member_id=code.member_id,
            referral_code_id=code.id,
            referee_user_id=referee_user_id,
            referee_phone_hash=referee_phone_hash,
            source=source,
            status="pending",
            meta=meta or {},
        )
        code.usage_count = int(code.usage_count or 0) + 1
        self.db.add(attribution)
        await self.db.commit()
        await self.db.refresh(attribution)
        await self._notify_referral_attribution_created(attribution=attribution, code=code)
        return attribution

    async def _notify_referral_attribution_created(self, *, attribution: ReferralAttribution, code: ReferralCode) -> None:
        try:
            member = (
                await self.db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == attribution.referrer_member_id))
            ).scalar_one_or_none()
            partner = (
                await self.db.execute(select(User).where(User.id == member.user_id))
            ).scalar_one_or_none() if member else None
            lines = [
                f"Код: {code.code}",
                f"Источник: {attribution.source}",
                f"Статус: {attribution.status}",
                f"Attribution ID: {attribution.id}",
            ]
            await TelegramNotificationService().notify_admin_and_partner(
                user=partner,
                member=member,
                admin_title="Новый реферал GLAME",
                partner_title="У вас новый реферал GLAME",
                lines=lines,
                severity="info",
            )
        except Exception as error:  # noqa: BLE001
            logger.warning("Failed to send Telegram referral-attribution notification: %s", error)

    async def request_cash_upgrade(
        self,
        member: ReferralProgramMember,
        *,
        legal_status: str,
        inn: str,
        passport_data: dict[str, Any] | None,
        payout_details: dict[str, Any] | None,
    ) -> ReferralCashUpgradeRequest:
        eligibility = await self.sync_cash_eligibility(member)
        if not eligibility.eligible:
            raise ValueError("Cash reward mode is not available yet")
        request = ReferralCashUpgradeRequest(
            member_id=member.id,
            status="pending",
            legal_status=legal_status,
            inn=inn,
            passport_data=passport_data or {},
            payout_details=payout_details or {},
            tax_responsibility_confirmed_at=datetime.now(timezone.utc),
            onec_sync_status="pending",
        )
        member.cash_status = "pending"
        member.legal_status = legal_status
        member.inn = inn
        member.passport_data = passport_data or {}
        member.payout_details = payout_details or {}
        member.tax_responsibility_confirmed_at = request.tax_responsibility_confirmed_at
        self.db.add(request)
        await self.db.commit()
        await self.db.refresh(request)
        await self.db.refresh(member)
        return request

    async def dashboard_summary(self, member: ReferralProgramMember) -> dict[str, int]:
        attributions_total = (
            await self.db.execute(
                select(func.count(ReferralAttribution.id)).where(ReferralAttribution.referrer_member_id == member.id)
            )
        ).scalar_one() or 0
        active_referrals = (
            await self.db.execute(
                select(func.count(ReferralAttribution.id)).where(
                    ReferralAttribution.referrer_member_id == member.id,
                    ReferralAttribution.status == "active",
                )
            )
        ).scalar_one() or 0
        purchases = (
            await self.db.execute(
                select(func.count(ReferralCommission.id)).where(
                    ReferralCommission.referrer_member_id == member.id,
                    ReferralCommission.status != "canceled",
                )
            )
        ).scalar_one() or 0
        sums = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(ReferralCommission.commission_base), 0),
                    func.coalesce(func.sum(ReferralCommission.amount_kopecks).filter(ReferralCommission.status == "hold"), 0),
                    func.coalesce(func.sum(ReferralCommission.amount_kopecks).filter(ReferralCommission.status.in_(["approved", "accrued_in_1c"])), 0),
                    func.coalesce(func.sum(ReferralCommission.amount_kopecks).filter(ReferralCommission.status == "accrued_in_1c"), 0),
                    func.coalesce(func.sum(ReferralCommission.amount_kopecks).filter(ReferralCommission.status == "paid"), 0),
                    func.coalesce(func.sum(ReferralCommission.points).filter(ReferralCommission.status.in_(["approved", "paid"])), 0),
                    func.coalesce(func.sum(ReferralCommission.points).filter(ReferralCommission.status == "hold"), 0),
                ).where(ReferralCommission.referrer_member_id == member.id)
            )
        ).one()
        payouts_paid = (
            await self.db.execute(
                select(func.coalesce(func.sum(ReferralPayout.amount_kopecks), 0)).where(
                    ReferralPayout.member_id == member.id,
                    ReferralPayout.status == "paid",
                )
            )
        ).scalar_one() or 0
        referral_revenue = int(sums[0] or 0)
        return {
            "registrations": int(attributions_total),
            "active_referrals": int(active_referrals),
            "purchases": int(purchases),
            "referral_revenue": referral_revenue,
            "pending_commission": int(sums[1] or 0),
            "approved_commission": int(sums[2] or 0),
            "accrued_in_1c": int(sums[3] or 0),
            "paid_commission": int(sums[4] or 0) + int(payouts_paid),
            "posted_points": int(sums[5] or 0),
            "pending_points": int(sums[6] or 0),
            "average_check": int(referral_revenue / purchases) if purchases else 0,
        }

    @staticmethod
    def cash_upgrade_thresholds() -> dict[str, Any]:
        return {
            "cash_unlock_level": CASH_UNLOCK_LEVEL_CODE,
            "annual_referral_turnover": CASH_REVENUE_THRESHOLD,
            "welcome_bonus_points": REFERRED_CLIENT_WELCOME_BONUS_POINTS,
            "welcome_bonus_valid_days": REFERRED_CLIENT_BONUS_VALID_DAYS,
        }

    @staticmethod
    def default_hold_until(days: int = REWARD_HOLD_DAYS) -> datetime:
        return datetime.now(timezone.utc) + timedelta(days=days)

    @staticmethod
    def level_for_turnover(annual_referral_turnover: int) -> dict[str, Any]:
        turnover = max(0, int(annual_referral_turnover or 0))
        current = REFERRAL_LEVELS[0]
        for level in REFERRAL_LEVELS:
            if turnover >= int(level["min_annual_turnover"]):
                current = level
        return dict(current)

    @staticmethod
    def referral_levels() -> list[dict[str, Any]]:
        return [dict(level) for level in REFERRAL_LEVELS]

    @staticmethod
    def _rate_promotions_dir() -> Path:
        REFERRAL_RATE_PROMOTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        return REFERRAL_RATE_PROMOTIONS_FILE.parent

    @staticmethod
    def _parse_promotion_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            date_value = value
        else:
            raw = str(value).strip()
            if not raw:
                return None
            if raw.endswith("Z"):
                raw = f"{raw[:-1]}+00:00"
            try:
                date_value = datetime.fromisoformat(raw)
            except ValueError:
                return None
        if date_value.tzinfo is None:
            date_value = date_value.replace(tzinfo=timezone.utc)
        return date_value.astimezone(timezone.utc)

    @staticmethod
    def _serialize_promotion_datetime(value: Any) -> str | None:
        date_value = ReferralService._parse_promotion_datetime(value)
        return date_value.isoformat() if date_value else None

    @staticmethod
    def _normalize_rate_promotion(item: dict[str, Any]) -> dict[str, Any] | None:
        promotion_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "Акция по баллам").strip() or "Акция по баллам"
        try:
            rate_percent = Decimal(str(item.get("rate_percent")))
        except Exception:
            return None
        starts_at = ReferralService._serialize_promotion_datetime(item.get("starts_at"))
        ends_at = ReferralService._serialize_promotion_datetime(item.get("ends_at"))
        if not promotion_id or starts_at is None or ends_at is None:
            return None
        return {
            "id": promotion_id,
            "title": title,
            "rate_percent": float(rate_percent),
            "starts_at": starts_at,
            "ends_at": ends_at,
            "is_active": bool(item.get("is_active", True)),
            "created_at": ReferralService._serialize_promotion_datetime(item.get("created_at")) or datetime.now(timezone.utc).isoformat(),
            "updated_at": ReferralService._serialize_promotion_datetime(item.get("updated_at")) or datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _rate_promotion_sort_key(item: dict[str, Any]) -> tuple[str, str]:
        return (str(item.get("starts_at") or ""), str(item.get("title") or ""))

    @classmethod
    def list_rate_promotions(cls) -> list[dict[str, Any]]:
        cls._rate_promotions_dir()
        if not REFERRAL_RATE_PROMOTIONS_FILE.exists():
            return []
        try:
            data = json.loads(REFERRAL_RATE_PROMOTIONS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        promotions = [normalized for item in data if isinstance(item, dict) for normalized in [cls._normalize_rate_promotion(item)] if normalized]
        return sorted(promotions, key=cls._rate_promotion_sort_key, reverse=True)

    @classmethod
    def write_rate_promotions(cls, promotions: list[dict[str, Any]]) -> None:
        cls._rate_promotions_dir()
        normalized = [
            item
            for promotion in promotions
            for item in [cls._normalize_rate_promotion(promotion)]
            if item is not None
        ]
        normalized = sorted(normalized, key=cls._rate_promotion_sort_key, reverse=True)
        REFERRAL_RATE_PROMOTIONS_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def create_rate_promotion(
        cls,
        *,
        title: str,
        rate_percent: Decimal,
        starts_at: datetime,
        ends_at: datetime,
        is_active: bool = True,
    ) -> dict[str, Any]:
        if rate_percent < Decimal("0") or rate_percent > Decimal("100"):
            raise ValueError("Процент акции должен быть от 0 до 100")
        start = cls._parse_promotion_datetime(starts_at)
        end = cls._parse_promotion_datetime(ends_at)
        if start is None or end is None or end <= start:
            raise ValueError("Дата окончания акции должна быть позже даты начала")
        now = datetime.now(timezone.utc).isoformat()
        promotion = {
            "id": str(uuid4()),
            "title": title.strip() or "Акция по баллам",
            "rate_percent": float(rate_percent),
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "is_active": bool(is_active),
            "created_at": now,
            "updated_at": now,
        }
        promotions = cls.list_rate_promotions()
        promotions.append(promotion)
        cls.write_rate_promotions(promotions)
        return promotion

    @classmethod
    def update_rate_promotion(cls, promotion_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        promotions = cls.list_rate_promotions()
        updated: dict[str, Any] | None = None
        for item in promotions:
            if item.get("id") != promotion_id:
                continue
            next_item = dict(item)
            if "title" in patch and patch["title"] is not None:
                next_item["title"] = str(patch["title"]).strip() or next_item["title"]
            if "rate_percent" in patch and patch["rate_percent"] is not None:
                rate_percent = Decimal(str(patch["rate_percent"]))
                if rate_percent < Decimal("0") or rate_percent > Decimal("100"):
                    raise ValueError("Процент акции должен быть от 0 до 100")
                next_item["rate_percent"] = float(rate_percent)
            if "starts_at" in patch and patch["starts_at"] is not None:
                start = cls._parse_promotion_datetime(patch["starts_at"])
                if start is None:
                    raise ValueError("Некорректная дата начала")
                next_item["starts_at"] = start.isoformat()
            if "ends_at" in patch and patch["ends_at"] is not None:
                end = cls._parse_promotion_datetime(patch["ends_at"])
                if end is None:
                    raise ValueError("Некорректная дата окончания")
                next_item["ends_at"] = end.isoformat()
            if "is_active" in patch and patch["is_active"] is not None:
                next_item["is_active"] = bool(patch["is_active"])
            start = cls._parse_promotion_datetime(next_item.get("starts_at"))
            end = cls._parse_promotion_datetime(next_item.get("ends_at"))
            if start is None or end is None or end <= start:
                raise ValueError("Дата окончания акции должна быть позже даты начала")
            next_item["updated_at"] = datetime.now(timezone.utc).isoformat()
            item.update(next_item)
            updated = item
            break
        if updated is None:
            return None
        cls.write_rate_promotions(promotions)
        return updated

    @classmethod
    def delete_rate_promotion(cls, promotion_id: str) -> bool:
        promotions = cls.list_rate_promotions()
        next_promotions = [item for item in promotions if item.get("id") != promotion_id]
        if len(next_promotions) == len(promotions):
            return False
        cls.write_rate_promotions(next_promotions)
        return True

    @classmethod
    def active_points_rate_promotion(cls, now: datetime | None = None) -> dict[str, Any] | None:
        current = cls._parse_promotion_datetime(now or datetime.now(timezone.utc)) or datetime.now(timezone.utc)
        active: list[dict[str, Any]] = []
        for item in cls.list_rate_promotions():
            start = cls._parse_promotion_datetime(item.get("starts_at"))
            end = cls._parse_promotion_datetime(item.get("ends_at"))
            if item.get("is_active", True) and start is not None and end is not None and start <= current < end:
                active.append(item)
        if not active:
            return None
        return sorted(active, key=lambda item: (str(item.get("starts_at") or ""), float(item.get("rate_percent") or 0)), reverse=True)[0]
