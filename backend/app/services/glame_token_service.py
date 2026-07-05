from __future__ import annotations

import hashlib
import json
import os
import base64
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from typing import Any
from uuid import UUID, uuid4

import httpx
from tonsdk.boc import Cell
from tonsdk.utils import Address
from sqlalchemy import String, and_, cast, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.glame_token import GlameTokenAccount, GlameTokenBridgeOperation, GlameTokenDailyAuditHash, GlameTokenTransaction
from app.models.reward_store import RewardStoreItem
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.referral import ReferralCommission, ReferralProgramMember
from app.models.user import User
from app.services.onec_customers_service import OneCCustomersService
from app.services.onec_outbound_service import OneCOutboundService
from app.services.telegram_notification_service import TelegramNotificationService


logger = logging.getLogger(__name__)


GLAME_TOKEN_CODE = "GLM"
GLAME_TOKEN_NAME = "GLAME Coin"
GLAME_TOKEN_DECIMALS = 0
GLAME_TOKEN_MAX_SUPPLY = 10_000_000
GLAME_TOKEN_MONTHLY_REFERRAL_EMISSION_LIMIT = 250_000
GLAME_BONUS_CONVERSION_MIN = 100
GLAME_BONUS_CONVERSION_MAX = 10_000
GLAME_BONUS_CONVERSION_MONTHLY_LIMIT = 50_000
GLAME_LOYALTY_POINTS_PURCHASE_SPREAD_PERCENT = 10
GLAME_LOYALTY_POINTS_PURCHASE_MIN = 100
GLAME_LOYALTY_POINTS_PURCHASE_MAX = 10_000
GLAME_LOYALTY_POINTS_FROM_GLM_EXPIRES_DAYS = 365
GLAME_STORE_CHECKOUT_MODE = os.getenv("GLM_STORE_CHECKOUT_MODE", "ton_deposit_required").strip() or "ton_deposit_required"
GLAME_GLM_TO_POINTS_BRIDGE_REASONS = {"glm_to_points_bridge", "buy_loyalty_points"}
JETTON_TRANSFER_OP = 0x0F8A7EA5
JETTON_TRANSFER_NOTIFICATION_OP = 0x7362D09C


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


GLAME_PRIVILEGE_TIERS = [
    {
        "code": "glm_start",
        "name": "GLM Start",
        "threshold": 0,
        "benefits": ["Базовый CryptoGLAME кабинет", "История GLM начислений"],
    },
    {
        "code": "glm_muse",
        "name": "GLM Muse",
        "threshold": 5_000,
        "benefits": ["Ранний доступ к дропам", "Приоритетные партнерские материалы"],
    },
    {
        "code": "glm_prive",
        "name": "GLM Privé",
        "threshold": 20_000,
        "benefits": ["Закрытые подборки", "Приглашения на приватные события"],
    },
    {
        "code": "glm_ambassador",
        "name": "GLM Ambassador",
        "threshold": 50_000,
        "benefits": ["Амбассадорский статус", "Персональные условия партнерских кампаний"],
    },
]
GLAME_USE_CASES = [
    {
        "code": "early_drops",
        "title": "Ранний доступ к дропам",
        "description": "GLM-статус открывает предварительный доступ к новым коллекциям и закрытым предложениям.",
        "status": "pilot_ready",
        "min_tier": "glm_muse",
    },
    {
        "code": "private_styling",
        "title": "Закрытые подборки стилиста",
        "description": "GLM можно использовать как критерий доступа к персональным подборкам и private sale.",
        "status": "pilot_ready",
        "min_tier": "glm_prive",
    },
    {
        "code": "online_partner_checkout",
        "title": "Онлайн-покупки на сайте партнера",
        "description": "GLM применяется в онлайн-сценариях партнёрского сайта, закрытых дропах и сервисах. Для физического магазина GLM сначала переводится в баллы 1С.",
        "status": "policy_draft",
        "min_tier": "glm_start",
    },
    {
        "code": "ambassador_campaigns",
        "title": "Амбассадорские кампании",
        "description": "Высокий GLM-статус дает доступ к персональным партнерским условиям и спецкампаниям.",
        "status": "policy_draft",
        "min_tier": "glm_ambassador",
    },
]
GLAME_ACCEPTANCE_RULES = [
    {"category": "Новые коллекции", "limit_percent": 10, "note": "осторожный лимит для защиты маржи"},
    {"category": "Основной ассортимент", "limit_percent": 20, "note": "базовый лимит внутренней ценности"},
    {"category": "VIP/Privé сценарии", "limit_percent": 30, "note": "для высокого статуса и спецкампаний"},
    {"category": "Старые остатки / clearance", "limit_percent": 50, "note": "повышенный лимит для ускорения оборота"},
    {"category": "Сервисные привилегии", "limit_percent": 100, "note": "если себестоимость сервиса низкая"},
]
GLAME_STORE_ITEMS = [
    {
        "sku": "glm-jewelry-holder-01",
        "title": "GLAME holder для украшений",
        "description": "Брендированный настольный холдер для колец, браслетов и цепочек.",
        "price_glm": 1_500,
        "price_points": 1_500,
        "category": "branded_goods",
        "status": "available",
        "inventory_status": "pilot_batch",
    },
    {
        "sku": "glm-silk-pouch-01",
        "title": "GLAME travel pouch",
        "description": "Мягкий дорожный pouch для украшений с фирменной маркировкой.",
        "price_glm": 900,
        "price_points": 900,
        "category": "branded_goods",
        "status": "available",
        "inventory_status": "pilot_batch",
    },
    {
        "sku": "glm-bracelet-pass-01",
        "title": "GLAME special bracelet",
        "description": "Лимитированный браслет-символ участника CryptoGLAME.",
        "price_glm": 3_500,
        "price_points": 3_500,
        "category": "limited_goods",
        "status": "available",
        "inventory_status": "limited",
    },
    {
        "sku": "glm-stylist-session-01",
        "title": "Private stylist session",
        "description": "Персональная онлайн-сессия со стилистом GLAME и подборкой украшений под образ.",
        "price_glm": 2_500,
        "price_points": 2_500,
        "category": "service",
        "status": "available",
        "inventory_status": "booking",
    },
    {
        "sku": "glm-private-selection-01",
        "title": "Закрытая подборка GLAME",
        "description": "Индивидуальная закрытая подборка украшений до публикации в общих каналах.",
        "price_glm": 1_200,
        "price_points": 1_200,
        "category": "service",
        "status": "available",
        "inventory_status": "digital",
    },
    {
        "sku": "glm-private-sale-pass-01",
        "title": "Private sale pass",
        "description": "Доступ к private sale / закрытому дропу для участников CryptoGLAME.",
        "price_glm": 800,
        "price_points": 800,
        "category": "access_pass",
        "status": "available",
        "inventory_status": "limited",
    },
]


class GlameTokenService:
    """Off-chain GLM ledger for GLAME referral utility rewards."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _audit_json_safe(value: Any) -> Any:
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): GlameTokenService._audit_json_safe(value[key]) for key in sorted(value)}
        if isinstance(value, (list, tuple)):
            return [GlameTokenService._audit_json_safe(item) for item in value]
        return value

    @staticmethod
    def _audit_sha256(payload: dict[str, Any]) -> str:
        canonical = json.dumps(
            GlameTokenService._audit_json_safe(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def _locked_account(self, account_id: UUID) -> GlameTokenAccount:
        account = (
            await self.db.execute(
                select(GlameTokenAccount)
                .where(GlameTokenAccount.id == account_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if account is None:
            raise ValueError("GLM account не найден")
        return account

    async def get_or_create_account(
        self,
        *,
        user_id: UUID,
        referral_member_id: UUID | None = None,
    ) -> GlameTokenAccount:
        stmt = select(GlameTokenAccount).where(
            GlameTokenAccount.token_code == GLAME_TOKEN_CODE,
            GlameTokenAccount.user_id == user_id,
        )
        if referral_member_id:
            stmt = stmt.where(GlameTokenAccount.referral_member_id == referral_member_id)
        result = await self.db.execute(stmt.limit(1))
        account = result.scalar_one_or_none()
        if account is not None:
            return account

        account = GlameTokenAccount(
            user_id=user_id,
            referral_member_id=referral_member_id,
            token_code=GLAME_TOKEN_CODE,
            status="active",
            meta={"policy": "referral_utility_token_v1"},
        )
        self.db.add(account)
        await self.db.flush()
        return account

    async def issue_referral_commission_hold(
        self,
        *,
        commission: ReferralCommission,
        member: ReferralProgramMember,
    ) -> GlameTokenTransaction | None:
        source_id = f"referral_commission:{commission.id}:glm_hold"
        existing = (
            await self.db.execute(select(GlameTokenTransaction).where(GlameTokenTransaction.source_id == source_id))
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        base_amount = self.calculate_referral_glm_amount(commission)
        campaign = self.referral_campaign_payload()
        multiplier = Decimal(str(campaign["multiplier"])) if campaign.get("active") else Decimal("1")
        amount = int(Decimal(base_amount) * multiplier)
        if amount <= 0:
            return None

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_issued = (
            await self.db.execute(
                select(func.coalesce(func.sum(GlameTokenTransaction.amount), 0)).where(
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "earn",
                    GlameTokenTransaction.status != "canceled",
                    GlameTokenTransaction.created_at >= month_start,
                )
            )
        ).scalar_one() or 0
        monthly_remaining = max(0, GLAME_TOKEN_MONTHLY_REFERRAL_EMISSION_LIMIT - int(monthly_issued or 0))
        requested_amount = amount
        amount = min(amount, monthly_remaining)
        if amount <= 0:
            return None

        account = await self.get_or_create_account(user_id=member.user_id, referral_member_id=member.id)
        account.hold_balance = int(account.hold_balance or 0) + amount
        account.lifetime_earned = int(account.lifetime_earned or 0) + amount

        tx = GlameTokenTransaction(
            account_id=account.id,
            user_id=member.user_id,
            referral_member_id=member.id,
            referral_commission_id=commission.id,
            token_code=GLAME_TOKEN_CODE,
            transaction_type="earn",
            status="hold",
            amount=amount,
            balance_after=int(account.balance or 0),
            hold_balance_after=int(account.hold_balance or 0),
            reason="referral_commission",
            description="GLM за реферальную покупку. Доступен после подтверждения комиссии.",
            source="referral",
            source_id=source_id,
            available_at=commission.hold_until,
            meta={
                "commission_base": int(commission.commission_base or 0),
                "commission_amount_kopecks": int(commission.amount_kopecks or 0),
                "rate_percent": float(commission.rate_percent or 0),
                "reward_mode": commission.reward_mode,
                "policy": "1 GLM per 1 RUB referral reward, hold until commission approval",
                "base_glm_amount": base_amount,
                "campaign": campaign,
                "requested_glm_amount": requested_amount,
                "monthly_referral_emission_limit": GLAME_TOKEN_MONTHLY_REFERRAL_EMISSION_LIMIT,
                "monthly_referral_emission_used_before": int(monthly_issued or 0),
                "monthly_referral_emission_remaining_before": monthly_remaining,
                "emission_capped": amount < requested_amount,
            },
        )
        self.db.add(tx)
        await self.db.flush()
        await self._notify_referral_glm_hold(tx=tx, commission=commission, member=member)
        return tx

    async def _notify_referral_glm_hold(
        self,
        *,
        tx: GlameTokenTransaction,
        commission: ReferralCommission,
        member: ReferralProgramMember,
    ) -> None:
        try:
            user = (
                await self.db.execute(select(User).where(User.id == member.user_id))
            ).scalar_one_or_none()
            amount_rub = int(commission.amount_kopecks or 0) // 100
            lines = [
                f"GLM: {int(tx.amount or 0)} в холде",
                f"Вознаграждение: {amount_rub} ₽",
                f"База покупки: {int(commission.commission_base or 0) // 100} ₽",
                f"Доступно после: {commission.hold_until.isoformat() if commission.hold_until else 'проверки'}",
            ]
            await TelegramNotificationService().notify_admin_and_partner(
                user=user,
                member=member,
                admin_title="GLM начислен партнеру в hold",
                partner_title="GLM начислен за реферальную покупку",
                lines=lines,
                severity="success",
            )
        except Exception as error:  # noqa: BLE001
            logger.warning("Failed to send Telegram GLM hold notification: %s", error)

    @staticmethod
    def _format_units(raw_value: int | str, decimals: int) -> str:
        value = int(raw_value or 0)
        if decimals <= 0:
            return str(value)
        multiplier = 10 ** decimals
        whole = value // multiplier
        fraction = value % multiplier
        if fraction == 0:
            return str(whole)
        return f"{whole}.{str(fraction).zfill(decimals).rstrip('0')}"

    @staticmethod
    def _parse_glm_units(value: Any) -> int:
        try:
            return int(Decimal(str(value or "0")).to_integral_value())
        except Exception:
            return 0

    @staticmethod
    def _ton_tx_hash(tx: dict[str, Any]) -> str | None:
        value = tx.get("hash")
        if isinstance(value, str) and value.strip():
            return value.strip()
        tx_id = tx.get("transaction_id") if isinstance(tx.get("transaction_id"), dict) else {}
        value = tx_id.get("hash")
        return value.strip() if isinstance(value, str) and value.strip() else None

    @classmethod
    def _decode_jetton_transfer_notification(cls, body_boc_base64: str | None, decimals: int) -> dict[str, Any] | None:
        if not body_boc_base64:
            return None
        try:
            cell = Cell.one_from_boc(base64.b64decode(body_boc_base64))
            s = cell.begin_parse()
            op = s.read_uint(32)
            if op != JETTON_TRANSFER_NOTIFICATION_OP:
                return None
            query_id = s.read_uint(64)
            amount_raw = s.read_coins()
            sender = s.read_msg_addr()
            return {
                "direction": "incoming",
                "query_id": str(query_id),
                "amount_raw": str(amount_raw),
                "amount": cls._parse_glm_units(cls._format_units(amount_raw, decimals)),
                "counterparty": sender.to_string(False) if sender else None,
            }
        except Exception:
            return None

    @classmethod
    def _decode_jetton_transfer(cls, body_boc_base64: str | None, decimals: int) -> dict[str, Any] | None:
        if not body_boc_base64:
            return None
        try:
            cell = Cell.one_from_boc(base64.b64decode(body_boc_base64))
            s = cell.begin_parse()
            op = s.read_uint(32)
            if op != JETTON_TRANSFER_OP:
                return None
            query_id = s.read_uint(64)
            amount_raw = s.read_coins()
            destination = s.read_msg_addr()
            return {
                "direction": "outgoing",
                "query_id": str(query_id),
                "amount_raw": str(amount_raw),
                "amount": cls._parse_glm_units(cls._format_units(amount_raw, decimals)),
                "counterparty": destination.to_string(False) if destination else None,
            }
        except Exception:
            return None

    async def ton_wallet_glm_balance(self, wallet_address: str | None) -> dict[str, Any]:
        decimals = int(os.getenv("TON_GLM_DECIMALS", "9") or 9)
        jetton_master = (os.getenv("TON_GLM_JETTON_MASTER_ADDRESS") or "").strip()
        ton_network = (os.getenv("TON_NETWORK", "testnet") or "testnet").strip()
        checked_at = datetime.now(timezone.utc).isoformat()
        if not wallet_address:
            return {
                "status": "no_wallet",
                "balance_raw": "0",
                "balance_glm": "0",
                "decimals": decimals,
                "checked_at": checked_at,
            }
        if not jetton_master:
            return {
                "status": "not_configured",
                "wallet_address": wallet_address,
                "balance_raw": "0",
                "balance_glm": "0",
                "decimals": decimals,
                "checked_at": checked_at,
            }

        base_url = (
            os.getenv("TONCENTER_V3_ENDPOINT")
            or ("https://testnet.toncenter.com/api/v3" if ton_network == "testnet" else "https://toncenter.com/api/v3")
        ).rstrip("/")
        params = {
            "owner_address": wallet_address,
            "jetton_address": jetton_master,
            "limit": "1",
        }
        headers = {}
        api_key = (os.getenv("TON_API_KEY") or "").strip()
        if api_key:
            headers["X-API-Key"] = api_key

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{base_url}/jetton/wallets", params=params, headers=headers)
                response.raise_for_status()
            payload = response.json()
            rows = payload.get("jetton_wallets") or []
            row = rows[0] if rows else {}
            raw_balance = str(row.get("balance") or "0")
            address_book = payload.get("address_book") if isinstance(payload, dict) else {}
            wallet_book = address_book.get(str(row.get("address") or "").upper()) if isinstance(address_book, dict) else None
            return {
                "status": "ok",
                "source": "toncenter_v3",
                "network": ton_network,
                "wallet_address": wallet_address,
                "jetton_master_address": jetton_master,
                "jetton_wallet_address": (wallet_book or {}).get("user_friendly") if isinstance(wallet_book, dict) else row.get("address"),
                "balance_raw": raw_balance,
                "balance_glm": self._format_units(raw_balance, decimals),
                "decimals": decimals,
                "checked_at": checked_at,
            }
        except Exception as error:
            return {
                "status": "error",
                "source": "toncenter_v3",
                "network": ton_network,
                "wallet_address": wallet_address,
                "jetton_master_address": jetton_master,
                "balance_raw": "0",
                "balance_glm": "0",
                "decimals": decimals,
                "checked_at": checked_at,
                "error": str(error) or repr(error),
            }

    async def ton_wallet_glm_transactions(self, wallet_address: str | None, *, limit: int = 20) -> list[dict[str, Any]]:
        balance = await self.ton_wallet_glm_balance(wallet_address)
        addresses = [
            item
            for item in [
                (wallet_address or "").strip(),
                str(balance.get("jetton_wallet_address") or "").strip(),
            ]
            if item
        ]
        if not addresses:
            return []

        network = (os.getenv("TON_NETWORK", "testnet") or "testnet").strip()
        base_url = (
            os.getenv("TONCENTER_API_BASE_URL")
            or ("https://testnet.toncenter.com/api/v2" if network == "testnet" else "https://toncenter.com/api/v2")
        ).rstrip("/")
        decimals = int(os.getenv("TON_GLM_DECIMALS", "9") or 9)
        headers = {}
        api_key = (os.getenv("TONCENTER_API_KEY") or os.getenv("TON_API_KEY") or "").strip()
        if api_key:
            headers["X-API-Key"] = api_key

        by_hash: dict[str, dict[str, Any]] = {}
        async with httpx.AsyncClient(timeout=15.0) as client:
            for address in addresses:
                try:
                    response = await client.get(
                        f"{base_url}/getTransactions",
                        params={"address": address, "limit": max(10, min(50, int(limit or 20))), "archival": "true"},
                        headers=headers,
                    )
                    response.raise_for_status()
                    transactions = response.json().get("result") or []
                except Exception as error:
                    logger.debug("Failed to fetch TON GLM transactions for %s: %s", address, error)
                    continue
                for tx in transactions:
                    if not isinstance(tx, dict):
                        continue
                    tx_hash = self._ton_tx_hash(tx)
                    if not tx_hash or tx_hash in by_hash:
                        continue
                    decoded: dict[str, Any] | None = None
                    in_msg = tx.get("in_msg") if isinstance(tx.get("in_msg"), dict) else {}
                    msg_data = in_msg.get("msg_data") if isinstance(in_msg.get("msg_data"), dict) else {}
                    decoded = self._decode_jetton_transfer_notification(
                        msg_data.get("body") if isinstance(msg_data.get("body"), str) else None,
                        decimals,
                    )
                    if decoded is None:
                        for message in tx.get("out_msgs") if isinstance(tx.get("out_msgs"), list) else []:
                            if not isinstance(message, dict):
                                continue
                            msg_data = message.get("msg_data") if isinstance(message.get("msg_data"), dict) else {}
                            decoded = self._decode_jetton_transfer(
                                msg_data.get("body") if isinstance(msg_data.get("body"), str) else None,
                                decimals,
                            )
                            if decoded:
                                break
                    if not decoded or int(decoded.get("amount") or 0) <= 0:
                        continue
                    by_hash[tx_hash] = {
                        "id": f"ton:{tx_hash}",
                        "type": "ton_incoming" if decoded.get("direction") == "incoming" else "ton_outgoing",
                        "status": "confirmed",
                        "amount": int(decoded.get("amount") or 0),
                        "reason": "external_ton_transfer",
                        "description": "Внешний перевод GLM в TON-кошельке",
                        "source": "ton_wallet",
                        "source_id": tx_hash,
                        "created_at": datetime.fromtimestamp(int(tx.get("utime") or 0), tz=timezone.utc).isoformat()
                        if tx.get("utime")
                        else None,
                        "tx_hash": tx_hash,
                        "ton_direction": decoded.get("direction"),
                        "counterparty": decoded.get("counterparty"),
                        "onchain": True,
                    }
        return sorted(by_hash.values(), key=lambda item: item.get("created_at") or "", reverse=True)[:limit]

    async def prepare_glm_to_points_ton_transaction(
        self,
        *,
        bridge: GlameTokenTransaction,
        sender_wallet_address: str | None,
    ) -> dict[str, Any]:
        if bridge.transaction_type != "bridge" or bridge.reason not in GLAME_GLM_TO_POINTS_BRIDGE_REASONS:
            raise ValueError("Это не GLM -> баллы bridge")
        if bridge.status != "pending":
            raise ValueError("TON transaction можно подготовить только для pending bridge")
        meta = bridge.meta if isinstance(bridge.meta, dict) else {}
        treasury_address = (meta.get("treasury_address") or os.getenv("TON_GLM_TREASURY_ADDRESS") or "").strip()
        if not treasury_address:
            raise ValueError("TON treasury не настроен")
        sender_wallet_address = (sender_wallet_address or meta.get("expected_ton_sender_address") or "").strip()
        if not sender_wallet_address:
            raise ValueError("TON-кошелек отправителя не привязан")

        balance_payload = await self.ton_wallet_glm_balance(sender_wallet_address)
        jetton_wallet_address = (balance_payload.get("jetton_wallet_address") or "").strip()
        if not jetton_wallet_address:
            raise ValueError("Не удалось найти GLM Jetton Wallet для привязанного TON-кошелька")

        decimals = int(os.getenv("TON_GLM_DECIMALS", "9") or 9)
        amount_glm = abs(int(bridge.amount or 0))
        amount_base_units = amount_glm * (10 ** decimals)
        forward_ton_amount = int(os.getenv("TON_GLM_TRANSFER_FORWARD_NANOTON", "1") or 1)
        tx_value = int(os.getenv("TON_GLM_TRANSFER_TX_VALUE_NANOTON", "30000000") or 30_000_000)
        query_id = int(datetime.now(timezone.utc).timestamp())

        forward_payload = Cell()
        forward_payload.bits.write_uint(0, 32)
        forward_payload.bits.write_string(f"GLAME glm_to_points bridge {bridge.id}")

        body = Cell()
        body.bits.write_uint(JETTON_TRANSFER_OP, 32)
        body.bits.write_uint(query_id, 64)
        body.bits.write_coins(amount_base_units)
        body.bits.write_address(Address(treasury_address))
        body.bits.write_address(Address(sender_wallet_address))
        body.bits.write_bit(0)
        body.bits.write_coins(forward_ton_amount)
        body.bits.write_bit(1)
        body.refs.append(forward_payload)
        payload = base64.b64encode(body.to_boc(False)).decode("ascii")

        valid_until = int(datetime.now(timezone.utc).timestamp()) + int(os.getenv("TON_GLM_CONNECT_TX_TTL_SECONDS", "600") or 600)
        now_iso = datetime.now(timezone.utc).isoformat()
        bridge.meta = {
            **meta,
            "ton_deposit_status": "wallet_request_prepared",
            "ton_deposit_requested_at": now_iso,
            "ton_deposit_sender_jetton_wallet_address": jetton_wallet_address,
            "ton_deposit_query_id": str(query_id),
            "ton_deposit_valid_until": valid_until,
        }
        flag_modified(bridge, "meta")
        await self.db.flush()
        await self.sync_bridge_operation(bridge)

        return {
            "bridge_id": str(bridge.id),
            "network": os.getenv("TON_NETWORK", "testnet").strip() or "testnet",
            "amount_glm": amount_glm,
            "amount_base_units": str(amount_base_units),
            "sender_wallet_address": sender_wallet_address,
            "sender_jetton_wallet_address": jetton_wallet_address,
            "treasury_address": treasury_address,
            "query_id": str(query_id),
            "transaction": {
                "validUntil": valid_until,
                "network": "-3" if (os.getenv("TON_NETWORK", "testnet").strip() or "testnet") == "testnet" else "-239",
                "from": sender_wallet_address,
                "messages": [
                    {
                        "address": jetton_wallet_address,
                        "amount": str(tx_value),
                        "payload": payload,
                    }
                ],
            },
            "note": "Проверьте в кошельке, что это GLM Jetton transfer в treasury GLAME.",
        }

    async def summary_for_member(self, member_id: UUID) -> dict[str, Any]:
        member = (
            await self.db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == member_id))
        ).scalar_one_or_none()
        wallet = (member.meta or {}).get("crypto_wallet") if member is not None and isinstance(member.meta, dict) else None
        wallet_address = wallet.get("address") if isinstance(wallet, dict) else None
        onchain_balance = await self.ton_wallet_glm_balance(wallet_address)
        account = (
            await self.db.execute(
                select(GlameTokenAccount).where(
                    GlameTokenAccount.referral_member_id == member_id,
                    GlameTokenAccount.token_code == GLAME_TOKEN_CODE,
                )
            )
        ).scalar_one_or_none()
        if account is None:
            return {
                **self.empty_summary(),
                "onchain_balance": onchain_balance,
            }

        pending_claim_amount = (
            await self.db.execute(
                select(func.coalesce(func.sum(GlameTokenTransaction.amount), 0)).where(
                    GlameTokenTransaction.referral_member_id == member_id,
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "claim",
                    GlameTokenTransaction.status == "pending",
                )
            )
        ).scalar_one() or 0
        earned_total = (
            await self.db.execute(
                select(func.coalesce(func.sum(GlameTokenTransaction.amount), 0)).where(
                    GlameTokenTransaction.referral_member_id == member_id,
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "earn",
                    GlameTokenTransaction.status != "canceled",
                )
            )
        ).scalar_one() or 0
        converted_total = (
            await self.db.execute(
                select(func.coalesce(func.sum(GlameTokenTransaction.amount), 0)).where(
                    GlameTokenTransaction.referral_member_id == member_id,
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "conversion",
                    GlameTokenTransaction.status == "available",
                )
            )
        ).scalar_one() or 0
        onchain_privilege_score = self._parse_glm_units(onchain_balance.get("balance_glm"))
        ledger_privilege_score = max(0, int(account.lifetime_earned or 0) - int(account.lifetime_burned or 0))
        privilege_score = onchain_privilege_score if onchain_balance.get("status") == "ok" else ledger_privilege_score
        tier_payload = self.tier_payload(privilege_score)
        policy = self.policy_payload()
        policy["store_items"] = await self.reward_store_items(only_active=True)
        return {
            **policy,
            "account_id": str(account.id),
            "status": account.status,
            "balance": int(account.balance or 0),
            "hold_balance": int(account.hold_balance or 0),
            "lifetime_earned": int(account.lifetime_earned or 0),
            "lifetime_burned": int(account.lifetime_burned or 0),
            "earned_total": int(earned_total or 0),
            "converted_total": int(converted_total or 0),
            "claimable_balance": int(account.balance or 0),
            "pending_claim_amount": int(pending_claim_amount or 0),
            "pending_claim": int(pending_claim_amount or 0) > 0,
            "onchain_balance": onchain_balance,
            "privilege_score": privilege_score,
            "privilege_score_basis": "ton_wallet_balance" if onchain_balance.get("status") == "ok" else "ledger_lifetime",
            "ledger_privilege_score": ledger_privilege_score,
            "onchain_privilege_score": onchain_privilege_score,
            **tier_payload,
        }

    async def convert_bonus_points_to_glm(
        self,
        *,
        member: ReferralProgramMember,
        points: int,
    ) -> GlameTokenTransaction:
        amount = int(points or 0)
        if amount < GLAME_BONUS_CONVERSION_MIN:
            raise ValueError(f"Минимальный bridge в GLM — {GLAME_BONUS_CONVERSION_MIN} баллов")
        if amount > GLAME_BONUS_CONVERSION_MAX:
            raise ValueError(f"Максимальный bridge в GLM за операцию — {GLAME_BONUS_CONVERSION_MAX} баллов")

        user = (
            await self.db.execute(select(User).where(User.id == member.user_id).with_for_update())
        ).scalar_one_or_none()
        if user is None:
            raise ValueError("Пользователь не найден")
        if int(user.loyalty_points or 0) < amount:
            raise ValueError("Недостаточно бонусных баллов для перевода в GLM")

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_converted = (
            await self.db.execute(
                select(func.coalesce(func.sum(GlameTokenTransaction.amount), 0)).where(
                    GlameTokenTransaction.referral_member_id == member.id,
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "conversion",
                    GlameTokenTransaction.status == "available",
                    GlameTokenTransaction.created_at >= month_start,
                )
            )
        ).scalar_one() or 0
        if int(month_converted or 0) + amount > GLAME_BONUS_CONVERSION_MONTHLY_LIMIT:
            raise ValueError(f"Месячный лимит bridge в GLM — {GLAME_BONUS_CONVERSION_MONTHLY_LIMIT} GLM")

        account = await self.get_or_create_account(user_id=member.user_id, referral_member_id=member.id)
        account = await self._locked_account(account.id)
        user.loyalty_points = int(user.loyalty_points or 0) - amount
        account.balance = int(account.balance or 0) + amount
        account.lifetime_earned = int(account.lifetime_earned or 0) + amount

        conversion_key = str(uuid4())
        loyalty_tx = LoyaltyTransaction(
            user_id=member.user_id,
            transaction_type="spend",
            points=-amount,
            balance_after=int(user.loyalty_points or 0),
            reason="points_to_glm_bridge",
            description="Bridge: перевод бонусных баллов 1С в GLM.",
            source="crypto_glame",
            source_id=f"points_to_glm:{conversion_key}:loyalty",
        )
        self.db.add(loyalty_tx)
        await self.db.flush()

        glm_tx = GlameTokenTransaction(
            account_id=account.id,
            user_id=member.user_id,
            referral_member_id=member.id,
            token_code=GLAME_TOKEN_CODE,
            transaction_type="conversion",
            status="available",
            amount=amount,
            balance_after=int(account.balance or 0),
            hold_balance_after=int(account.hold_balance or 0),
            reason="points_to_glm_bridge",
            description="Bridge: бонусные баллы 1С переведены в GLM.",
            source="loyalty_points",
            source_id=f"points_to_glm:{conversion_key}:glm",
            meta={
                "bridge_type": "points_to_glm",
                "loyalty_transaction_id": str(loyalty_tx.id),
                "points_converted": amount,
                "rate": "1 bonus point = 1 GLM",
                "policy": "points_to_glm bridge with monthly and per-transaction limits",
            },
        )
        self.db.add(glm_tx)
        await self.db.flush()
        onec_spend_result = await self._sync_points_to_glm_spend_to_onec(
            bridge=glm_tx,
            user=user,
            points=amount,
            operation="points_to_glm",
        )
        if (
            _env_bool("ONEC_GLM_BRIDGE_SPEND_REQUIRE_SUCCESS", "false")
            and onec_spend_result.get("status") != "success"
        ):
            raise ValueError(f"1C не подтвердил списание баллов: {onec_spend_result.get('error') or onec_spend_result.get('status')}")
        glm_tx.meta = {
            **(glm_tx.meta or {}),
            "onec_spend_document_id": onec_spend_result.get("document_id"),
            "onec_spend_sync_status": onec_spend_result.get("status"),
            "onec_spend_sync_error": onec_spend_result.get("error"),
            "onec_spend_request_payload": onec_spend_result.get("payload"),
            "onec_spend_response_payload": onec_spend_result.get("response"),
        }
        flag_modified(glm_tx, "meta")
        await self.sync_bridge_operation(glm_tx)
        return glm_tx

    async def bridge_points_to_glm(
        self,
        *,
        member: ReferralProgramMember,
        points: int,
    ) -> GlameTokenTransaction:
        return await self.convert_bonus_points_to_glm(member=member, points=points)

    async def sync_bridge_operation(self, tx: GlameTokenTransaction) -> GlameTokenBridgeOperation | None:
        if tx.token_code != GLAME_TOKEN_CODE:
            return None
        if tx.transaction_type == "bridge" and tx.reason in GLAME_GLM_TO_POINTS_BRIDGE_REASONS:
            direction = "glm_to_points"
        elif tx.transaction_type in {"claim", "conversion"} and tx.reason in {"points_to_ton_bridge", "points_to_glm_bridge"}:
            direction = "points_to_glm"
        else:
            return None

        meta = tx.meta if isinstance(tx.meta, dict) else {}
        auto_transfer = meta.get("ton_auto_transfer") if isinstance(meta.get("ton_auto_transfer"), dict) else {}
        ton_tx_hash = (
            meta.get("deposit_tx_hash")
            or meta.get("tx_hash")
            or auto_transfer.get("tx_hash")
        )
        ton_status = (
            meta.get("ton_deposit_status")
            or auto_transfer.get("status")
            or ("tx_hash_present" if ton_tx_hash else None)
        )
        onec_document_id = meta.get("onec_document_id") or meta.get("onec_spend_document_id")
        onec_status = meta.get("onec_sync_status") or meta.get("onec_spend_sync_status")
        onec_error = meta.get("onec_sync_error") or meta.get("onec_spend_sync_error")
        requested_at = _parse_datetime(meta.get("requested_at")) or tx.created_at
        processed_at = _parse_datetime(meta.get("processed_at"))
        points_amount = int(meta.get("target_points") or meta.get("points_converted") or abs(int(tx.amount or 0)) or 0)
        glm_amount = int(meta.get("glm_amount") or abs(int(tx.amount or 0)) or points_amount)

        existing = (
            await self.db.execute(
                select(GlameTokenBridgeOperation)
                .where(GlameTokenBridgeOperation.transaction_id == tx.id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        payload = {
            "account_id": tx.account_id,
            "user_id": tx.user_id,
            "referral_member_id": tx.referral_member_id,
            "token_code": tx.token_code,
            "direction": direction,
            "status": tx.status,
            "idempotency_key": tx.source_id or str(tx.id),
            "points_amount": points_amount,
            "glm_amount": glm_amount,
            "rate_basis": meta.get("rate") or "1 GLM = 1 point",
            "ton_network": meta.get("ton_network") or os.getenv("TON_NETWORK", "testnet"),
            "ton_sender_address": meta.get("expected_ton_sender_address") or meta.get("ton_sender_address"),
            "ton_recipient_address": meta.get("wallet_address") or meta.get("ton_recipient_address"),
            "ton_treasury_address": meta.get("treasury_address") or os.getenv("TON_GLM_TREASURY_ADDRESS") or None,
            "ton_tx_hash": ton_tx_hash,
            "ton_status": ton_status,
            "onec_document_id": onec_document_id,
            "onec_status": onec_status,
            "onec_error": onec_error,
            "source": tx.source,
            "source_id": tx.source_id,
            "meta": {
                "transaction_type": tx.transaction_type,
                "reason": tx.reason,
                "debit_source": meta.get("debit_source"),
                "wallet_app": meta.get("wallet_app"),
                "bridge_meta_version": 1,
            },
            "requested_at": requested_at,
            "processed_at": processed_at,
        }
        if existing is None:
            existing = GlameTokenBridgeOperation(transaction_id=tx.id, **payload)
            self.db.add(existing)
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
        await self.db.flush()
        return existing

    async def _sync_points_to_glm_spend_to_onec(
        self,
        *,
        bridge: GlameTokenTransaction,
        user: User,
        points: int,
        operation: str,
        manual_document_id: str | None = None,
    ) -> dict[str, Any]:
        comment_operation = (operation or "points_to_glm").strip() or "points_to_glm"
        comment = f"crypto_glame_{comment_operation}:{bridge.id}"
        bonus_program_key = (
            os.getenv("ONEC_GLM_BRIDGE_SPEND_BONUS_PROGRAM_KEY")
            or os.getenv("ONEC_BONUS_PROGRAM_KEY")
            or os.getenv("ONEC_GLM_BRIDGE_BONUS_PROGRAM_KEY")
            or os.getenv("ONEC_WELCOME_BONUS_PROGRAM_KEY")
            or "ffa42f0e-ba53-11f0-836e-fa163e4cc04e"
        )
        card_ref_key = str(getattr(user, "discount_card_id_1c", None) or "").strip()
        payload = {
            "document_type": "Document_НачислениеСписаниеБонусныхБаллов",
            "operation": operation,
            "comment": comment,
            "bonus_program_key": bonus_program_key,
            "discount_card_id_1c": card_ref_key or None,
            "customer_id_1c": getattr(user, "customer_id_1c", None),
            "points": points,
            "bridge_transaction_id": str(bridge.id),
            "bridge_reason": bridge.reason,
        }
        if manual_document_id:
            return {
                "status": "manual_spend_document_recorded",
                "document_id": manual_document_id,
                "payload": payload,
            }
        if not card_ref_key:
            return {
                "status": "missing_discount_card",
                "payload": payload,
                "error": "У пользователя нет discount_card_id_1c",
            }
        if not _env_bool("ONEC_GLM_BRIDGE_SPEND_SYNC_ENABLED", "false"):
            return {
                "status": "ready_for_1c_spend",
                "payload": payload,
            }

        try:
            balance_before: int | None = None
            if _env_bool("ONEC_GLM_BRIDGE_SPEND_VERIFY_BALANCE", "true"):
                try:
                    async with OneCCustomersService() as customers_onec:
                        before_payload = await customers_onec.fetch_loyalty_balance(
                            getattr(user, "customer_id_1c", None),
                            card_ref_key,
                        )
                    if before_payload and before_payload.get("balance") is not None:
                        balance_before = int(before_payload.get("balance") or 0)
                        payload["balance_before"] = balance_before
                        payload["balance_before_source_id"] = before_payload.get("source_id")
                except Exception as balance_error:
                    payload["balance_before_error"] = str(balance_error)[:1000]

            async with OneCOutboundService() as onec:
                existing = await onec.find_welcome_bonus_doc(comment)
                response_payload: dict[str, Any] | None = None
                if existing:
                    doc_ref_key = str(existing.get("Ref_Key") or "")
                    if doc_ref_key:
                        await onec.unpost_welcome_bonus_doc(doc_ref_key)
                        response_payload = await onec.update_bonus_spend_doc(
                            doc_ref_key=doc_ref_key,
                            bonus_program_key=bonus_program_key,
                            card_ref_key=card_ref_key,
                            points=points,
                            comment=comment,
                        )
                        await onec.post_welcome_bonus_doc(doc_ref_key)
                        document_id = doc_ref_key
                    else:
                        document_id = None
                else:
                    created = await onec.create_bonus_spend_doc(
                        bonus_program_key=bonus_program_key,
                        card_ref_key=card_ref_key,
                        points=points,
                        comment=comment,
                    )
                    document_id = str(created.get("Ref_Key") or "")
                    response_payload = created
                    if document_id:
                        await onec.post_welcome_bonus_doc(document_id)

                balance_after: int | None = None
                balance_after_payload: dict[str, Any] | None = None
                if _env_bool("ONEC_GLM_BRIDGE_SPEND_VERIFY_BALANCE", "true"):
                    try:
                        async with OneCCustomersService() as customers_onec:
                            balance_after_payload = await customers_onec.fetch_loyalty_balance(
                                getattr(user, "customer_id_1c", None),
                                card_ref_key,
                            )
                        if balance_after_payload and balance_after_payload.get("balance") is not None:
                            balance_after = int(balance_after_payload.get("balance") or 0)
                            payload["balance_after"] = balance_after
                            payload["balance_after_source_id"] = balance_after_payload.get("source_id")
                    except Exception as balance_error:
                        payload["balance_after_error"] = str(balance_error)[:1000]

                if balance_before is not None and balance_after is not None:
                    expected_max_balance = balance_before - int(points or 0)
                    local_expected_balance = int(getattr(user, "loyalty_points", 0) or 0)
                    balance_decreased_now = balance_after <= expected_max_balance
                    balance_matches_local_debit = balance_after <= local_expected_balance
                    if not (balance_decreased_now or balance_matches_local_debit):
                        return {
                            "status": "posted_without_balance_change",
                            "document_id": document_id or None,
                            "payload": payload,
                            "response": response_payload,
                            "error": (
                                f"1C document posted, but loyalty balance did not decrease enough: "
                                f"before={balance_before}, after={balance_after}, points={points}, "
                                f"local_expected={local_expected_balance}"
                            ),
                        }
                return {
                    "status": "success" if document_id else "created_without_ref_key",
                    "document_id": document_id or None,
                    "payload": payload,
                    "response": response_payload,
                }
        except Exception as error:
            return {
                "status": "failed",
                "payload": payload,
                "error": str(error)[:2000],
            }

    async def _sync_points_to_glm_refund_to_onec(
        self,
        *,
        claim: GlameTokenTransaction,
        user: User,
        points: int,
    ) -> dict[str, Any]:
        meta = claim.meta if isinstance(claim.meta, dict) else {}
        spend_status = str(meta.get("onec_spend_sync_status") or "")
        if spend_status != "success":
            return {
                "status": "skipped_spend_not_success",
                "spend_status": spend_status or None,
            }
        spend_document_id = str(meta.get("onec_spend_document_id") or "").strip()
        if not spend_document_id:
            return {
                "status": "missing_spend_document_id",
                "error": "Нельзя отменить 1С-списание: нет onec_spend_document_id",
            }

        card_ref_key = str(getattr(user, "discount_card_id_1c", None) or "").strip()
        payload = {
            "document_type": "Document_НачислениеСписаниеБонусныхБаллов",
            "operation": "points_to_ton_cancel_unpost_spend",
            "discount_card_id_1c": card_ref_key or None,
            "customer_id_1c": getattr(user, "customer_id_1c", None),
            "points": points,
            "bridge_transaction_id": str(claim.id),
            "bridge_reason": claim.reason,
            "original_spend_document_id": spend_document_id,
        }
        if not card_ref_key:
            return {
                "status": "missing_discount_card",
                "payload": payload,
                "error": "У пользователя нет discount_card_id_1c",
            }
        if not _env_bool("ONEC_GLM_BRIDGE_SPEND_SYNC_ENABLED", "false"):
            return {
                "status": "ready_for_1c_refund",
                "payload": payload,
            }

        try:
            if _env_bool("ONEC_GLM_BRIDGE_SPEND_VERIFY_BALANCE", "true"):
                try:
                    async with OneCCustomersService() as customers_onec:
                        payload["balance_before"] = await customers_onec.fetch_loyalty_balance(
                            getattr(user, "customer_id_1c", None),
                            card_ref_key,
                        )
                except Exception as balance_error:
                    payload["balance_before_error"] = str(balance_error)[:1000]

            async with OneCOutboundService() as onec:
                await onec.unpost_welcome_bonus_doc(spend_document_id)

            if _env_bool("ONEC_GLM_BRIDGE_SPEND_VERIFY_BALANCE", "true"):
                try:
                    async with OneCCustomersService() as customers_onec:
                        payload["balance_after"] = await customers_onec.fetch_loyalty_balance(
                            getattr(user, "customer_id_1c", None),
                            card_ref_key,
                        )
                except Exception as balance_error:
                    payload["balance_after_error"] = str(balance_error)[:1000]

            return {
                "status": "success",
                "document_id": spend_document_id,
                "payload": payload,
                "response": {"unposted_spend_document_id": spend_document_id},
            }
        except Exception as error:
            return {
                "status": "failed",
                "payload": payload,
                "error": str(error)[:2000],
            }

    async def request_points_to_ton_bridge(
        self,
        *,
        member: ReferralProgramMember,
        wallet: dict[str, Any],
        points: int,
    ) -> GlameTokenTransaction:
        amount = int(points or 0)
        if amount < GLAME_BONUS_CONVERSION_MIN:
            raise ValueError(f"Минимальный bridge в GLM — {GLAME_BONUS_CONVERSION_MIN} баллов")
        if amount > GLAME_BONUS_CONVERSION_MAX:
            raise ValueError(f"Максимальный bridge в GLM за операцию — {GLAME_BONUS_CONVERSION_MAX} баллов")

        user = (
            await self.db.execute(select(User).where(User.id == member.user_id).with_for_update())
        ).scalar_one_or_none()
        if user is None:
            raise ValueError("Пользователь не найден")
        if int(user.loyalty_points or 0) < amount:
            raise ValueError("Недостаточно бонусных баллов для перевода в GLM")

        account = await self.get_or_create_account(user_id=member.user_id, referral_member_id=member.id)
        account = await self._locked_account(account.id)
        existing_pending = (
            await self.db.execute(
                select(GlameTokenTransaction).where(
                    GlameTokenTransaction.account_id == account.id,
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "claim",
                    GlameTokenTransaction.status == "pending",
                )
            )
        ).scalar_one_or_none()
        if existing_pending is not None:
            raise ValueError("У вас уже есть заявка на вывод GLM в обработке")

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_claimed = (
            await self.db.execute(
                select(func.coalesce(func.sum(GlameTokenTransaction.amount), 0)).where(
                    GlameTokenTransaction.referral_member_id == member.id,
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "claim",
                    GlameTokenTransaction.status.in_(("pending", "processed")),
                    GlameTokenTransaction.reason == "points_to_ton_bridge",
                    GlameTokenTransaction.created_at >= month_start,
                )
            )
        ).scalar_one() or 0
        if int(month_claimed or 0) + amount > GLAME_BONUS_CONVERSION_MONTHLY_LIMIT:
            raise ValueError(f"Месячный лимит bridge в GLM — {GLAME_BONUS_CONVERSION_MONTHLY_LIMIT} GLM")

        bridge_key = str(uuid4())
        user.loyalty_points = int(user.loyalty_points or 0) - amount
        loyalty_tx = LoyaltyTransaction(
            user_id=member.user_id,
            transaction_type="spend",
            points=-amount,
            balance_after=int(user.loyalty_points or 0),
            reason="points_to_ton_bridge",
            description="Bridge: бонусные баллы 1С переведены в заявку на отправку GLM из treasury в TON.",
            source="crypto_glame",
            source_id=f"points_to_ton:{bridge_key}:loyalty",
        )
        self.db.add(loyalty_tx)
        await self.db.flush()

        tx = GlameTokenTransaction(
            account_id=account.id,
            user_id=member.user_id,
            referral_member_id=member.id,
            token_code=GLAME_TOKEN_CODE,
            transaction_type="claim",
            status="pending",
            amount=amount,
            balance_after=int(account.balance or 0),
            hold_balance_after=int(account.hold_balance or 0),
            reason="points_to_ton_bridge",
            description="Bridge: баллы списаны, GLM ожидает перевода из treasury GLAME в подтвержденный TON-кошелек.",
            source="ton_claim",
            source_id=f"points_to_ton:{bridge_key}:claim",
            meta={
                "bridge_type": "points_to_ton",
                "debit_source": "loyalty_points",
                "wallet_address": wallet.get("address"),
                "wallet_app": wallet.get("wallet_app") or wallet.get("label"),
                "wallet_verified_at": wallet.get("verified_at"),
                "loyalty_transaction_id": str(loyalty_tx.id),
                "points_converted": amount,
                "rate": "1 bonus point = 1 GLM",
                "requested_at": now.isoformat(),
                "policy": "points to TON bridge; operator transfers existing GLM from GLAME treasury/bank to user TON wallet",
                "operator_action": "transfer_testnet_glm_from_treasury_to_wallet",
            },
        )
        account.meta = {
            **(account.meta or {}),
            "pending_claim": {
                "amount": amount,
                "requested_at": now.isoformat(),
                "wallet_address": wallet.get("address"),
                "transaction_source_id": tx.source_id,
                "bridge_type": "points_to_ton",
            },
        }

    async def prepare_reward_store_ton_transaction(
        self,
        *,
        redemption: GlameTokenTransaction,
        sender_wallet_address: str | None,
    ) -> dict[str, Any]:
        if redemption.transaction_type != "redemption" or redemption.reason != "glm_store_item":
            raise ValueError("Это не GLM Store redemption")
        if redemption.status != "pending_ton_payment":
            raise ValueError("TON transaction можно подготовить только для pending TON payment")
        meta = redemption.meta if isinstance(redemption.meta, dict) else {}
        treasury_address = (meta.get("treasury_address") or os.getenv("TON_GLM_TREASURY_ADDRESS") or "").strip()
        if not treasury_address:
            raise ValueError("TON treasury не настроен")
        sender_wallet_address = (sender_wallet_address or meta.get("expected_ton_sender_address") or "").strip()
        if not sender_wallet_address:
            raise ValueError("TON-кошелек отправителя не привязан")

        balance_payload = await self.ton_wallet_glm_balance(sender_wallet_address)
        jetton_wallet_address = (balance_payload.get("jetton_wallet_address") or "").strip()
        if not jetton_wallet_address:
            raise ValueError("Не удалось найти GLM Jetton Wallet для привязанного TON-кошелька")

        decimals = int(os.getenv("TON_GLM_DECIMALS", "9") or 9)
        amount_glm = abs(int(redemption.amount or 0))
        amount_base_units = amount_glm * (10 ** decimals)
        forward_ton_amount = int(os.getenv("TON_GLM_TRANSFER_FORWARD_NANOTON", "1") or 1)
        tx_value = int(os.getenv("TON_GLM_TRANSFER_TX_VALUE_NANOTON", "30000000") or 30_000_000)
        query_id = int(datetime.now(timezone.utc).timestamp())

        forward_payload = Cell()
        forward_payload.bits.write_uint(0, 32)
        forward_payload.bits.write_string(f"GLAME reward_store redemption {redemption.id}")

        body = Cell()
        body.bits.write_uint(JETTON_TRANSFER_OP, 32)
        body.bits.write_uint(query_id, 64)
        body.bits.write_coins(amount_base_units)
        body.bits.write_address(Address(treasury_address))
        body.bits.write_address(Address(sender_wallet_address))
        body.bits.write_bit(0)
        body.bits.write_coins(forward_ton_amount)
        body.bits.write_bit(1)
        body.refs.append(forward_payload)
        payload = base64.b64encode(body.to_boc(False)).decode("ascii")

        valid_until = int(datetime.now(timezone.utc).timestamp()) + int(os.getenv("TON_GLM_CONNECT_TX_TTL_SECONDS", "600") or 600)
        now_iso = datetime.now(timezone.utc).isoformat()
        redemption.meta = {
            **meta,
            "ton_deposit_status": "wallet_request_prepared",
            "ton_deposit_requested_at": now_iso,
            "ton_deposit_sender_jetton_wallet_address": jetton_wallet_address,
            "ton_deposit_query_id": str(query_id),
            "ton_deposit_valid_until": valid_until,
        }
        flag_modified(redemption, "meta")
        await self.db.flush()

        return {
            "redemption_id": str(redemption.id),
            "network": os.getenv("TON_NETWORK", "testnet").strip() or "testnet",
            "amount_glm": amount_glm,
            "amount_base_units": str(amount_base_units),
            "sender_wallet_address": sender_wallet_address,
            "sender_jetton_wallet_address": jetton_wallet_address,
            "treasury_address": treasury_address,
            "query_id": str(query_id),
            "transaction": {
                "validUntil": valid_until,
                "messages": [
                    {
                        "address": jetton_wallet_address,
                        "amount": str(tx_value),
                        "payload": payload,
                    }
                ],
            },
        }
        flag_modified(account, "meta")
        self.db.add(tx)
        await self.db.flush()
        onec_spend_result = await self._sync_points_to_glm_spend_to_onec(
            bridge=tx,
            user=user,
            points=amount,
            operation="points_to_ton",
        )
        if (
            _env_bool("ONEC_GLM_BRIDGE_SPEND_REQUIRE_SUCCESS", "false")
            and onec_spend_result.get("status") != "success"
        ):
            raise ValueError(f"1C не подтвердил списание баллов: {onec_spend_result.get('error') or onec_spend_result.get('status')}")
        tx.meta = {
            **(tx.meta or {}),
            "onec_spend_document_id": onec_spend_result.get("document_id"),
            "onec_spend_sync_status": onec_spend_result.get("status"),
            "onec_spend_sync_error": onec_spend_result.get("error"),
            "onec_spend_request_payload": onec_spend_result.get("payload"),
            "onec_spend_response_payload": onec_spend_result.get("response"),
        }
        flag_modified(tx, "meta")
        await self.sync_bridge_operation(tx)
        return tx

    async def request_ton_claim(
        self,
        *,
        member: ReferralProgramMember,
        wallet: dict[str, Any],
        amount: int | None = None,
        source_transaction: GlameTokenTransaction | None = None,
    ) -> GlameTokenTransaction:
        account = await self.get_or_create_account(user_id=member.user_id, referral_member_id=member.id)
        account = await self._locked_account(account.id)
        claim_amount = int(amount if amount is not None else account.balance or 0)
        if claim_amount <= 0:
            raise ValueError("Нет доступных GLM для вывода")
        if int(account.balance or 0) < claim_amount:
            raise ValueError("Недостаточно доступных GLM для вывода")

        existing_pending = (
            await self.db.execute(
                select(GlameTokenTransaction).where(
                    GlameTokenTransaction.account_id == account.id,
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "claim",
                    GlameTokenTransaction.status == "pending",
                )
            )
        ).scalar_one_or_none()
        if existing_pending is not None:
            raise ValueError("У вас уже есть заявка на вывод GLM в обработке")

        now = datetime.now(timezone.utc)
        account.balance = int(account.balance or 0) - claim_amount
        tx = GlameTokenTransaction(
            account_id=account.id,
            user_id=member.user_id,
            referral_member_id=member.id,
            token_code=GLAME_TOKEN_CODE,
            transaction_type="claim",
            status="pending",
            amount=claim_amount,
            balance_after=int(account.balance or 0),
            hold_balance_after=int(account.hold_balance or 0),
            reason="ton_wallet_claim",
            description="Заявка на вывод GLM в подтвержденный TON-кошелек.",
            source="ton_claim",
            source_id=f"glm_claim:{account.id}:{uuid4()}",
            meta={
                "wallet_address": wallet.get("address"),
                "wallet_app": wallet.get("wallet_app") or wallet.get("label"),
                "wallet_verified_at": wallet.get("verified_at"),
                "policy": "pending admin/on-chain settlement",
                "source_transaction_id": str(source_transaction.id) if source_transaction is not None else None,
                "source_transaction_type": source_transaction.transaction_type if source_transaction is not None else None,
                "source_bridge_type": (source_transaction.meta or {}).get("bridge_type") if source_transaction is not None and isinstance(source_transaction.meta, dict) else None,
            },
        )
        account.meta = {
            **(account.meta or {}),
            "pending_claim": {
                "amount": claim_amount,
                "requested_at": now.isoformat(),
                "wallet_address": wallet.get("address"),
                "transaction_source_id": tx.source_id,
            },
        }
        flag_modified(account, "meta")
        self.db.add(tx)
        await self.db.flush()
        return tx

    async def redeem_checkout_internal_value(
        self,
        *,
        user_id: UUID,
        amount: int,
        order_id: UUID,
        meta: dict[str, Any] | None = None,
    ) -> GlameTokenTransaction:
        redeem_amount = int(amount or 0)
        if redeem_amount <= 0:
            raise ValueError("Сумма GLM должна быть больше нуля")

        account = (
            await self.db.execute(
                select(GlameTokenAccount).where(
                    GlameTokenAccount.user_id == user_id,
                    GlameTokenAccount.token_code == GLAME_TOKEN_CODE,
                ).with_for_update()
            )
        ).scalar_one_or_none()
        if account is None:
            raise ValueError("GLM account не найден")
        if int(account.balance or 0) < redeem_amount:
            raise ValueError("Недостаточно доступных GLM")

        account.balance = int(account.balance or 0) - redeem_amount
        account.lifetime_burned = int(account.lifetime_burned or 0) + redeem_amount
        now = datetime.now(timezone.utc)
        tx = GlameTokenTransaction(
            account_id=account.id,
            user_id=user_id,
            referral_member_id=account.referral_member_id,
            token_code=GLAME_TOKEN_CODE,
            transaction_type="redemption",
            status="fulfilled",
            amount=-redeem_amount,
            balance_after=int(account.balance or 0),
            hold_balance_after=int(account.hold_balance or 0),
            reason="checkout_internal_value",
            description=f"Списание GLM как внутренней ценности заказа {order_id}.",
            source="checkout",
            source_id=f"glm_checkout:{order_id}",
            meta={
                **(meta or {}),
                "order_id": str(order_id),
                "redeemed_at": now.isoformat(),
                "fulfillment_status": "fulfilled",
                "policy": "1 GLM = 1 RUB internal checkout value within category limits",
            },
        )
        self.db.add(tx)
        await self.db.flush()
        await self.sync_bridge_operation(tx)
        return tx

    async def reward_store_items(self, only_active: bool = True) -> list[dict[str, Any]]:
        try:
            stmt = select(RewardStoreItem)
            if only_active:
                stmt = stmt.where(
                    RewardStoreItem.is_active == True,
                    RewardStoreItem.status.in_(["available", "limited"]),
                )
            rows = (
                await self.db.execute(
                    stmt.order_by(RewardStoreItem.sort_order.asc(), RewardStoreItem.created_at.asc())
                )
            ).scalars().all()
        except Exception:
            rows = []

        if not rows:
            return [dict(item) for item in GLAME_STORE_ITEMS]

        return [
            {
                "id": str(row.id),
                "sku": row.sku,
                "title": row.title,
                "description": row.description or "",
                "price_glm": int(row.price_glm or 0) if row.price_glm is not None else None,
                "price_points": int(row.price_points or 0) if row.price_points is not None else None,
                "category": row.category,
                "status": row.status,
                "inventory_status": row.inventory_status,
                "quantity_available": self._reward_store_quantity(row),
                "image_url": self._reward_store_image_url(row),
                "sort_order": int(row.sort_order or 0),
                "is_active": bool(row.is_active),
                "meta": row.meta if isinstance(row.meta, dict) else {},
            }
            for row in rows
        ]

    @staticmethod
    def _reward_store_quantity(item: RewardStoreItem) -> int | None:
        meta = item.meta if isinstance(item.meta, dict) else {}
        value = meta.get("quantity_available")
        try:
            return int(value) if value is not None and str(value).strip() != "" else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _reward_store_image_url(item: RewardStoreItem) -> str | None:
        meta = item.meta if isinstance(item.meta, dict) else {}
        value = str(meta.get("image_url") or "").strip()
        return value or None

    async def _reserve_reward_store_item(self, sku: str) -> None:
        item = (
            await self.db.execute(
                select(RewardStoreItem)
                .where(
                    RewardStoreItem.sku == sku,
                    RewardStoreItem.is_active == True,
                    RewardStoreItem.status.in_(["available", "limited"]),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if item is None:
            return
        quantity = self._reward_store_quantity(item)
        if quantity is None:
            return
        if quantity <= 0:
            raise ValueError("Товар закончился")
        meta = dict(item.meta or {})
        next_quantity = quantity - 1
        meta["quantity_available"] = next_quantity
        item.meta = meta
        if next_quantity <= 0:
            item.status = "sold_out"
            item.is_active = False
        item.updated_at = datetime.now(timezone.utc)
        flag_modified(item, "meta")

    async def request_glm_to_points_bridge(
        self,
        *,
        member: ReferralProgramMember,
        amount: int,
        target_points: int | None = None,
        note: str | None = None,
        wallet: dict[str, Any] | None = None,
        reserve_platform_balance: bool = False,
        reason: str = "glm_to_points_bridge",
        description: str | None = None,
        source_prefix: str = "glm_to_points",
        policy: str = "manual GLM to loyalty points bridge pending TON treasury deposit and admin/1C confirmation",
    ) -> GlameTokenTransaction:
        if reason not in GLAME_GLM_TO_POINTS_BRIDGE_REASONS:
            raise ValueError("Некорректный тип bridge")
        bridge_amount = int(amount or 0)
        if bridge_amount <= 0:
            raise ValueError("Сумма GLM должна быть больше нуля")
        if bridge_amount > GLAME_BONUS_CONVERSION_MAX:
            raise ValueError(f"Максимальный bridge в баллы за операцию — {GLAME_BONUS_CONVERSION_MAX} GLM")

        account = await self.get_or_create_account(user_id=member.user_id, referral_member_id=member.id)
        account = await self._locked_account(account.id)
        if reserve_platform_balance and int(account.balance or 0) < bridge_amount:
            raise ValueError("Недостаточно доступных GLM для bridge в баллы")

        existing_pending = (
            await self.db.execute(
                select(GlameTokenTransaction).where(
                    GlameTokenTransaction.account_id == account.id,
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "bridge",
                    GlameTokenTransaction.status == "pending",
                    GlameTokenTransaction.reason.in_(GLAME_GLM_TO_POINTS_BRIDGE_REASONS),
                )
            )
        ).scalar_one_or_none()
        if existing_pending is not None:
            raise ValueError("У вас уже есть pending GLM -> баллы bridge")

        points_to_credit = int(target_points or bridge_amount)
        if points_to_credit <= 0:
            raise ValueError("Сумма баллов должна быть больше нуля")

        now = datetime.now(timezone.utc)
        if reserve_platform_balance:
            account.balance = int(account.balance or 0) - bridge_amount
        wallet = wallet or {}
        tx = GlameTokenTransaction(
            account_id=account.id,
            user_id=member.user_id,
            referral_member_id=member.id,
            token_code=GLAME_TOKEN_CODE,
            transaction_type="bridge",
            status="pending",
            amount=-bridge_amount,
            balance_after=int(account.balance or 0),
            hold_balance_after=int(account.hold_balance or 0),
            reason=reason,
            description=description or "Bridge: ожидается депозит GLM в treasury для перевода в бонусные баллы 1С.",
            source="loyalty_bridge",
            source_id=f"{source_prefix}:{account.id}:{uuid4()}",
            meta={
                "bridge_type": reason,
                "debit_source": "platform_balance" if reserve_platform_balance else "ton_deposit",
                "glm_amount": bridge_amount,
                "target_points": points_to_credit,
                "requested_at": now.isoformat(),
                "note": (note or "").strip() or None,
                "expected_ton_sender_address": wallet.get("address"),
                "wallet_app": wallet.get("wallet_app") or wallet.get("label"),
                "treasury_address": (os.getenv("TON_GLM_TREASURY_ADDRESS") or "").strip() or None,
                "policy": policy,
            },
        )
        self.db.add(tx)
        await self.db.flush()
        await self.sync_bridge_operation(tx)
        return tx

    async def request_buy_loyalty_points(
        self,
        *,
        member: ReferralProgramMember,
        points: int,
        note: str | None = None,
        wallet: dict[str, Any] | None = None,
    ) -> GlameTokenTransaction:
        target_points = int(points or 0)
        if target_points < GLAME_LOYALTY_POINTS_PURCHASE_MIN:
            raise ValueError(f"Минимальная покупка — {GLAME_LOYALTY_POINTS_PURCHASE_MIN} баллов")
        if target_points > GLAME_LOYALTY_POINTS_PURCHASE_MAX:
            raise ValueError(f"Максимальная покупка за операцию — {GLAME_LOYALTY_POINTS_PURCHASE_MAX} баллов")
        glm_amount = int((Decimal(target_points) * Decimal(100 + GLAME_LOYALTY_POINTS_PURCHASE_SPREAD_PERCENT) / Decimal(100)).to_integral_value(rounding=ROUND_CEILING))
        return await self.request_glm_to_points_bridge(
            member=member,
            amount=glm_amount,
            target_points=target_points,
            note=note,
            wallet=wallet,
            reason="buy_loyalty_points",
            description="Покупка баллов лояльности за GLM с product spread GLAME.",
            source_prefix="buy_loyalty_points",
            policy=f"buy loyalty points product, {GLAME_LOYALTY_POINTS_PURCHASE_SPREAD_PERCENT}% GLAME spread, pending admin/1C confirmation",
        )

    async def _sync_glm_bridge_points_to_onec(
        self,
        *,
        bridge: GlameTokenTransaction,
        user: User,
        points: int,
        expires_at: datetime,
        manual_document_id: str | None = None,
    ) -> dict[str, Any]:
        comment = f"crypto_glame_bridge:{bridge.id}"
        bonus_program_key = (
            os.getenv("ONEC_GLM_BRIDGE_BONUS_PROGRAM_KEY")
            or os.getenv("ONEC_BONUS_PROGRAM_KEY")
            or os.getenv("ONEC_WELCOME_BONUS_PROGRAM_KEY")
            or "ffa42f0e-ba53-11f0-836e-fa163e4cc04e"
        )
        analytics_key = os.getenv("ONEC_GLM_BRIDGE_BONUS_ANALYTICS_KEY") or os.getenv(
            "ONEC_WELCOME_BONUS_ANALYTICS_KEY",
            "e6881e68-cdf4-11f0-85a1-fa163e4cc04e",
        )
        card_ref_key = str(getattr(user, "discount_card_id_1c", None) or "").strip()
        payload = {
            "document_type": "Document_НачислениеСписаниеБонусныхБаллов",
            "comment": comment,
            "bonus_program_key": bonus_program_key,
            "discount_card_id_1c": card_ref_key or None,
            "customer_id_1c": getattr(user, "customer_id_1c", None),
            "points": points,
            "expires_at": expires_at.replace(microsecond=0).isoformat(),
            "bridge_transaction_id": str(bridge.id),
            "bridge_reason": bridge.reason,
        }
        if manual_document_id:
            return {
                "status": "manual_document_recorded",
                "document_id": manual_document_id,
                "payload": payload,
            }
        if not card_ref_key:
            return {
                "status": "missing_discount_card",
                "payload": payload,
                "error": "У пользователя нет discount_card_id_1c",
            }
        if not _env_bool("ONEC_GLM_BRIDGE_BONUS_SYNC_ENABLED", "false"):
            return {
                "status": "ready_for_1c",
                "payload": payload,
            }

        try:
            async with OneCOutboundService() as onec:
                existing = await onec.find_welcome_bonus_doc(comment)
                if existing:
                    doc_ref_key = str(existing.get("Ref_Key") or "")
                    if doc_ref_key:
                        await onec.unpost_welcome_bonus_doc(doc_ref_key)
                        await onec.update_welcome_bonus_doc(
                            doc_ref_key=doc_ref_key,
                            bonus_program_key=bonus_program_key,
                            card_ref_key=card_ref_key,
                            points=points,
                            comment=comment,
                            analytics_key=analytics_key,
                            expires_at=payload["expires_at"],
                        )
                        await onec.post_welcome_bonus_doc(doc_ref_key)
                        return {"status": "success", "document_id": doc_ref_key, "payload": payload}

                created = await onec.create_welcome_bonus_doc(
                    bonus_program_key=bonus_program_key,
                    card_ref_key=card_ref_key,
                    points=points,
                    comment=comment,
                    analytics_key=analytics_key,
                    expires_at=payload["expires_at"],
                )
                doc_ref_key = str(created.get("Ref_Key") or "")
                if doc_ref_key:
                    await onec.post_welcome_bonus_doc(doc_ref_key)
                return {
                    "status": "success" if doc_ref_key else "created_without_ref_key",
                    "document_id": doc_ref_key or None,
                    "payload": payload,
                    "response": created,
                }
        except Exception as error:
            return {
                "status": "failed",
                "payload": payload,
                "error": str(error)[:2000],
            }

    async def update_glm_to_points_bridge_status(
        self,
        *,
        bridge: GlameTokenTransaction,
        status: str,
        admin_user_id: UUID,
        points: int | None = None,
        comment: str | None = None,
        onec_document_id: str | None = None,
    ) -> GlameTokenTransaction:
        bridge = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(GlameTokenTransaction.id == bridge.id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if bridge is None:
            raise ValueError("Bridge transaction не найдена")
        if bridge.transaction_type != "bridge" or bridge.reason not in GLAME_GLM_TO_POINTS_BRIDGE_REASONS:
            raise ValueError("Транзакция не является GLM -> баллы bridge")
        if bridge.status != "pending":
            raise ValueError("Можно обработать только pending bridge")
        if status not in {"processed", "failed", "canceled"}:
            raise ValueError("Некорректный статус bridge")

        account = await self._locked_account(bridge.account_id)

        meta = bridge.meta if isinstance(bridge.meta, dict) else {}
        reserved_glm = abs(int(bridge.amount or 0))
        points_to_credit = int(points or meta.get("target_points") or reserved_glm)
        now = datetime.now(timezone.utc)

        if status == "processed":
            if points_to_credit <= 0:
                raise ValueError("Сумма баллов должна быть больше нуля")
            user = (
                await self.db.execute(select(User).where(User.id == bridge.user_id).with_for_update())
            ).scalar_one_or_none()
            if user is None:
                raise ValueError("Пользователь не найден")
            user.loyalty_points = int(user.loyalty_points or 0) + points_to_credit
            points_expires_at = now + timedelta(days=GLAME_LOYALTY_POINTS_FROM_GLM_EXPIRES_DAYS)
            loyalty_tx = LoyaltyTransaction(
                user_id=bridge.user_id,
                transaction_type="earn",
                points=points_to_credit,
                balance_after=int(user.loyalty_points or 0),
                reason=bridge.reason,
                description="Bridge: GLM переведены в бонусные баллы 1С.",
                source="crypto_glame",
                source_id=f"{bridge.source_id}:loyalty",
                expires_at=points_expires_at,
            )
            self.db.add(loyalty_tx)
            await self.db.flush()
            onec_result = await self._sync_glm_bridge_points_to_onec(
                bridge=bridge,
                user=user,
                points=points_to_credit,
                expires_at=points_expires_at,
                manual_document_id=(onec_document_id or "").strip() or None,
            )
            bridge.meta = {
                **meta,
                "processed_at": now.isoformat(),
                "processed_by": str(admin_user_id),
                "processed_points": points_to_credit,
                "loyalty_transaction_id": str(loyalty_tx.id),
                "loyalty_points_expires_at": points_expires_at.isoformat(),
                "loyalty_points_expires_days": GLAME_LOYALTY_POINTS_FROM_GLM_EXPIRES_DAYS,
                "onec_document_id": onec_result.get("document_id") or (onec_document_id or "").strip() or None,
                "onec_sync_status": onec_result.get("status"),
                "onec_sync_error": onec_result.get("error"),
                "onec_request_payload": onec_result.get("payload"),
                "onec_response_payload": onec_result.get("response"),
                "admin_comment": (comment or "").strip() or None,
            }
            account.lifetime_burned = int(account.lifetime_burned or 0) + reserved_glm
        else:
            if meta.get("debit_source") != "ton_deposit":
                account.balance = int(account.balance or 0) + reserved_glm
            bridge.meta = {
                **meta,
                "processed_at": now.isoformat(),
                "processed_by": str(admin_user_id),
                "refunded_glm": reserved_glm if meta.get("debit_source") != "ton_deposit" else 0,
                "admin_comment": (comment or "").strip() or None,
            }

        bridge.status = status
        bridge.balance_after = int(account.balance or 0)
        bridge.hold_balance_after = int(account.hold_balance or 0)
        flag_modified(bridge, "meta")
        await self.db.flush()
        await self.sync_bridge_operation(bridge)
        return bridge

    async def reconcile_bridge_operations(self, *, stale_hours: int = 48, limit: int = 500) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(hours=max(1, int(stale_hours or 48)))
        bridge_rows = (
            await self.db.execute(
                select(GlameTokenTransaction, GlameTokenAccount)
                .join(GlameTokenAccount, GlameTokenAccount.id == GlameTokenTransaction.account_id)
                .where(
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "bridge",
                    GlameTokenTransaction.reason.in_(GLAME_GLM_TO_POINTS_BRIDGE_REASONS),
                )
                .order_by(desc(GlameTokenTransaction.created_at))
                .limit(limit)
            )
        ).all()
        points_to_glm_rows = (
            await self.db.execute(
                select(GlameTokenTransaction, GlameTokenAccount)
                .join(GlameTokenAccount, GlameTokenAccount.id == GlameTokenTransaction.account_id)
                .where(
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type.in_(("claim", "conversion")),
                    GlameTokenTransaction.reason.in_(("points_to_ton_bridge", "points_to_glm_bridge")),
                )
                .order_by(desc(GlameTokenTransaction.created_at))
                .limit(limit)
            )
        ).all()
        negative_accounts = (
            await self.db.execute(
                select(GlameTokenAccount)
                .where(
                    GlameTokenAccount.token_code == GLAME_TOKEN_CODE,
                    (GlameTokenAccount.balance < 0) | (GlameTokenAccount.hold_balance < 0),
                )
                .limit(100)
            )
        ).scalars().all()
        bridge_operation_rows = (
            await self.db.execute(
                select(GlameTokenBridgeOperation, GlameTokenTransaction, GlameTokenAccount)
                .join(GlameTokenTransaction, GlameTokenTransaction.id == GlameTokenBridgeOperation.transaction_id)
                .join(GlameTokenAccount, GlameTokenAccount.id == GlameTokenBridgeOperation.account_id)
                .where(GlameTokenBridgeOperation.token_code == GLAME_TOKEN_CODE)
                .order_by(desc(GlameTokenBridgeOperation.created_at))
                .limit(limit)
            )
        ).all()
        bridge_operation_total = (
            await self.db.execute(
                select(func.count(GlameTokenBridgeOperation.id)).where(
                    GlameTokenBridgeOperation.token_code == GLAME_TOKEN_CODE
                )
            )
        ).scalar_one() or 0
        bridge_operation_missing_domain_count = (
            await self.db.execute(
                select(func.count(GlameTokenTransaction.id)).where(
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    or_(
                        and_(
                            GlameTokenTransaction.transaction_type == "bridge",
                            GlameTokenTransaction.reason.in_(GLAME_GLM_TO_POINTS_BRIDGE_REASONS),
                        ),
                        and_(
                            GlameTokenTransaction.transaction_type.in_(("claim", "conversion")),
                            GlameTokenTransaction.reason.in_(("points_to_ton_bridge", "points_to_glm_bridge")),
                        ),
                    ),
                    ~GlameTokenTransaction.id.in_(select(GlameTokenBridgeOperation.transaction_id)),
                )
            )
        ).scalar_one() or 0

        issues: list[dict[str, Any]] = []
        bridge_operation_by_direction: dict[str, dict[str, Any]] = {}
        bridge_operation_by_status: dict[str, dict[str, int]] = {}
        bridge_operation_stale_pending_count = 0
        bridge_operation_consistency_issue_count = 0
        for operation, tx, account in bridge_operation_rows:
            direction_key = str(operation.direction or "unknown")
            status_key = str(operation.status or "unknown")
            direction_bucket = bridge_operation_by_direction.setdefault(direction_key, {"count": 0, "amount_glm": 0, "statuses": {}})
            direction_bucket["count"] += 1
            direction_bucket["amount_glm"] += int(operation.glm_amount or 0)
            direction_bucket["statuses"][status_key] = int(direction_bucket["statuses"].get(status_key, 0)) + 1
            status_bucket = bridge_operation_by_status.setdefault(status_key, {"count": 0, "amount_glm": 0})
            status_bucket["count"] += 1
            status_bucket["amount_glm"] += int(operation.glm_amount or 0)

            requested_at = operation.requested_at or operation.created_at
            if requested_at and requested_at.tzinfo is None:
                requested_at = requested_at.replace(tzinfo=timezone.utc)
            if operation.status == "pending" and requested_at and requested_at < stale_before:
                bridge_operation_stale_pending_count += 1
                issues.append({
                    "severity": "warn",
                    "code": "domain_stale_pending_bridge",
                    "operation": operation.direction,
                    "bridge_operation_id": str(operation.id),
                    "transaction_id": str(operation.transaction_id),
                    "account_id": str(account.id),
                    "message": f"Bridge operation pending старше {stale_hours} часов",
                })

            expected_direction = (
                "glm_to_points"
                if tx.transaction_type == "bridge" and tx.reason in GLAME_GLM_TO_POINTS_BRIDGE_REASONS
                else "points_to_glm"
            )
            expected_glm_amount = abs(int(tx.amount or 0))
            if operation.direction != expected_direction:
                bridge_operation_consistency_issue_count += 1
                issues.append({
                    "severity": "error",
                    "code": "domain_direction_mismatch",
                    "bridge_operation_id": str(operation.id),
                    "transaction_id": str(tx.id),
                    "account_id": str(account.id),
                    "message": f"Bridge operation direction={operation.direction}, legacy direction={expected_direction}",
                })
            if operation.status != tx.status:
                bridge_operation_consistency_issue_count += 1
                issues.append({
                    "severity": "warn",
                    "code": "domain_status_mismatch",
                    "bridge_operation_id": str(operation.id),
                    "transaction_id": str(tx.id),
                    "account_id": str(account.id),
                    "message": f"Bridge operation status={operation.status}, legacy status={tx.status}",
                })
            if int(operation.glm_amount or 0) != expected_glm_amount:
                bridge_operation_consistency_issue_count += 1
                issues.append({
                    "severity": "error",
                    "code": "domain_glm_amount_mismatch",
                    "bridge_operation_id": str(operation.id),
                    "transaction_id": str(tx.id),
                    "account_id": str(account.id),
                    "message": f"Bridge operation GLM={int(operation.glm_amount or 0)}, legacy GLM={expected_glm_amount}",
                })
        if int(bridge_operation_missing_domain_count or 0) > 0:
            bridge_operation_consistency_issue_count += int(bridge_operation_missing_domain_count or 0)
            issues.append({
                "severity": "error",
                "code": "domain_missing_bridge_operations",
                "message": f"{bridge_operation_missing_domain_count} legacy bridge transactions не имеют glame_token_bridge_operations rows",
            })

        pending_count = 0
        pending_reserved_glm = 0
        processed_count = 0
        processed_points = 0
        onec_ready_count = 0
        onec_failed_count = 0
        onec_spend_ready_count = 0
        onec_spend_failed_count = 0
        points_to_glm_checked_count = len(points_to_glm_rows)
        points_to_glm_pending_count = 0
        points_to_glm_processed_count = 0
        points_to_glm_canceled_count = 0
        ton_sent_waiting_count = 0
        ton_processed_without_tx_count = 0
        onec_cancel_spend_failed_count = 0

        loyalty_ids: set[str] = set()
        for tx, _account in bridge_rows:
            meta = tx.meta if isinstance(tx.meta, dict) else {}
            loyalty_id = meta.get("loyalty_transaction_id")
            if loyalty_id:
                loyalty_ids.add(str(loyalty_id))
        existing_loyalty_ids: set[str] = set()
        if loyalty_ids:
            loyalty_rows = (
                await self.db.execute(
                    select(LoyaltyTransaction.id).where(cast(LoyaltyTransaction.id, String).in_(loyalty_ids))
                )
            ).scalars().all()
            existing_loyalty_ids = {str(item) for item in loyalty_rows}

        for tx, account in bridge_rows:
            meta = tx.meta if isinstance(tx.meta, dict) else {}
            amount_abs = abs(int(tx.amount or 0))
            if tx.status == "pending":
                pending_count += 1
                pending_reserved_glm += amount_abs
                created_at = tx.created_at
                if created_at and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at and created_at < stale_before:
                    issues.append({
                        "severity": "warn",
                        "code": "stale_pending_bridge",
                        "transaction_id": str(tx.id),
                        "account_id": str(account.id),
                        "message": f"Pending bridge старше {stale_hours} часов",
                    })
            if tx.status == "processed":
                processed_count += 1
                processed_points += int(meta.get("processed_points") or meta.get("target_points") or 0)
                loyalty_id = str(meta.get("loyalty_transaction_id") or "")
                if not loyalty_id:
                    issues.append({
                        "severity": "error",
                        "code": "processed_without_loyalty_transaction",
                        "transaction_id": str(tx.id),
                        "account_id": str(account.id),
                        "message": "Processed bridge без loyalty_transaction_id",
                    })
                elif loyalty_id not in existing_loyalty_ids:
                    issues.append({
                        "severity": "error",
                        "code": "missing_loyalty_transaction",
                        "transaction_id": str(tx.id),
                        "account_id": str(account.id),
                        "message": "loyalty_transaction_id не найден в loyalty_transactions",
                    })
                onec_status = meta.get("onec_sync_status")
                if onec_status == "ready_for_1c":
                    onec_ready_count += 1
                    issues.append({
                        "severity": "info",
                        "code": "onec_ready_for_manual_sync",
                        "transaction_id": str(tx.id),
                        "account_id": str(account.id),
                        "message": "1С payload готов, автосинк выключен или ожидает ручной обработки",
                    })
                if onec_status in {"failed", "missing_discount_card"}:
                    onec_failed_count += 1
                    issues.append({
                        "severity": "warn",
                        "code": f"onec_{onec_status}",
                        "transaction_id": str(tx.id),
                        "account_id": str(account.id),
                        "message": str(meta.get("onec_sync_error") or onec_status),
                    })
            if tx.status in {"failed", "canceled"} and amount_abs > 0 and "refunded_glm" not in meta:
                issues.append({
                    "severity": "warn",
                    "code": "closed_without_refund_marker",
                    "transaction_id": str(tx.id),
                    "account_id": str(account.id),
                    "message": "Closed bridge без refunded_glm marker",
                })

        for tx, account in points_to_glm_rows:
            meta = tx.meta if isinstance(tx.meta, dict) else {}
            spend_status = meta.get("onec_spend_sync_status")
            auto_transfer = meta.get("ton_auto_transfer") if isinstance(meta.get("ton_auto_transfer"), dict) else {}
            ton_tx_hash = (
                str(meta.get("tx_hash") or "").strip()
                or str(auto_transfer.get("tx_hash") or "").strip()
                or str(meta.get("operator_tx_hash") or "").strip()
            )

            if tx.status == "pending":
                points_to_glm_pending_count += 1
                created_at = tx.created_at
                if created_at and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at and created_at < stale_before:
                    issues.append({
                        "severity": "warn",
                        "code": "stale_pending_points_to_glm",
                        "operation": "points_to_glm",
                        "transaction_id": str(tx.id),
                        "account_id": str(account.id),
                        "onec_document_id": meta.get("onec_spend_document_id"),
                        "ton_status": auto_transfer.get("status"),
                        "message": f"Pending points_to_glm старше {stale_hours} часов",
                    })
            elif tx.status == "processed":
                points_to_glm_processed_count += 1
            elif tx.status == "canceled":
                points_to_glm_canceled_count += 1

            if auto_transfer.get("status") == "sent_waiting_settlement":
                ton_sent_waiting_count += 1
                issues.append({
                    "severity": "warn",
                    "code": "ton_sent_waiting_settlement",
                    "operation": "points_to_glm",
                    "transaction_id": str(tx.id),
                    "account_id": str(account.id),
                    "onec_document_id": meta.get("onec_spend_document_id"),
                    "ton_tx_hash": ton_tx_hash or None,
                    "ton_status": auto_transfer.get("status"),
                    "message": "GLM transfer уже отправлен, но claim еще ждет TON settlement/retry",
                })

            if tx.status == "processed" and not ton_tx_hash:
                ton_processed_without_tx_count += 1
                issues.append({
                    "severity": "error",
                    "code": "processed_points_to_glm_without_ton_tx",
                    "operation": "points_to_glm",
                    "transaction_id": str(tx.id),
                    "account_id": str(account.id),
                    "onec_document_id": meta.get("onec_spend_document_id"),
                    "message": "Processed points_to_glm без TON tx hash",
                })

            if tx.status == "processed" and spend_status not in {"success", "manual_spend_document_recorded", "legacy_manual_testnet_mint"}:
                onec_spend_failed_count += 1
                issues.append({
                    "severity": "error",
                    "code": "processed_points_to_glm_without_1c_spend",
                    "operation": "points_to_glm",
                    "transaction_id": str(tx.id),
                    "account_id": str(account.id),
                    "onec_document_id": meta.get("onec_spend_document_id"),
                    "ton_tx_hash": ton_tx_hash or None,
                    "message": "Processed points_to_glm без подтвержденного 1С-списания",
                })

            if tx.status == "canceled" and auto_transfer.get("status") in {"sent", "sent_waiting_settlement", "settled"}:
                issues.append({
                    "severity": "error",
                    "code": "canceled_points_to_glm_with_ton_transfer",
                    "operation": "points_to_glm",
                    "transaction_id": str(tx.id),
                    "account_id": str(account.id),
                    "onec_document_id": meta.get("onec_spend_document_id"),
                    "ton_tx_hash": ton_tx_hash or None,
                    "ton_status": auto_transfer.get("status"),
                    "message": "Заявка отменена, но TON transfer уже был отправлен или подтвержден",
                })

            if tx.status in {"failed", "canceled"} and spend_status == "success":
                cancel_status = str(meta.get("onec_cancel_spend_sync_status") or "")
                if cancel_status != "success":
                    onec_cancel_spend_failed_count += 1
                    issues.append({
                        "severity": "error",
                        "code": "closed_points_to_glm_without_1c_spend_unpost",
                        "operation": "points_to_glm",
                        "transaction_id": str(tx.id),
                        "account_id": str(account.id),
                        "onec_document_id": meta.get("onec_spend_document_id"),
                        "message": "Заявка закрыта/отменена после успешного 1С-списания, но исходный 1С-документ не распроведен",
                    })

            if tx.status in {"superseded", "failed", "canceled"}:
                continue

            if spend_status in {None, "", "ready_for_1c_spend"}:
                onec_spend_ready_count += 1
                issues.append({
                    "severity": "info",
                    "code": "onec_spend_ready_for_manual_sync",
                    "operation": "points_to_glm",
                    "transaction_id": str(tx.id),
                    "account_id": str(account.id),
                    "message": "1С payload списания баллов готов или еще не создан; требуется retry после включения spend sync",
                })
            if spend_status in {"failed", "missing_discount_card", "posted_without_balance_change"}:
                onec_spend_failed_count += 1
                issues.append({
                    "severity": "warn",
                    "code": f"onec_spend_{spend_status}",
                    "operation": "points_to_glm",
                    "transaction_id": str(tx.id),
                    "account_id": str(account.id),
                    "onec_document_id": meta.get("onec_spend_document_id"),
                    "message": str(meta.get("onec_spend_sync_error") or spend_status),
                })

        for account in negative_accounts:
            issues.append({
                "severity": "error",
                "code": "negative_glm_account_balance",
                "account_id": str(account.id),
                "message": f"Negative GLM balance={int(account.balance or 0)}, hold={int(account.hold_balance or 0)}",
            })

        tx_meta_by_id = {
            str(tx.id): tx.meta if isinstance(tx.meta, dict) else {}
            for tx, _account in [*bridge_rows, *points_to_glm_rows]
        }
        visible_issues = []
        for issue in issues:
            tx_id = str(issue.get("transaction_id") or "")
            issue_code = str(issue.get("code") or "")
            meta = tx_meta_by_id.get(tx_id) if tx_id else None
            reviewed_codes = set(meta.get("bridge_reconciliation_reviewed_codes") or []) if isinstance(meta, dict) else set()
            if issue_code and issue_code in reviewed_codes:
                continue
            visible_issues.append(issue)

        return {
            "generated_at": now.isoformat(),
            "stale_hours": stale_hours,
            "bridge_operations_source": "glame_token_bridge_operations",
            "checked_bridge_operations": len(bridge_operation_rows),
            "bridge_operations_total": int(bridge_operation_total or 0),
            "bridge_operations_missing_domain_count": int(bridge_operation_missing_domain_count or 0),
            "bridge_operations_stale_pending_count": bridge_operation_stale_pending_count,
            "bridge_operations_consistency_issue_count": bridge_operation_consistency_issue_count,
            "bridge_operations_by_direction": bridge_operation_by_direction,
            "bridge_operations_by_status": bridge_operation_by_status,
            "checked_bridge_transactions": len(bridge_rows),
            "checked_points_to_glm_transactions": points_to_glm_checked_count,
            "checked_total_transactions": len(bridge_rows) + points_to_glm_checked_count,
            "pending_count": pending_count,
            "pending_reserved_glm": pending_reserved_glm,
            "processed_count": processed_count,
            "processed_points": processed_points,
            "points_to_glm_pending_count": points_to_glm_pending_count,
            "points_to_glm_processed_count": points_to_glm_processed_count,
            "points_to_glm_canceled_count": points_to_glm_canceled_count,
            "ton_sent_waiting_count": ton_sent_waiting_count,
            "ton_processed_without_tx_count": ton_processed_without_tx_count,
            "onec_ready_count": onec_ready_count,
            "onec_failed_count": onec_failed_count,
            "onec_spend_ready_count": onec_spend_ready_count,
            "onec_spend_failed_count": onec_spend_failed_count,
            "onec_cancel_spend_failed_count": onec_cancel_spend_failed_count,
            "negative_accounts_count": len(negative_accounts),
            "issues_count": len(visible_issues),
            "issues": visible_issues[:200],
        }

    async def list_daily_audit_hashes(self, *, limit: int = 30) -> list[GlameTokenDailyAuditHash]:
        return (
            await self.db.execute(
                select(GlameTokenDailyAuditHash)
                .where(GlameTokenDailyAuditHash.token_code == GLAME_TOKEN_CODE)
                .order_by(desc(GlameTokenDailyAuditHash.audit_date))
                .limit(limit)
            )
        ).scalars().all()

    async def generate_daily_audit_hash(
        self,
        *,
        audit_date: date | None = None,
        admin_user_id: UUID | None = None,
    ) -> GlameTokenDailyAuditHash:
        target_date = audit_date or datetime.now(timezone.utc).date()
        day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        generated_at = datetime.now(timezone.utc)

        transactions = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.created_at >= day_start,
                    GlameTokenTransaction.created_at < day_end,
                )
                .order_by(GlameTokenTransaction.created_at.asc(), GlameTokenTransaction.id.asc())
            )
        ).scalars().all()
        accounts = (
            await self.db.execute(
                select(GlameTokenAccount)
                .where(GlameTokenAccount.token_code == GLAME_TOKEN_CODE)
                .order_by(GlameTokenAccount.id.asc())
            )
        ).scalars().all()
        previous = (
            await self.db.execute(
                select(GlameTokenDailyAuditHash)
                .where(
                    GlameTokenDailyAuditHash.token_code == GLAME_TOKEN_CODE,
                    GlameTokenDailyAuditHash.audit_date < target_date,
                )
                .order_by(desc(GlameTokenDailyAuditHash.audit_date))
                .limit(1)
            )
        ).scalar_one_or_none()

        transaction_records: list[dict[str, Any]] = []
        transaction_hashes: list[dict[str, str]] = []
        for tx in transactions:
            record = {
                "id": str(tx.id),
                "account_id": str(tx.account_id),
                "user_id": str(tx.user_id),
                "referral_member_id": str(tx.referral_member_id) if tx.referral_member_id else None,
                "referral_commission_id": str(tx.referral_commission_id) if tx.referral_commission_id else None,
                "type": tx.transaction_type,
                "status": tx.status,
                "amount": int(tx.amount or 0),
                "balance_after": int(tx.balance_after or 0),
                "hold_balance_after": int(tx.hold_balance_after or 0),
                "reason": tx.reason,
                "source": tx.source,
                "source_id": tx.source_id,
                "available_at": tx.available_at.isoformat() if tx.available_at else None,
                "expires_at": tx.expires_at.isoformat() if tx.expires_at else None,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
                "meta": tx.meta or {},
            }
            record_hash = self._audit_sha256(record)
            transaction_records.append(record)
            transaction_hashes.append({"id": str(tx.id), "hash": record_hash})

        account_records = [
            {
                "id": str(account.id),
                "user_id": str(account.user_id),
                "referral_member_id": str(account.referral_member_id) if account.referral_member_id else None,
                "status": account.status,
                "balance": int(account.balance or 0),
                "hold_balance": int(account.hold_balance or 0),
                "lifetime_earned": int(account.lifetime_earned or 0),
                "lifetime_burned": int(account.lifetime_burned or 0),
            }
            for account in accounts
        ]
        totals = {
            "accounts_count": len(account_records),
            "balance_total": sum(int(item["balance"] or 0) for item in account_records),
            "hold_total": sum(int(item["hold_balance"] or 0) for item in account_records),
            "lifetime_earned_total": sum(int(item["lifetime_earned"] or 0) for item in account_records),
            "lifetime_burned_total": sum(int(item["lifetime_burned"] or 0) for item in account_records),
            "transactions_count": len(transaction_records),
        }
        root_payload = {
            "schema": "glame_token_daily_audit_v1",
            "token_code": GLAME_TOKEN_CODE,
            "audit_date": target_date.isoformat(),
            "period": {"from": day_start.isoformat(), "to": day_end.isoformat()},
            "previous_root_hash": previous.root_hash if previous else None,
            "transactions": transaction_records,
            "accounts": account_records,
            "totals": totals,
        }
        root_hash = self._audit_sha256(root_payload)
        stored_payload = {
            "schema": root_payload["schema"],
            "period": root_payload["period"],
            "previous_audit_date": previous.audit_date.isoformat() if previous else None,
            "previous_root_hash": previous.root_hash if previous else None,
            "transaction_hashes": transaction_hashes,
            "account_hash": self._audit_sha256({"accounts": account_records}),
            "totals": totals,
            "generated_at": generated_at.isoformat(),
        }

        existing = (
            await self.db.execute(
                select(GlameTokenDailyAuditHash).where(
                    GlameTokenDailyAuditHash.token_code == GLAME_TOKEN_CODE,
                    GlameTokenDailyAuditHash.audit_date == target_date,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = GlameTokenDailyAuditHash(audit_date=target_date, token_code=GLAME_TOKEN_CODE)
            self.db.add(existing)

        existing.root_hash = root_hash
        existing.previous_root_hash = previous.root_hash if previous else None
        existing.transactions_count = totals["transactions_count"]
        existing.accounts_count = totals["accounts_count"]
        existing.balance_total = totals["balance_total"]
        existing.hold_total = totals["hold_total"]
        existing.lifetime_earned_total = totals["lifetime_earned_total"]
        existing.lifetime_burned_total = totals["lifetime_burned_total"]
        existing.payload = stored_payload
        existing.public_status = existing.public_status or "internal"
        existing.generated_by = admin_user_id
        existing.generated_at = generated_at
        existing.updated_at = generated_at
        flag_modified(existing, "payload")
        await self.db.flush()
        return existing

    async def repair_glm_bridge_onec_sync(
        self,
        *,
        bridge: GlameTokenTransaction,
        action: str,
        admin_user_id: UUID,
        onec_document_id: str | None = None,
        comment: str | None = None,
    ) -> GlameTokenTransaction:
        bridge = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(GlameTokenTransaction.id == bridge.id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if bridge is None:
            raise ValueError("Bridge transaction не найдена")
        if bridge.transaction_type != "bridge" or bridge.reason not in GLAME_GLM_TO_POINTS_BRIDGE_REASONS:
            raise ValueError("Транзакция не является GLM -> баллы bridge")
        if bridge.status != "processed":
            raise ValueError("Repair доступен только для processed bridge")
        if action not in {"retry_onec", "record_manual_document", "mark_reviewed"}:
            raise ValueError("Некорректное repair-действие")

        meta = bridge.meta if isinstance(bridge.meta, dict) else {}
        now = datetime.now(timezone.utc)
        next_meta = dict(meta)
        repair_event = {
            "action": action,
            "at": now.isoformat(),
            "admin_user_id": str(admin_user_id),
            "comment": (comment or "").strip() or None,
        }

        if action == "mark_reviewed":
            next_meta["repair_status"] = "reviewed"
            next_meta["repair_comment"] = (comment or "").strip() or None
        else:
            points = int(meta.get("processed_points") or meta.get("target_points") or 0)
            if points <= 0:
                raise ValueError("Не найдена сумма processed_points для repair")
            expires_raw = meta.get("loyalty_points_expires_at")
            try:
                expires_at = datetime.fromisoformat(str(expires_raw)) if expires_raw else now + timedelta(days=GLAME_LOYALTY_POINTS_FROM_GLM_EXPIRES_DAYS)
            except ValueError:
                expires_at = now + timedelta(days=GLAME_LOYALTY_POINTS_FROM_GLM_EXPIRES_DAYS)
            user = (
                await self.db.execute(select(User).where(User.id == bridge.user_id))
            ).scalar_one_or_none()
            if user is None:
                raise ValueError("Пользователь не найден")
            onec_result = await self._sync_glm_bridge_points_to_onec(
                bridge=bridge,
                user=user,
                points=points,
                expires_at=expires_at,
                manual_document_id=(onec_document_id or "").strip() if action == "record_manual_document" else None,
            )
            next_meta.update({
                "onec_document_id": onec_result.get("document_id") or next_meta.get("onec_document_id"),
                "onec_sync_status": onec_result.get("status"),
                "onec_sync_error": onec_result.get("error"),
                "onec_request_payload": onec_result.get("payload"),
                "onec_response_payload": onec_result.get("response"),
                "repair_status": "applied",
            })
            repair_event["onec_sync_status"] = onec_result.get("status")
            repair_event["onec_document_id"] = onec_result.get("document_id")

        next_meta["repair_history"] = [*(meta.get("repair_history") or []), repair_event][-20:]
        bridge.meta = next_meta
        flag_modified(bridge, "meta")
        await self.db.flush()
        return bridge

    async def repair_points_to_glm_spend_sync(
        self,
        *,
        transaction: GlameTokenTransaction,
        action: str,
        admin_user_id: UUID,
        onec_document_id: str | None = None,
        comment: str | None = None,
    ) -> GlameTokenTransaction:
        tx = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(GlameTokenTransaction.id == transaction.id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if tx is None:
            raise ValueError("GLM transaction не найдена")
        if tx.transaction_type not in {"claim", "conversion"} or tx.reason not in {"points_to_ton_bridge", "points_to_glm_bridge"}:
            raise ValueError("Транзакция не является points -> GLM bridge")
        if action not in {"retry_onec_spend", "record_manual_spend_document", "mark_reviewed"}:
            raise ValueError("Некорректное repair-действие")

        meta = tx.meta if isinstance(tx.meta, dict) else {}
        now = datetime.now(timezone.utc)
        next_meta = dict(meta)
        repair_event = {
            "action": action,
            "at": now.isoformat(),
            "admin_user_id": str(admin_user_id),
            "comment": (comment or "").strip() or None,
        }

        if action == "mark_reviewed":
            next_meta["onec_spend_repair_status"] = "reviewed"
            next_meta["onec_spend_repair_comment"] = (comment or "").strip() or None
        else:
            points = int(meta.get("points_converted") or abs(int(tx.amount or 0)))
            if points <= 0:
                raise ValueError("Не найдена сумма points_converted для repair")
            user = (
                await self.db.execute(select(User).where(User.id == tx.user_id))
            ).scalar_one_or_none()
            if user is None:
                raise ValueError("Пользователь не найден")
            onec_result = await self._sync_points_to_glm_spend_to_onec(
                bridge=tx,
                user=user,
                points=points,
                operation=str(meta.get("bridge_type") or tx.reason or "points_to_glm"),
                manual_document_id=(onec_document_id or "").strip() if action == "record_manual_spend_document" else None,
            )
            next_meta.update({
                "onec_spend_document_id": onec_result.get("document_id") or next_meta.get("onec_spend_document_id"),
                "onec_spend_sync_status": onec_result.get("status"),
                "onec_spend_sync_error": onec_result.get("error"),
                "onec_spend_request_payload": onec_result.get("payload"),
                "onec_spend_response_payload": onec_result.get("response"),
                "onec_spend_repair_status": "applied",
            })
            repair_event["onec_spend_sync_status"] = onec_result.get("status")
            repair_event["onec_spend_document_id"] = onec_result.get("document_id")

        next_meta["onec_spend_repair_history"] = [*(meta.get("onec_spend_repair_history") or []), repair_event][-20:]
        tx.meta = next_meta
        flag_modified(tx, "meta")
        await self.db.flush()
        return tx

    async def repair_points_to_glm_cancel_spend_sync(
        self,
        *,
        transaction_id: UUID,
        admin_user_id: UUID,
        comment: str | None = None,
    ) -> GlameTokenTransaction:
        tx = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(GlameTokenTransaction.id == transaction_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if tx is None:
            raise ValueError("GLM transaction не найдена")
        if tx.transaction_type not in {"claim", "conversion"} or tx.reason not in {"points_to_ton_bridge", "points_to_glm_bridge"}:
            raise ValueError("Транзакция не является points -> GLM bridge")
        if tx.status not in {"failed", "canceled"}:
            raise ValueError("Распроведение 1С-списания доступно только для failed/canceled points -> GLM")

        meta = tx.meta if isinstance(tx.meta, dict) else {}
        points = int(meta.get("points_converted") or abs(int(tx.amount or 0)))
        if points <= 0:
            raise ValueError("Не найдена сумма points_converted для распроведения")
        user = (
            await self.db.execute(select(User).where(User.id == tx.user_id))
        ).scalar_one_or_none()
        if user is None:
            raise ValueError("Пользователь не найден")

        onec_result = await self._sync_points_to_glm_refund_to_onec(
            claim=tx,
            user=user,
            points=points,
        )
        now = datetime.now(timezone.utc)
        repair_event = {
            "action": "cancel_onec_spend",
            "at": now.isoformat(),
            "admin_user_id": str(admin_user_id),
            "comment": (comment or "").strip() or None,
            "onec_cancel_spend_sync_status": onec_result.get("status"),
            "onec_cancel_spend_document_id": onec_result.get("document_id"),
        }
        tx.meta = {
            **meta,
            "onec_cancel_spend_document_id": onec_result.get("document_id") or meta.get("onec_cancel_spend_document_id"),
            "onec_cancel_spend_sync_status": onec_result.get("status"),
            "onec_cancel_spend_sync_error": onec_result.get("error"),
            "onec_cancel_spend_request_payload": onec_result.get("payload"),
            "onec_cancel_spend_response_payload": onec_result.get("response"),
            "onec_cancel_spend_repair_history": [*(meta.get("onec_cancel_spend_repair_history") or []), repair_event][-20:],
        }
        flag_modified(tx, "meta")
        await self.db.flush()
        return tx

    async def mark_points_to_glm_reconciliation_review(
        self,
        *,
        transaction_id: UUID,
        action: str,
        admin_user_id: UUID,
        issue_code: str | None = None,
        comment: str | None = None,
    ) -> GlameTokenTransaction:
        if action not in {"mark_legacy_manual", "mark_reviewed"}:
            raise ValueError("Некорректное reconciliation-действие")
        tx = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(GlameTokenTransaction.id == transaction_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if tx is None:
            raise ValueError("GLM transaction не найдена")
        if tx.transaction_type not in {"claim", "conversion"} or tx.reason not in {"points_to_ton_bridge", "points_to_glm_bridge"}:
            raise ValueError("Транзакция не является points -> GLM bridge")

        meta = tx.meta if isinstance(tx.meta, dict) else {}
        now = datetime.now(timezone.utc)
        event = {
            "action": action,
            "issue_code": (issue_code or "").strip() or None,
            "at": now.isoformat(),
            "admin_user_id": str(admin_user_id),
            "comment": (comment or "").strip() or None,
        }
        next_meta = dict(meta)
        if action == "mark_legacy_manual":
            next_meta["onec_spend_sync_status"] = "legacy_manual_testnet_mint"
            next_meta["onec_spend_repair_status"] = "legacy_manual_reviewed"
        else:
            next_meta["bridge_reconciliation_review_status"] = "reviewed"
            reviewed_codes = {
                str(item)
                for item in (meta.get("bridge_reconciliation_reviewed_codes") or [])
                if str(item).strip()
            }
            if (issue_code or "").strip():
                reviewed_codes.add((issue_code or "").strip())
            next_meta["bridge_reconciliation_reviewed_codes"] = sorted(reviewed_codes)
        next_meta["bridge_reconciliation_review_history"] = [
            *(meta.get("bridge_reconciliation_review_history") or []),
            event,
        ][-20:]
        tx.meta = next_meta
        flag_modified(tx, "meta")
        await self.db.flush()
        return tx

    async def update_claim_status(
        self,
        *,
        claim: GlameTokenTransaction,
        status: str,
        admin_user_id: UUID,
        tx_hash: str | None = None,
        comment: str | None = None,
    ) -> GlameTokenTransaction:
        claim = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(GlameTokenTransaction.id == claim.id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if claim is None:
            raise ValueError("GLM claim не найден")
        if claim.transaction_type != "claim":
            raise ValueError("Транзакция не является GLM claim")
        if claim.status != "pending":
            raise ValueError("Можно обработать только pending claim")
        if status not in {"processed", "failed", "canceled"}:
            raise ValueError("Некорректный статус GLM claim")
        if status == "processed" and not (tx_hash or "").strip():
            raise ValueError("Для статуса processed нужен TON tx hash. Используйте TON settlement или вставьте hash после реального treasury transfer.")

        account = await self._locked_account(claim.account_id)
        meta = claim.meta if isinstance(claim.meta, dict) else {}
        if (
            status == "processed"
            and claim.reason == "points_to_ton_bridge"
            and _env_bool("ONEC_GLM_BRIDGE_SPEND_REQUIRE_SUCCESS", "false")
        ):
            spend_status = str(meta.get("onec_spend_sync_status") or "")
            if spend_status not in {"success", "manual_spend_document_recorded"}:
                raise ValueError(
                    "Нельзя закрыть points -> GLM claim: 1C-списание баллов не подтверждено. "
                    "Выполните retry_onec_spend или record_manual_spend_document."
                )

        if status in {"failed", "canceled"}:
            if meta.get("debit_source") == "loyalty_points":
                refund_points = int(meta.get("points_converted") or claim.amount or 0)
                user = (
                    await self.db.execute(select(User).where(User.id == claim.user_id).with_for_update())
                ).scalar_one_or_none()
                if user is None:
                    raise ValueError("Пользователь не найден")
                user.loyalty_points = int(user.loyalty_points or 0) + refund_points
                refund_tx = LoyaltyTransaction(
                    user_id=claim.user_id,
                    transaction_type="earn",
                    points=refund_points,
                    balance_after=int(user.loyalty_points or 0),
                    reason="points_to_ton_refund",
                    description="Возврат баллов: TON bridge GLM не был обработан.",
                    source="crypto_glame",
                    source_id=f"{claim.source_id}:loyalty_refund",
                )
                self.db.add(refund_tx)
                await self.db.flush()
                onec_refund_result: dict[str, Any] | None = None
                if claim.reason == "points_to_ton_bridge":
                    onec_refund_result = await self._sync_points_to_glm_refund_to_onec(
                        claim=claim,
                        user=user,
                        points=refund_points,
                    )
                meta = {
                    **meta,
                    "refund_loyalty_transaction_id": str(refund_tx.id),
                    "refunded_points": refund_points,
                }
                if onec_refund_result is not None:
                    meta = {
                        **meta,
                        "onec_cancel_spend_document_id": onec_refund_result.get("document_id"),
                        "onec_cancel_spend_sync_status": onec_refund_result.get("status"),
                        "onec_cancel_spend_sync_error": onec_refund_result.get("error"),
                        "onec_cancel_spend_request_payload": onec_refund_result.get("payload"),
                        "onec_cancel_spend_response_payload": onec_refund_result.get("response"),
                    }
            else:
                account.balance = int(account.balance or 0) + int(claim.amount or 0)
        pending_claim = (account.meta or {}).get("pending_claim") if isinstance(account.meta, dict) else None
        source_matches = isinstance(pending_claim, dict) and pending_claim.get("transaction_source_id") == claim.source_id
        next_meta = dict(account.meta or {})
        if source_matches:
            next_meta.pop("pending_claim", None)
        account.meta = next_meta
        flag_modified(account, "meta")

        now = datetime.now(timezone.utc).isoformat()
        claim.status = status
        claim.balance_after = int(account.balance or 0)
        claim.hold_balance_after = int(account.hold_balance or 0)
        processed_meta = {
            **meta,
            "processed_at": now,
            "processed_by": str(admin_user_id),
            "tx_hash": (tx_hash or "").strip() or None,
            "admin_comment": (comment or "").strip() or None,
        }
        auto_transfer = processed_meta.get("ton_auto_transfer")
        if status == "processed" and isinstance(auto_transfer, dict):
            processed_meta["ton_auto_transfer"] = {
                **auto_transfer,
                "status": "settled",
                "settled_at": now,
                "tx_hash": (tx_hash or auto_transfer.get("tx_hash") or "").strip() or None,
            }
        claim.meta = processed_meta
        flag_modified(claim, "meta")
        await self.db.flush()
        await self.sync_bridge_operation(claim)
        return claim

    async def release_hold_to_balance(
        self,
        *,
        member: ReferralProgramMember,
        amount: int | None = None,
        admin_user_id: UUID | None = None,
        reason: str = "admin_release",
    ) -> GlameTokenTransaction:
        account = await self.get_or_create_account(user_id=member.user_id, referral_member_id=member.id)
        hold_balance = int(account.hold_balance or 0)
        release_amount = hold_balance if amount is None else int(amount)
        if release_amount <= 0:
            raise ValueError("Нет GLM в hold для перевода")
        if release_amount > hold_balance:
            raise ValueError("Нельзя перевести больше GLM, чем находится в hold")

        account.hold_balance = hold_balance - release_amount
        account.balance = int(account.balance or 0) + release_amount

        hold_rows = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(
                    GlameTokenTransaction.account_id == account.id,
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "earn",
                    GlameTokenTransaction.status == "hold",
                )
                .order_by(GlameTokenTransaction.created_at)
            )
        ).scalars().all()
        remaining = release_amount
        released_sources: list[str] = []
        for row in hold_rows:
            if remaining <= 0:
                break
            row_amount = int(row.amount or 0)
            if row_amount <= remaining:
                row.status = "available"
                row.balance_after = int(account.balance or 0)
                row.hold_balance_after = int(account.hold_balance or 0)
                row.meta = {
                    **(row.meta or {}),
                    "released_at": datetime.now(timezone.utc).isoformat(),
                    "released_by": str(admin_user_id) if admin_user_id else None,
                }
                flag_modified(row, "meta")
                remaining -= row_amount
                if row.source_id:
                    released_sources.append(row.source_id)

        tx = GlameTokenTransaction(
            account_id=account.id,
            user_id=member.user_id,
            referral_member_id=member.id,
            token_code=GLAME_TOKEN_CODE,
            transaction_type="release",
            status="available",
            amount=release_amount,
            balance_after=int(account.balance or 0),
            hold_balance_after=int(account.hold_balance or 0),
            reason=reason,
            description="Админский перевод GLM из hold в доступный баланс.",
            source="admin",
            source_id=f"glm_release:{account.id}:{uuid4()}",
            meta={
                "admin_user_id": str(admin_user_id) if admin_user_id else None,
                "released_sources": released_sources,
                "policy": "manual hold release for approved/test referral rewards",
            },
        )
        self.db.add(tx)
        await self.db.flush()
        return tx

    async def release_due_holds(
        self,
        *,
        limit: int = 500,
        admin_user_id: UUID | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        rows = (
            await self.db.execute(
                select(GlameTokenTransaction, GlameTokenAccount, ReferralCommission)
                .join(GlameTokenAccount, GlameTokenAccount.id == GlameTokenTransaction.account_id)
                .outerjoin(ReferralCommission, ReferralCommission.id == GlameTokenTransaction.referral_commission_id)
                .where(
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "earn",
                    GlameTokenTransaction.status == "hold",
                    GlameTokenTransaction.available_at.is_not(None),
                    GlameTokenTransaction.available_at <= now,
                )
                .order_by(GlameTokenTransaction.available_at.asc(), GlameTokenTransaction.created_at.asc())
                .limit(limit)
            )
        ).all()

        released_count = 0
        released_amount = 0
        skipped: list[str] = []
        release_ids: list[str] = []
        for earn_tx, account, commission in rows:
            amount = int(earn_tx.amount or 0)
            if amount <= 0 or int(account.hold_balance or 0) < amount:
                skipped.append(str(earn_tx.id))
                continue

            account.hold_balance = int(account.hold_balance or 0) - amount
            account.balance = int(account.balance or 0) + amount

            earn_tx.status = "available"
            earn_tx.balance_after = int(account.balance or 0)
            earn_tx.hold_balance_after = int(account.hold_balance or 0)
            earn_tx.meta = {
                **(earn_tx.meta or {}),
                "released_at": now.isoformat(),
                "released_by": str(admin_user_id) if admin_user_id else None,
                "release_mode": "due_hold_batch",
            }
            flag_modified(earn_tx, "meta")

            if commission is not None and commission.status == "hold":
                commission.status = "approved"
                commission.approved_at = now
                commission.meta = {
                    **(commission.meta or {}),
                    "glm_auto_released_at": now.isoformat(),
                    "glm_auto_released_by": str(admin_user_id) if admin_user_id else None,
                }
                flag_modified(commission, "meta")

            release_tx = GlameTokenTransaction(
                account_id=account.id,
                user_id=account.user_id,
                referral_member_id=account.referral_member_id,
                referral_commission_id=earn_tx.referral_commission_id,
                token_code=GLAME_TOKEN_CODE,
                transaction_type="release",
                status="available",
                amount=amount,
                balance_after=int(account.balance or 0),
                hold_balance_after=int(account.hold_balance or 0),
                reason="auto_hold_release",
                description="Автоматический перевод GLM из hold после истечения hold-периода.",
                source="admin_batch",
                source_id=f"glm_auto_release:{earn_tx.id}",
                meta={
                    "admin_user_id": str(admin_user_id) if admin_user_id else None,
                    "earn_transaction_id": str(earn_tx.id),
                    "released_at": now.isoformat(),
                    "policy": "release GLM hold when available_at is due",
                },
            )
            self.db.add(release_tx)
            await self.db.flush()

            released_count += 1
            released_amount += amount
            release_ids.append(str(release_tx.id))

        return {
            "released_count": released_count,
            "released_amount": released_amount,
            "skipped_count": len(skipped),
            "skipped_transaction_ids": skipped,
            "release_transaction_ids": release_ids,
        }

    async def adjust_available_balance(
        self,
        *,
        member: ReferralProgramMember,
        amount: int,
        direction: str,
        reason: str,
        admin_user_id: UUID,
        comment: str | None = None,
    ) -> GlameTokenTransaction:
        adjustment_amount = int(amount or 0)
        if adjustment_amount <= 0:
            raise ValueError("Сумма корректировки должна быть больше нуля")
        if direction not in {"credit", "debit"}:
            raise ValueError("Некорректное направление корректировки")
        normalized_reason = (reason or "").strip()
        if len(normalized_reason) < 5:
            raise ValueError("Укажите причину корректировки")

        account = await self.get_or_create_account(user_id=member.user_id, referral_member_id=member.id)
        signed_amount = adjustment_amount if direction == "credit" else -adjustment_amount
        next_balance = int(account.balance or 0) + signed_amount
        if next_balance < 0:
            raise ValueError("Нельзя списать больше доступного GLM balance")
        account.balance = next_balance

        now = datetime.now(timezone.utc)
        tx = GlameTokenTransaction(
            account_id=account.id,
            user_id=member.user_id,
            referral_member_id=member.id,
            token_code=GLAME_TOKEN_CODE,
            transaction_type="adjustment",
            status="available",
            amount=signed_amount,
            balance_after=int(account.balance or 0),
            hold_balance_after=int(account.hold_balance or 0),
            reason=normalized_reason[:100],
            description="Админская корректировка доступного GLM balance.",
            source="admin_adjustment",
            source_id=f"glm_adjustment:{account.id}:{uuid4()}",
            meta={
                "admin_user_id": str(admin_user_id),
                "direction": direction,
                "comment": (comment or "").strip() or None,
                "adjusted_at": now.isoformat(),
                "policy": "manual GLM balance adjustment with required reason",
            },
        )
        self.db.add(tx)
        await self.db.flush()
        return tx

    async def redeem_store_item(
        self,
        *,
        member: ReferralProgramMember,
        sku: str,
        delivery_note: str | None = None,
    ) -> GlameTokenTransaction:
        if GLAME_STORE_CHECKOUT_MODE != "platform_ledger":
            raise ValueError("GLM Store checkout через TON-перевод готовится; внутреннее списание GLM ledger отключено")
        store_items = await self.reward_store_items(only_active=True)
        item = next((entry for entry in store_items if entry["sku"] == sku), None)
        if item is None or item.get("status") not in {"available", "limited"}:
            raise ValueError("Товар GLM Store недоступен")
        price = int(item.get("price_glm") or 0)
        if price <= 0:
            raise ValueError("Некорректная цена GLM Store")
        quantity = item.get("quantity_available")
        if quantity is not None and int(quantity or 0) <= 0:
            raise ValueError("Товар закончился")

        account = await self.get_or_create_account(user_id=member.user_id, referral_member_id=member.id)
        account = await self._locked_account(account.id)
        if int(account.balance or 0) < price:
            raise ValueError("Недостаточно доступных GLM для покупки")
        await self._reserve_reward_store_item(sku)
        account.balance = int(account.balance or 0) - price
        account.lifetime_burned = int(account.lifetime_burned or 0) + price

        now = datetime.now(timezone.utc)
        tx = GlameTokenTransaction(
            account_id=account.id,
            user_id=member.user_id,
            referral_member_id=member.id,
            token_code=GLAME_TOKEN_CODE,
            transaction_type="redemption",
            status="pending_fulfillment",
            amount=-price,
            balance_after=int(account.balance or 0),
            hold_balance_after=int(account.hold_balance or 0),
            reason="glm_store_item",
            description=f"Покупка в GLM Store: {item['title']}",
            source="glm_store",
            source_id=f"glm_store:{account.id}:{sku}:{uuid4()}",
            meta={
                "sku": sku,
                "item": item,
                "price_glm": price,
                "delivery_note": (delivery_note or "").strip() or None,
                "redeemed_at": now.isoformat(),
                "fulfillment_status": "pending",
                "policy": "GLM-only goods, services, and access passes",
            },
        )
        self.db.add(tx)
        await self.db.flush()
        return tx

    async def request_store_item_ton_checkout(
        self,
        *,
        member: ReferralProgramMember,
        sku: str,
        wallet: dict[str, Any] | None = None,
        delivery_note: str | None = None,
    ) -> GlameTokenTransaction:
        store_items = await self.reward_store_items(only_active=True)
        item = next((entry for entry in store_items if entry["sku"] == sku), None)
        if item is None or item.get("status") not in {"available", "limited"}:
            raise ValueError("Товар GLM Store недоступен")
        price = int(item.get("price_glm") or 0)
        if price <= 0:
            raise ValueError("Некорректная цена GLM Store")
        quantity = item.get("quantity_available")
        if quantity is not None and int(quantity or 0) <= 0:
            raise ValueError("Товар закончился")

        account = await self.get_or_create_account(user_id=member.user_id, referral_member_id=member.id)
        account = await self._locked_account(account.id)

        existing_pending = (
            await self.db.execute(
                select(GlameTokenTransaction).where(
                    GlameTokenTransaction.account_id == account.id,
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "redemption",
                    GlameTokenTransaction.status == "pending_ton_payment",
                    GlameTokenTransaction.reason == "glm_store_item",
                )
            )
        ).scalar_one_or_none()
        if existing_pending is not None:
            raise ValueError("У вас уже есть pending GLM Store оплата")
        await self._reserve_reward_store_item(sku)

        now = datetime.now(timezone.utc)
        wallet = wallet or {}
        tx = GlameTokenTransaction(
            account_id=account.id,
            user_id=member.user_id,
            referral_member_id=member.id,
            token_code=GLAME_TOKEN_CODE,
            transaction_type="redemption",
            status="pending_ton_payment",
            amount=-price,
            balance_after=int(account.balance or 0),
            hold_balance_after=int(account.hold_balance or 0),
            reason="glm_store_item",
            description=f"Покупка в GLM Store ожидает TON-оплату: {item['title']}",
            source="glm_store",
            source_id=f"glm_store_ton:{account.id}:{sku}:{uuid4()}",
            meta={
                "sku": sku,
                "item": item,
                "payment_method": "ton_glm",
                "price_glm": price,
                "price_points": int(item.get("price_points") or 0) if item.get("price_points") is not None else None,
                "delivery_note": (delivery_note or "").strip() or None,
                "redeemed_at": now.isoformat(),
                "fulfillment_status": "waiting_for_payment",
                "ton_deposit_status": "waiting_for_deposit",
                "expected_ton_sender_address": wallet.get("address"),
                "wallet_app": wallet.get("wallet_app") or wallet.get("label"),
                "treasury_address": (os.getenv("TON_GLM_TREASURY_ADDRESS") or "").strip() or None,
                "policy": "GLM Store purchase paid by TON GLM deposit to treasury",
            },
        )
        self.db.add(tx)
        await self.db.flush()
        return tx

    async def redeem_store_item_with_points(
        self,
        *,
        member: ReferralProgramMember,
        sku: str,
        delivery_note: str | None = None,
    ) -> GlameTokenTransaction:
        store_items = await self.reward_store_items(only_active=True)
        item = next((entry for entry in store_items if entry["sku"] == sku), None)
        if item is None or item.get("status") not in {"available", "limited"}:
            raise ValueError("Товар Reward Store недоступен")
        price_points = int(item.get("price_points") or 0)
        if price_points <= 0:
            raise ValueError("Для этого товара не задана цена в баллах")
        quantity = item.get("quantity_available")
        if quantity is not None and int(quantity or 0) <= 0:
            raise ValueError("Товар закончился")

        user = (
            await self.db.execute(select(User).where(User.id == member.user_id).with_for_update())
        ).scalar_one_or_none()
        if user is None:
            raise ValueError("Пользователь не найден")
        if int(user.loyalty_points or 0) < price_points:
            raise ValueError("Недостаточно бонусных баллов для покупки")
        await self._reserve_reward_store_item(sku)

        account = await self.get_or_create_account(user_id=member.user_id, referral_member_id=member.id)
        account = await self._locked_account(account.id)
        user.loyalty_points = int(user.loyalty_points or 0) - price_points

        purchase_key = str(uuid4())
        loyalty_tx = LoyaltyTransaction(
            user_id=member.user_id,
            transaction_type="spend",
            points=-price_points,
            balance_after=int(user.loyalty_points or 0),
            reason="reward_store_points_item",
            description=f"Покупка в Reward Store за баллы: {item['title']}",
            source="reward_store",
            source_id=f"reward_store_points:{purchase_key}:loyalty",
        )
        self.db.add(loyalty_tx)
        await self.db.flush()

        now = datetime.now(timezone.utc)
        tx = GlameTokenTransaction(
            account_id=account.id,
            user_id=member.user_id,
            referral_member_id=member.id,
            token_code=GLAME_TOKEN_CODE,
            transaction_type="redemption",
            status="pending_fulfillment",
            amount=0,
            balance_after=int(account.balance or 0),
            hold_balance_after=int(account.hold_balance or 0),
            reason="reward_store_points_item",
            description=f"Покупка в Reward Store за баллы: {item['title']}",
            source="reward_store",
            source_id=f"reward_store_points:{account.id}:{sku}:{purchase_key}",
            meta={
                "sku": sku,
                "item": item,
                "payment_method": "loyalty_points",
                "price_points": price_points,
                "price_glm": int(item.get("price_glm") or 0) if item.get("price_glm") is not None else None,
                "loyalty_transaction_id": str(loyalty_tx.id),
                "delivery_note": (delivery_note or "").strip() or None,
                "redeemed_at": now.isoformat(),
                "fulfillment_status": "pending",
                "policy": "Reward Store purchase paid with 1C loyalty points",
            },
        )
        self.db.add(tx)
        await self.db.flush()

        onec_spend_result = await self._sync_points_to_glm_spend_to_onec(
            bridge=tx,
            user=user,
            points=price_points,
            operation="reward_store_points",
        )
        if (
            _env_bool("ONEC_REWARD_STORE_POINTS_REQUIRE_SUCCESS", "true")
            and onec_spend_result.get("status") != "success"
        ):
            raise ValueError(f"1C не подтвердил списание баллов: {onec_spend_result.get('error') or onec_spend_result.get('status')}")
        tx.meta = {
            **(tx.meta or {}),
            "onec_spend_document_id": onec_spend_result.get("document_id"),
            "onec_spend_sync_status": onec_spend_result.get("status"),
            "onec_spend_sync_error": onec_spend_result.get("error"),
            "onec_spend_request_payload": onec_spend_result.get("payload"),
            "onec_spend_response_payload": onec_spend_result.get("response"),
        }
        flag_modified(tx, "meta")
        await self.db.flush()
        return tx

    async def update_redemption_status(
        self,
        *,
        redemption: GlameTokenTransaction,
        status: str,
        admin_user_id: UUID,
        comment: str | None = None,
    ) -> GlameTokenTransaction:
        redemption = (
            await self.db.execute(
                select(GlameTokenTransaction)
                .where(GlameTokenTransaction.id == redemption.id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if redemption is None:
            raise ValueError("GLM redemption не найден")
        if redemption.transaction_type != "redemption":
            raise ValueError("Транзакция не является GLM redemption")
        if redemption.status != "pending_fulfillment":
            raise ValueError("Можно обработать только pending fulfillment")
        if status not in {"fulfilled", "canceled", "failed"}:
            raise ValueError("Некорректный статус GLM redemption")

        account = await self._locked_account(redemption.account_id)

        meta = redemption.meta if isinstance(redemption.meta, dict) else {}
        payment_method = str(meta.get("payment_method") or "").strip()
        platform_ledger_payment = payment_method in {"", "platform_ledger"}
        refund_amount = abs(int(redemption.amount or 0))
        refund_points = int(meta.get("price_points") or 0)
        now = datetime.now(timezone.utc)
        refunded_glm = refund_amount if status in {"canceled", "failed"} and platform_ledger_payment else 0
        ton_refund_required = bool(status in {"canceled", "failed"} and payment_method == "ton_glm" and refund_amount > 0)
        if refunded_glm > 0:
            account.balance = int(account.balance or 0) + refund_amount
            account.lifetime_burned = max(0, int(account.lifetime_burned or 0) - refund_amount)
        points_refund_payload: dict[str, Any] | None = None
        if status in {"canceled", "failed"} and payment_method == "loyalty_points" and refund_points > 0:
            user = (
                await self.db.execute(select(User).where(User.id == redemption.user_id).with_for_update())
            ).scalar_one_or_none()
            if user is None:
                raise ValueError("Пользователь для возврата баллов не найден")
            onec_refund_result = await self._sync_points_to_glm_refund_to_onec(
                claim=redemption,
                user=user,
                points=refund_points,
            )
            if (
                _env_bool("ONEC_REWARD_STORE_POINTS_REQUIRE_SUCCESS", "true")
                and onec_refund_result.get("status") != "success"
            ):
                raise ValueError(f"1C не подтвердил возврат баллов: {onec_refund_result.get('error') or onec_refund_result.get('status')}")
            user.loyalty_points = int(user.loyalty_points or 0) + refund_points
            loyalty_tx = LoyaltyTransaction(
                user_id=redemption.user_id,
                transaction_type="bonus",
                points=refund_points,
                balance_after=int(user.loyalty_points or 0),
                reason="reward_store_points_refund",
                description="Возврат баллов за отмененную покупку Reward Store.",
                source="reward_store",
                source_id=f"reward_store_points_refund:{redemption.id}",
                created_by=admin_user_id,
            )
            self.db.add(loyalty_tx)
            await self.db.flush()
            points_refund_payload = {
                "refunded_points": refund_points,
                "loyalty_transaction_id": str(loyalty_tx.id),
                "onec_refund_status": onec_refund_result.get("status"),
                "onec_refund_document_id": onec_refund_result.get("document_id"),
                "onec_refund_error": onec_refund_result.get("error"),
                "onec_refund_payload": onec_refund_result.get("payload"),
            }

        redemption.status = status
        redemption.balance_after = int(account.balance or 0)
        redemption.hold_balance_after = int(account.hold_balance or 0)
        redemption.meta = {
            **meta,
            "fulfillment_status": status,
            "fulfilled_at": now.isoformat() if status == "fulfilled" else None,
            "processed_at": now.isoformat(),
            "processed_by": str(admin_user_id),
            "admin_comment": (comment or "").strip() or None,
            "refunded_glm": refunded_glm,
            "ton_refund_required": ton_refund_required,
            "refunded_points": refund_points if points_refund_payload else 0,
            "points_refund": points_refund_payload,
        }
        flag_modified(redemption, "meta")
        await self.db.flush()
        return redemption

    async def cancel_referral_commission_glm(
        self,
        *,
        commission: ReferralCommission,
        admin_user_id: UUID,
        reason: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        if commission.status == "canceled":
            raise ValueError("Комиссия уже отменена")

        earn_tx = (
            await self.db.execute(
                select(GlameTokenTransaction).where(
                    GlameTokenTransaction.referral_commission_id == commission.id,
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "earn",
                    GlameTokenTransaction.status != "canceled",
                )
            )
        ).scalar_one_or_none()
        if earn_tx is None:
            now = datetime.now(timezone.utc)
            commission.status = "canceled"
            commission.meta = {
                **(commission.meta or {}),
                "canceled_at": now.isoformat(),
                "canceled_by": str(admin_user_id),
                "cancel_reason": reason,
                "cancel_comment": (comment or "").strip() or None,
                "glm_reversal_status": "no_glm_earn_transaction",
            }
            flag_modified(commission, "meta")
            await self.db.flush()
            return {"status": "canceled", "reversed_amount": 0, "reversal_status": "no_glm_earn_transaction"}

        account = (
            await self.db.execute(
                select(GlameTokenAccount).where(GlameTokenAccount.id == earn_tx.account_id)
            )
        ).scalar_one_or_none()
        if account is None:
            raise ValueError("GLM account не найден")

        now = datetime.now(timezone.utc)
        amount = max(0, int(earn_tx.amount or 0))
        reversed_amount = 0
        reversal_status = "none"
        needs_manual_recovery = False
        manual_recovery_amount = 0

        if amount > 0 and earn_tx.status == "hold":
            reverse_amount = min(amount, int(account.hold_balance or 0))
            account.hold_balance = int(account.hold_balance or 0) - reverse_amount
            account.lifetime_earned = max(0, int(account.lifetime_earned or 0) - reverse_amount)
            reversed_amount = reverse_amount
            reversal_status = "hold_reversed"
            if reverse_amount < amount:
                needs_manual_recovery = True
                manual_recovery_amount = amount - reverse_amount
        elif amount > 0 and earn_tx.status == "available":
            reverse_amount = min(amount, int(account.balance or 0))
            account.balance = int(account.balance or 0) - reverse_amount
            account.lifetime_earned = max(0, int(account.lifetime_earned or 0) - reverse_amount)
            reversed_amount = reverse_amount
            reversal_status = "balance_reversed"
            if reverse_amount < amount:
                needs_manual_recovery = True
                manual_recovery_amount = amount - reverse_amount
                reversal_status = "partial_balance_reversed"
        elif amount > 0:
            needs_manual_recovery = True
            manual_recovery_amount = amount
            reversal_status = f"manual_recovery_required_from_{earn_tx.status}"

        earn_tx.status = "canceled"
        earn_tx.balance_after = int(account.balance or 0)
        earn_tx.hold_balance_after = int(account.hold_balance or 0)
        earn_tx.meta = {
            **(earn_tx.meta or {}),
            "canceled_at": now.isoformat(),
            "canceled_by": str(admin_user_id),
            "cancel_reason": reason,
            "cancel_comment": (comment or "").strip() or None,
            "reversed_amount": reversed_amount,
            "manual_recovery_amount": manual_recovery_amount,
            "reversal_status": reversal_status,
        }
        flag_modified(earn_tx, "meta")

        commission.status = "canceled"
        commission.meta = {
            **(commission.meta or {}),
            "canceled_at": now.isoformat(),
            "canceled_by": str(admin_user_id),
            "cancel_reason": reason,
            "cancel_comment": (comment or "").strip() or None,
            "glm_earn_transaction_id": str(earn_tx.id),
            "glm_reversed_amount": reversed_amount,
            "glm_manual_recovery_amount": manual_recovery_amount,
            "glm_reversal_status": reversal_status,
        }
        flag_modified(commission, "meta")

        reversal_tx = GlameTokenTransaction(
            account_id=account.id,
            user_id=account.user_id,
            referral_member_id=account.referral_member_id,
            referral_commission_id=commission.id,
            token_code=GLAME_TOKEN_CODE,
            transaction_type="reversal",
            status="processed" if not needs_manual_recovery else "partial",
            amount=-reversed_amount,
            balance_after=int(account.balance or 0),
            hold_balance_after=int(account.hold_balance or 0),
            reason="referral_commission_canceled",
            description="Отмена GLM начисления из-за отмены/возврата реферальной покупки.",
            source="admin_refund",
            source_id=f"glm_reversal:{earn_tx.id}:{uuid4()}",
            meta={
                "admin_user_id": str(admin_user_id),
                "earn_transaction_id": str(earn_tx.id),
                "commission_id": str(commission.id),
                "reason": reason,
                "comment": (comment or "").strip() or None,
                "reversal_status": reversal_status,
                "manual_recovery_amount": manual_recovery_amount,
                "policy": "cancel referral GLM when source order/referral commission is canceled",
            },
        )
        self.db.add(reversal_tx)
        await self.db.flush()
        return {
            "status": "canceled",
            "reversed_amount": reversed_amount,
            "reversal_status": reversal_status,
            "manual_recovery_amount": manual_recovery_amount,
            "reversal_transaction_id": str(reversal_tx.id),
        }

    async def commission_glm_payload(self, commission_id: UUID) -> dict[str, Any]:
        tx = (
            await self.db.execute(
                select(GlameTokenTransaction).where(
                    GlameTokenTransaction.referral_commission_id == commission_id,
                    GlameTokenTransaction.token_code == GLAME_TOKEN_CODE,
                    GlameTokenTransaction.transaction_type == "earn",
                )
            )
        ).scalar_one_or_none()
        if tx is None:
            return {"amount": 0, "status": None, "available_at": None, "expires_at": None}
        return {
            "amount": int(tx.amount or 0),
            "status": tx.status,
            "available_at": tx.available_at.isoformat() if tx.available_at else None,
            "expires_at": tx.expires_at.isoformat() if tx.expires_at else None,
        }

    @staticmethod
    def calculate_referral_glm_amount(commission: ReferralCommission) -> int:
        rub_amount = Decimal(max(0, int(commission.amount_kopecks or 0))) / Decimal("100")
        return int(rub_amount)

    @classmethod
    def empty_summary(cls) -> dict[str, Any]:
        tier_payload = cls.tier_payload(0)
        return {
            **cls.policy_payload(),
            "account_id": None,
            "status": "not_created",
            "balance": 0,
            "hold_balance": 0,
            "lifetime_earned": 0,
            "lifetime_burned": 0,
            "earned_total": 0,
            "converted_total": 0,
            "claimable_balance": 0,
            "pending_claim_amount": 0,
            "pending_claim": False,
            "privilege_score": 0,
            **tier_payload,
        }

    @classmethod
    def tier_payload(cls, score: int) -> dict[str, Any]:
        tiers = cls.privilege_tiers()
        current = tiers[0]
        for tier in tiers:
            if score >= int(tier["threshold"]):
                current = tier
        next_tier = next((tier for tier in tiers if int(tier["threshold"]) > score), None)
        if next_tier:
            previous_threshold = int(current["threshold"])
            next_threshold = int(next_tier["threshold"])
            span = max(1, next_threshold - previous_threshold)
            progress = min(100, max(0, int(((score - previous_threshold) / span) * 100)))
            to_next = max(0, next_threshold - score)
        else:
            progress = 100
            to_next = 0
        return {
            "privilege_tier": current,
            "next_privilege_tier": next_tier,
            "privilege_progress_percent": progress,
            "privilege_to_next": to_next,
            "privilege_tier_basis": "lifetime_earned_minus_burned",
        }

    @staticmethod
    def privilege_tiers() -> list[dict[str, Any]]:
        return [dict(tier) for tier in GLAME_PRIVILEGE_TIERS]

    @staticmethod
    def checkout_category_limit_percent(category: str | None, tags: Any = None) -> int:
        haystack = " ".join(
            [
                str(category or ""),
                " ".join(str(tag) for tag in tags) if isinstance(tags, list) else str(tags or ""),
            ]
        ).lower()
        if any(word in haystack for word in ["clearance", "sale", "скид", "распрод", "остат"]):
            return 50
        if any(word in haystack for word in ["service", "сервис", "услуг", "stylist", "стилист"]):
            return 100
        if any(word in haystack for word in ["new", "нов", "fresh"]):
            return 10
        if any(word in haystack for word in ["vip", "privé", "prive"]):
            return 30
        return 20

    @classmethod
    def calculate_checkout_glm_limit(cls, lines: list[dict[str, Any]]) -> dict[str, Any]:
        max_discount_kopecks = 0
        line_limits: list[dict[str, Any]] = []
        for line in lines:
            line_total = max(0, int(line.get("line_total") or 0))
            limit_percent = cls.checkout_category_limit_percent(line.get("category"), line.get("tags"))
            limit_kopecks = int(line_total * limit_percent / 100)
            max_discount_kopecks += limit_kopecks
            line_limits.append(
                {
                    "product_id": str(line.get("product_id") or ""),
                    "category": line.get("category"),
                    "line_total": line_total,
                    "limit_percent": limit_percent,
                    "limit_kopecks": limit_kopecks,
                }
            )
        max_glm = max_discount_kopecks // 100
        return {
            "max_glm": max_glm,
            "max_discount_kopecks": max_glm * 100,
            "line_limits": line_limits,
            "policy": "category_limits",
        }

    @staticmethod
    def policy_payload() -> dict[str, Any]:
        ton_network = os.getenv("TON_NETWORK", "testnet").strip() or "testnet"
        jetton_master = (os.getenv("TON_GLM_JETTON_MASTER_ADDRESS") or "").strip() or None
        treasury_address = (os.getenv("TON_GLM_TREASURY_ADDRESS") or "").strip() or None
        metadata_url = (
            os.getenv("TON_GLM_METADATA_URL")
            or "https://partner.glamejewelry.ru/static/glm_policy/jetton-metadata.json"
        ).strip()
        onchain_status = "testnet_ready" if jetton_master else "draft_not_deployed"
        return {
            "token_code": GLAME_TOKEN_CODE,
            "token_name": GLAME_TOKEN_NAME,
            "decimals": GLAME_TOKEN_DECIMALS,
            "max_supply": GLAME_TOKEN_MAX_SUPPLY,
            "monthly_referral_emission_limit": GLAME_TOKEN_MONTHLY_REFERRAL_EMISSION_LIMIT,
            "referral_campaign": GlameTokenService.referral_campaign_payload(),
            "expiry_policy": {
                "mode": "perpetual",
                "description": "GLM не сгорает по календарю. Бонусные баллы 1С живут по текущим правилам и могут сгорать до перевода в GLM.",
            },
            "bonus_conversion_policy": {
                "enabled": True,
                "rate": "1 bonus point = 1 GLM",
                "min_points": GLAME_BONUS_CONVERSION_MIN,
                "max_points": GLAME_BONUS_CONVERSION_MAX,
                "monthly_limit": GLAME_BONUS_CONVERSION_MONTHLY_LIMIT,
                "bridge_type": "points_to_glm",
                "description": "Перевод сгорающих бонусных баллов 1С в GLM; в партнерском TON-сценарии заявка сразу уходит на вывод в кошелек.",
            },
            "loyalty_points_purchase_policy": {
                "enabled": True,
                "bridge_type": "buy_loyalty_points",
                "spread_percent": GLAME_LOYALTY_POINTS_PURCHASE_SPREAD_PERCENT,
                "min_points": GLAME_LOYALTY_POINTS_PURCHASE_MIN,
                "max_points": GLAME_LOYALTY_POINTS_PURCHASE_MAX,
                "points_expires_days": GLAME_LOYALTY_POINTS_FROM_GLM_EXPIRES_DAYS,
                "description": "Покупка баллов лояльности за GLM с product spread GLAME. Баллы начисляются после обработки bridge в 1С и живут по сроку действия баллов.",
            },
            "network": "off_chain_glame_ledger",
            "onchain_policy": {
                "network": ton_network,
                "standard": "TON Jetton / TEP-74 compatible",
                "status": onchain_status,
                "claim_mode": "operator_testnet_treasury_transfer" if jetton_master else "offchain_pending_claim_only",
                "treasury_distribution_mode": "transfer_existing_glm_from_treasury",
                "jetton_master_address": jetton_master,
                "treasury_address": treasury_address,
                "metadata_url": metadata_url,
                "metadata_status": "published",
                "mainnet_enabled": False,
                "mainnet_gate": "legal_security_treasury_approval_required",
                "implementation_package": "contracts/ton/glm-jetton",
                "disclaimer": "GLM withdrawal to TON is a controlled testnet/operator workflow until legal and security approval. It is not a public cash-out, buyback promise or bonus-to-token exchange duplicate.",
            },
            "transferable": False,
            "cash_out": False,
            "privilege_tiers": GlameTokenService.privilege_tiers(),
            "use_cases": [dict(item) for item in GLAME_USE_CASES],
            "acceptance_rules": [dict(item) for item in GLAME_ACCEPTANCE_RULES],
            "store_items": [],
            "store_checkout_policy": {
                "mode": GLAME_STORE_CHECKOUT_MODE,
                "enabled": GLAME_STORE_CHECKOUT_MODE == "platform_ledger",
                "next_mode": "ton_deposit_checkout",
                "description": (
                    "GLM Store должен списывать фактический GLM из TON-кошелька. "
                    "Внутренний ledger checkout отключен, чтобы не смешивать платформенный учет и on-chain GLM."
                    if GLAME_STORE_CHECKOUT_MODE != "platform_ledger"
                    else "Pilot checkout списывает внутренний GLM ledger. Использовать только для закрытого теста."
                ),
            },
            "internal_value_rule": {
                "value": "GLM can be bridged into loyalty points or redeemed in supported GLM services",
                "disclaimer": "GLM и баллы 1С - разные балансы. Для кассовой скидки GLM нужно перевести в баллы через bridge или использовать в поддерживаемом GLM-сервисе.",
                "max_discount_formula": "order_total * category_limit * customer_status_multiplier",
            },
            "reserve_lock_policy": {
                "mode": "db_row_lock",
                "description": "GLM account, bridge, claim and redemption rows are locked during reserve/process operations to reduce double-spend risk.",
            },
            "utility": [
                "referral_rewards",
                "club_status",
                "closed_drops",
                "future_glame_privileges",
            ],
            "risk_note": "GLM is a closed-loop GLAME utility reward, not an investment product.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def referral_campaign_payload() -> dict[str, Any]:
        raw_multiplier = os.getenv("GLM_REFERRAL_MULTIPLIER", "1").strip() or "1"
        try:
            multiplier = max(Decimal("1"), Decimal(raw_multiplier))
        except Exception:
            multiplier = Decimal("1")
        until_raw = (os.getenv("GLM_REFERRAL_CAMPAIGN_UNTIL") or "").strip()
        until_iso: str | None = None
        active_until_ok = True
        if until_raw:
            try:
                until_dt = datetime.fromisoformat(until_raw.replace("Z", "+00:00"))
                if until_dt.tzinfo is None:
                    until_dt = until_dt.replace(tzinfo=timezone.utc)
                until_iso = until_dt.isoformat()
                active_until_ok = until_dt >= datetime.now(timezone.utc)
            except Exception:
                active_until_ok = False
        active = multiplier > Decimal("1") and active_until_ok
        return {
            "active": bool(active),
            "code": os.getenv("GLM_REFERRAL_CAMPAIGN_CODE", "double_glm").strip() or "double_glm",
            "name": os.getenv("GLM_REFERRAL_CAMPAIGN_NAME", "Двойной GLM за рефералов").strip() or "Двойной GLM за рефералов",
            "multiplier": float(multiplier),
            "until": until_iso,
            "description": "Промо-множитель применяется к новым referral earn GLM, если кампания активна.",
        }
