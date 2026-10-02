from __future__ import annotations

import hashlib
import hmac
import logging
import os
from calendar import monthrange
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gift_certificate import GiftCertificate
from app.models.gift_certificate_transaction import GiftCertificateTransaction
from app.models.order import Order
from app.services.onec_gift_certificate_service import OneCGiftCertificateService


ACTIVE_STATUSES = {"active", "reserved"}
logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rub(amount_kopeks: int) -> int:
    return max(0, int(amount_kopeks or 0))


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def gift_certificate_amount_limits() -> dict[str, int]:
    min_amount = max(1, _env_int("GIFT_CERTIFICATE_MIN_AMOUNT", 100_000))
    max_amount = max(min_amount, _env_int("GIFT_CERTIFICATE_MAX_AMOUNT", 10_000_000))
    step = max(1, _env_int("GIFT_CERTIFICATE_AMOUNT_STEP", 100))
    return {
        "min_amount": min_amount,
        "max_amount": max_amount,
        "step": step,
    }


def validate_gift_certificate_nominal(amount_kopeks: int) -> int:
    nominal = _rub(amount_kopeks)
    limits = gift_certificate_amount_limits()
    if nominal < limits["min_amount"]:
        raise HTTPException(
            status_code=400,
            detail=f"Certificate nominal must be at least {limits['min_amount'] // 100} RUB",
        )
    if nominal > limits["max_amount"]:
        raise HTTPException(
            status_code=400,
            detail=f"Certificate nominal must be no more than {limits['max_amount'] // 100} RUB",
        )
    if nominal % limits["step"] != 0:
        step_rub = limits["step"] / 100
        raise HTTPException(
            status_code=400,
            detail=f"Certificate nominal must be a multiple of {step_rub:g} RUB",
        )
    return nominal


def hash_certificate_pin(pin: str) -> str:
    secret = os.getenv("GIFT_CERTIFICATE_SECRET") or os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError("GIFT_CERTIFICATE_SECRET or JWT_SECRET_KEY must be configured")
    return hmac.new(secret.encode("utf-8"), str(pin).encode("utf-8"), hashlib.sha256).hexdigest()


def generate_certificate_number(nominal_amount: int) -> str:
    """Generate a readable unique number ending with the nominal in whole RUB."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    part1 = "".join(secrets.choice(alphabet) for _ in range(4))
    part2 = "".join(secrets.choice(alphabet) for _ in range(4))
    nominal_rub = _rub(nominal_amount) // 100
    return f"GLM-{datetime.now(timezone.utc).year}-{part1}-{part2}-{nominal_rub}"


def generate_certificate_pin() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


class GiftCertificateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_program_certificate(
        self,
        *,
        recipient_user_id: UUID,
        nominal_amount: int,
        source: str,
        source_idempotency_key: str,
        recipient_name: Optional[str] = None,
        recipient_phone: Optional[str] = None,
        recipient_email: Optional[str] = None,
        message: Optional[str] = None,
        expires_in_days: int = 30,
        buyer_user_id: Optional[UUID] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> tuple[GiftCertificate, str, bool]:
        """Issue an active certificate from an internal CRM/loyalty program.

        Unlike purchased certificates this flow has no order/payment. It is
        idempotent by source key because daily CRM generators may run more than
        once for the same customer/birthday.
        """
        if not source_idempotency_key:
            raise HTTPException(status_code=400, detail="source_idempotency_key is required")

        existing = (
            await self.db.execute(
                select(GiftCertificate).where(
                    GiftCertificate.meta["source_idempotency_key"].as_string() == source_idempotency_key
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing_meta = existing.meta if isinstance(existing.meta, dict) else {}
            return existing, str(existing_meta.get("delivery_pin") or ""), False

        nominal = validate_gift_certificate_nominal(nominal_amount)
        pin = generate_certificate_pin()
        for _ in range(10):
            number = generate_certificate_number(nominal)
            exists = (
                await self.db.execute(select(GiftCertificate).where(GiftCertificate.number == number))
            ).scalar_one_or_none()
            if not exists:
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate certificate number")

        cert_meta = {
            **(meta or {}),
            "delivery_pin": pin,
            "source": source,
            "source_idempotency_key": source_idempotency_key,
            "program_certificate": True,
            "validity_days": max(1, int(expires_in_days or 30)),
        }
        if os.getenv("ONEC_GIFT_CERTIFICATES_ENABLED", "true").lower() in {"0", "false", "no"}:
            raise HTTPException(status_code=503, detail="CRM certificates require 1C gift certificate accounting")
        organization_ref = os.getenv("ONEC_GIFT_CERTIFICATE_ORGANIZATION_KEY")
        if not organization_ref:
            raise HTTPException(status_code=503, detail="ONEC_GIFT_CERTIFICATE_ORGANIZATION_KEY is not configured")
        try:
            async with OneCGiftCertificateService() as onec:
                onec_nomenclature = await onec.find_gift_nomenclature_by_nominal(nominal)
                onec_custom_nominal = False
                if not onec_nomenclature:
                    onec_nomenclature = await onec.find_arbitrary_gift_nomenclature()
                    onec_custom_nominal = bool(onec_nomenclature)
                if not onec_nomenclature:
                    raise RuntimeError(f"Gift certificate nominal {nominal // 100} RUB is not configured in 1C")
                onec_series = await onec.create_series(
                    certificate_number=number,
                    gift_nomenclature_ref=str(onec_nomenclature["Ref_Key"]),
                    sold=False,
                )
                series_ref = str(onec_series.get("Ref_Key") or "")
                if not series_ref:
                    raise RuntimeError("1C did not return the gift certificate series reference")
                cert_meta["onec_series_ref_key"] = series_ref
                cert_meta["onec_series_number"] = onec_series.get("Description") or number
                if onec_custom_nominal:
                    await onec.set_series_nominal(series_ref, nominal)
                issued_doc = await onec.issue_program_balance(
                    series_ref_key=series_ref,
                    gift_nomenclature_ref=str(onec_nomenclature["Ref_Key"]),
                    nominal_kopeks=nominal,
                    organization_ref_key=organization_ref,
                    certificate_number=number,
                )
                cert_meta["onec_balance_document_ref_key"] = issued_doc.get("Ref_Key")
                cert_meta["onec_gift_nomenclature_ref_key"] = onec_nomenclature.get("Ref_Key")
                cert_meta["onec_gift_nomenclature_name"] = onec_nomenclature.get("Description")
                cert_meta["onec_gift_nomenclature_article"] = onec_nomenclature.get("Артикул")
                cert_meta["onec_gift_nomenclature_nominal"] = onec_nomenclature.get("Номинал")
                cert_meta["onec_gift_nomenclature_arbitrary"] = bool(onec_nomenclature.get("ПроизвольныйНоминал"))
                if onec_custom_nominal:
                    cert_meta["custom_nominal"] = True
                    cert_meta["custom_nominal_amount"] = nominal
                cert_meta["onec_sync_status"] = "balance_posted"
        except Exception as exc:
            logger.exception("Не удалось начислить программный подарочный сертификат в 1С")
            raise HTTPException(status_code=502, detail=f"Could not activate program certificate in 1C: {exc}") from exc

        now = _now()
        cert = GiftCertificate(
            number=number,
            pin_hash=hash_certificate_pin(pin),
            status="active",
            currency="RUB",
            nominal_amount=nominal,
            balance_amount=nominal,
            reserved_amount=0,
            buyer_user_id=buyer_user_id or recipient_user_id,
            recipient_user_id=recipient_user_id,
            recipient_name=recipient_name,
            recipient_phone=recipient_phone,
            recipient_email=recipient_email,
            message=message,
            onec_certificate_id=cert_meta.get("onec_series_ref_key"),
            onec_sale_document_id=cert_meta.get("onec_balance_document_ref_key"),
            expires_at=now + timedelta(days=max(1, int(expires_in_days or 30))),
            issued_at=now,
            activated_at=now,
            meta=cert_meta,
        )
        self.db.add(cert)
        await self.db.flush()
        self._add_tx(
            cert,
            "program_issue",
            nominal,
            created_by=buyer_user_id,
            source=source,
            external_operation_id=source_idempotency_key,
            meta={"source": source, "source_idempotency_key": source_idempotency_key},
        )
        return cert, pin, True

    async def create_pending_certificate(
        self,
        *,
        buyer_user_id: Optional[UUID],
        recipient_user_id: Optional[UUID] = None,
        nominal_amount: int,
        order_id: Optional[UUID],
        recipient_name: Optional[str] = None,
        recipient_phone: Optional[str] = None,
        recipient_email: Optional[str] = None,
        message: Optional[str] = None,
        expires_in_days: Optional[int] = None,
        expires_in_months: Optional[int] = None,
        pin_required: bool = True,
        meta: Optional[dict[str, Any]] = None,
    ) -> tuple[GiftCertificate, Optional[str]]:
        nominal = validate_gift_certificate_nominal(nominal_amount)
        if os.getenv("ONEC_GIFT_CERTIFICATES_ENABLED", "true").lower() in {"0", "false", "no"}:
            raise HTTPException(status_code=503, detail="Electronic certificates require 1C gift certificate accounting")
        if not os.getenv("ONEC_GIFT_CERTIFICATE_ORGANIZATION_KEY"):
            raise HTTPException(status_code=503, detail="ONEC_GIFT_CERTIFICATE_ORGANIZATION_KEY is not configured")

        pin = generate_certificate_pin() if pin_required else None
        for _ in range(10):
            number = generate_certificate_number(nominal)
            exists = (
                await self.db.execute(select(GiftCertificate).where(GiftCertificate.number == number))
            ).scalar_one_or_none()
            if not exists:
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate certificate number")

        cert_meta = dict(meta or {})
        if pin:
            cert_meta.setdefault("delivery_pin", pin)
        onec_series = None
        onec_nomenclature = None
        onec_custom_nominal = False
        if os.getenv("ONEC_GIFT_CERTIFICATES_ENABLED", "true").lower() not in {"0", "false", "no"}:
            try:
                async with OneCGiftCertificateService() as onec:
                    onec_nomenclature = await onec.find_gift_nomenclature_by_nominal(nominal)
                    if not onec_nomenclature:
                        onec_nomenclature = await onec.find_arbitrary_gift_nomenclature()
                        onec_custom_nominal = bool(onec_nomenclature)
                    if not onec_nomenclature:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                f"Gift certificate nominal {nominal // 100} RUB is not configured in 1C "
                                "and arbitrary nominal gift certificate nomenclature was not found"
                            ),
                        )
                    onec_series = await onec.create_series(
                        certificate_number=number,
                        gift_nomenclature_ref=str(onec_nomenclature["Ref_Key"]),
                        sold=False,
                    )
                    if not onec_series or not onec_series.get("Ref_Key"):
                        raise RuntimeError("1C did not return the gift certificate series reference")
                    onec_series = await onec.set_series_nominal(str(onec_series["Ref_Key"]), nominal)
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception("Не удалось создать серию подарочного сертификата в 1С")
                raise HTTPException(status_code=502, detail=f"Could not create certificate series in 1C: {exc}")
        if onec_series:
            cert_meta["onec_series_ref_key"] = onec_series.get("Ref_Key")
            cert_meta["onec_series_number"] = onec_series.get("Description") or number
        if onec_nomenclature:
            cert_meta["onec_gift_nomenclature_ref_key"] = onec_nomenclature.get("Ref_Key")
            cert_meta["onec_gift_nomenclature_name"] = onec_nomenclature.get("Description")
            cert_meta["onec_gift_nomenclature_article"] = onec_nomenclature.get("Артикул")
            cert_meta["onec_gift_nomenclature_nominal"] = onec_nomenclature.get("Номинал")
            cert_meta["onec_gift_nomenclature_arbitrary"] = bool(
                onec_nomenclature.get("ПроизвольныйНоминал")
            )
        if onec_custom_nominal:
            cert_meta["custom_nominal"] = True
            cert_meta["custom_nominal_amount"] = nominal

        cert = GiftCertificate(
            number=number,
            pin_hash=hash_certificate_pin(pin) if pin else None,
            status="pending",
            currency="RUB",
            nominal_amount=nominal,
            balance_amount=0,
            reserved_amount=0,
            buyer_user_id=buyer_user_id,
            recipient_user_id=recipient_user_id,
            recipient_name=recipient_name,
            recipient_phone=recipient_phone,
            recipient_email=recipient_email,
            message=message,
            order_id=order_id,
            onec_certificate_id=str(onec_series.get("Ref_Key")) if onec_series and onec_series.get("Ref_Key") else None,
            expires_at=self._expiry_date(
                expires_in_days=expires_in_days,
                expires_in_months=expires_in_months,
            ),
            meta=cert_meta or None,
        )
        self.db.add(cert)
        await self.db.flush()
        self._add_tx(cert, "issue_pending", 0, order_id=order_id, source="platform")
        return cert, pin

    @staticmethod
    def _expiry_date(*, expires_in_days: Optional[int], expires_in_months: Optional[int]):
        now = _now()
        if expires_in_months:
            months = max(1, int(expires_in_months))
            month_index = now.month - 1 + months
            year = now.year + month_index // 12
            month = month_index % 12 + 1
            return now.replace(year=year, month=month, day=min(now.day, monthrange(year, month)[1]))
        if expires_in_days:
            return now + timedelta(days=max(1, int(expires_in_days)))
        return None

    async def activate_order_certificates(self, order_id: UUID, payment_id: Optional[UUID] = None) -> list[GiftCertificate]:
        rows = (
            await self.db.execute(
                select(GiftCertificate)
                .where(GiftCertificate.order_id == order_id)
                .where(GiftCertificate.status == "pending")
                .with_for_update()
            )
        ).scalars().all()
        activated: list[GiftCertificate] = []
        for cert in rows:
            await self.ensure_onec_certificate_balance(cert, source="purchase")
            cert.status = "active"
            cert.balance_amount = int(cert.nominal_amount or 0)
            cert.reserved_amount = 0
            cert.payment_id = payment_id
            cert.issued_at = _now()
            cert.activated_at = _now()
            self._add_tx(
                cert,
                "activation",
                int(cert.nominal_amount or 0),
                order_id=order_id,
                source="platform",
            )
            activated.append(cert)
        return activated

    async def ensure_onec_certificate_balance(self, cert: GiftCertificate, *, source: str) -> None:
        meta = cert.meta if isinstance(cert.meta, dict) else {}
        series_ref = cert.onec_certificate_id or meta.get("onec_series_ref_key")
        gift_ref = meta.get("onec_gift_nomenclature_ref_key")
        organization_ref = os.getenv("ONEC_GIFT_CERTIFICATE_ORGANIZATION_KEY")
        if not series_ref or not gift_ref or not organization_ref:
            raise HTTPException(status_code=503, detail="Certificate accounting references are missing in 1C")
        if os.getenv("ONEC_GIFT_CERTIFICATES_ENABLED", "true").lower() in {"0", "false", "no"}:
            raise HTTPException(status_code=503, detail="Electronic certificates require 1C gift certificate accounting")
        try:
            async with OneCGiftCertificateService() as onec:
                document = await onec.issue_program_balance(
                    series_ref_key=str(series_ref),
                    gift_nomenclature_ref=str(gift_ref),
                    nominal_kopeks=int(cert.nominal_amount),
                    organization_ref_key=organization_ref,
                    certificate_number=cert.number,
                    source=source,
                )
        except Exception as exc:
            logger.exception("Не удалось провести остаток сертификата %s в 1С", cert.number)
            raise HTTPException(status_code=502, detail=f"Could not activate certificate in 1C: {exc}") from exc
        next_meta = dict(meta)
        next_meta["onec_sync_status"] = "balance_posted"
        if document.get("Ref_Key"):
            next_meta["onec_balance_document_ref_key"] = document["Ref_Key"]
            cert.onec_sale_document_id = str(document["Ref_Key"])
        cert.meta = next_meta

    async def cancel_order_certificates(self, order_id: UUID) -> list[GiftCertificate]:
        rows = (
            await self.db.execute(
                select(GiftCertificate)
                .where(GiftCertificate.order_id == order_id)
                .where(GiftCertificate.status == "pending")
                .with_for_update()
            )
        ).scalars().all()
        for cert in rows:
            await self._mark_onec_series_sold(cert, sold=False)
            cert.status = "canceled"
            cert.canceled_at = _now()
            self._add_tx(cert, "cancel", 0, order_id=order_id, source="platform")
        return rows

    async def get_valid_certificate(
        self,
        *,
        number: str,
        pin: Optional[str] = None,
        lock: bool = False,
        require_pin: bool = False,
    ) -> GiftCertificate:
        normalized = self.normalize_number(number)
        stmt = select(GiftCertificate).where(GiftCertificate.number == normalized)
        if lock:
            stmt = stmt.with_for_update()
        cert = (await self.db.execute(stmt)).scalar_one_or_none()
        if not cert:
            raise HTTPException(status_code=404, detail="Certificate not found")
        if cert.pin_hash and require_pin and not str(pin or "").strip():
            raise HTTPException(status_code=403, detail="Certificate PIN is required")
        if cert.pin_hash and pin is not None and not hmac.compare_digest(cert.pin_hash, hash_certificate_pin(pin)):
            raise HTTPException(status_code=403, detail="Invalid certificate PIN")
        self._ensure_spendable(cert)
        return cert

    async def validate(self, *, number: str, pin: Optional[str] = None) -> dict[str, Any]:
        cert = await self.get_valid_certificate(number=number, pin=pin, lock=False, require_pin=True)
        return self.to_public_dict(cert, include_private=False)

    async def reserve_for_order(
        self,
        *,
        number: str,
        amount: int,
        order_id: UUID,
        pin: Optional[str] = None,
    ) -> GiftCertificate:
        cert = await self.get_valid_certificate(number=number, pin=pin, lock=True, require_pin=True)
        spend = min(_rub(amount), int(cert.balance_amount or 0))
        if spend <= 0:
            raise HTTPException(status_code=400, detail="Certificate has no available balance")
        cert.balance_amount = int(cert.balance_amount or 0) - spend
        cert.reserved_amount = int(cert.reserved_amount or 0) + spend
        cert.status = "reserved"
        self._add_tx(cert, "reserve", spend, order_id=order_id, source="platform")
        return cert

    async def redeem_reserved_for_order(self, order_id: UUID) -> list[GiftCertificate]:
        rows = (
            await self.db.execute(
                select(GiftCertificate)
                .where(GiftCertificate.reserved_amount > 0)
                .where(GiftCertificate.status == "reserved")
                .with_for_update()
            )
        ).scalars().all()
        redeemed: list[GiftCertificate] = []
        for cert in rows:
            amount = self._reserved_for_order_amount(cert, order_id)
            if amount <= 0:
                continue
            cert.reserved_amount = max(0, int(cert.reserved_amount or 0) - amount)
            if int(cert.reserved_amount or 0) > 0:
                cert.status = "reserved"
            elif int(cert.balance_amount or 0) <= 0:
                cert.status = "redeemed"
            else:
                cert.status = "active"
            self._add_tx(cert, "redeem", amount, order_id=order_id, source="platform")
            redeemed.append(cert)
        return redeemed

    async def release_reserved_for_order(self, order_id: UUID) -> list[GiftCertificate]:
        rows = (
            await self.db.execute(
                select(GiftCertificate)
                .where(GiftCertificate.reserved_amount > 0)
                .where(GiftCertificate.status == "reserved")
                .with_for_update()
            )
        ).scalars().all()
        released: list[GiftCertificate] = []
        for cert in rows:
            amount = self._reserved_for_order_amount(cert, order_id)
            if amount <= 0:
                continue
            cert.reserved_amount = max(0, int(cert.reserved_amount or 0) - amount)
            cert.balance_amount = int(cert.balance_amount or 0) + amount
            cert.status = "reserved" if int(cert.reserved_amount or 0) > 0 else "active"
            self._add_tx(cert, "release", amount, order_id=order_id, source="platform")
            released.append(cert)
        return released

    async def redeem_offline(
        self,
        *,
        number: str,
        amount: int,
        pin: Optional[str] = None,
        store_id: Optional[UUID] = None,
        created_by: Optional[UUID] = None,
        external_operation_id: Optional[str] = None,
        onec_document_id: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> GiftCertificate:
        if external_operation_id:
            existing_tx = (
                await self.db.execute(
                    select(GiftCertificateTransaction)
                    .where(GiftCertificateTransaction.source == "offline")
                    .where(GiftCertificateTransaction.external_operation_id == external_operation_id)
                )
            ).scalar_one_or_none()
            if existing_tx:
                raise HTTPException(status_code=409, detail="Certificate operation already processed")

        cert = await self.get_valid_certificate(number=number, pin=pin, lock=True)
        spend = min(_rub(amount), int(cert.balance_amount or 0))
        if spend <= 0:
            raise HTTPException(status_code=400, detail="Certificate has no available balance")
        cert.balance_amount = int(cert.balance_amount or 0) - spend
        cert.status = "redeemed" if int(cert.balance_amount or 0) <= 0 else "active"
        self._add_tx(
            cert,
            "redeem",
            spend,
            store_id=store_id,
            created_by=created_by,
            source="offline",
            external_operation_id=external_operation_id,
            onec_document_id=onec_document_id,
            meta=meta,
        )
        return cert

    async def create_order_certificate_payment_meta(self, order: Order) -> dict[str, Any]:
        meta = order.meta if isinstance(order.meta, dict) else {}
        gift = meta.get("gift_certificate_payment") if isinstance(meta.get("gift_certificate_payment"), dict) else {}
        return gift

    @staticmethod
    def normalize_number(number: str) -> str:
        return str(number or "").strip().upper().replace(" ", "")

    @staticmethod
    def to_public_dict(
        cert: GiftCertificate,
        *,
        include_private: bool = False,
        include_pin: bool = False,
    ) -> dict[str, Any]:
        meta = cert.meta if isinstance(cert.meta, dict) else {}
        data = {
            "id": str(cert.id),
            "number": cert.number,
            "series": cert.number,
            "onec_series_ref_key": cert.onec_certificate_id,
            "status": cert.status,
            "currency": cert.currency,
            "nominal_amount": int(cert.nominal_amount or 0),
            "balance_amount": int(cert.balance_amount or 0),
            "reserved_amount": int(cert.reserved_amount or 0),
            "recipient_name": cert.recipient_name,
            "recipient_phone": cert.recipient_phone,
            "recipient_email": cert.recipient_email,
            "message": cert.message,
            "order_id": str(cert.order_id) if cert.order_id else None,
            "expires_at": cert.expires_at.isoformat() if cert.expires_at else None,
            "activated_at": cert.activated_at.isoformat() if cert.activated_at else None,
            "created_at": cert.created_at.isoformat() if cert.created_at else None,
            "send_at": meta.get("send_at"),
            "sender_name": meta.get("sender_name"),
            "design": meta.get("design"),
            "accent": meta.get("accent"),
            "texture_id": meta.get("texture_id"),
        }
        if include_pin and meta.get("delivery_pin"):
            data["pin"] = meta.get("delivery_pin")
        if include_private:
            data["buyer_user_id"] = str(cert.buyer_user_id) if cert.buyer_user_id else None
            data["recipient_user_id"] = str(cert.recipient_user_id) if cert.recipient_user_id else None
            data["onec_certificate_id"] = cert.onec_certificate_id
            data["onec_sale_document_id"] = cert.onec_sale_document_id
            data["meta"] = meta
        return data

    async def _mark_onec_series_sold(self, cert: GiftCertificate, *, sold: bool) -> None:
        series_ref = cert.onec_certificate_id
        if not series_ref:
            meta = cert.meta if isinstance(cert.meta, dict) else {}
            series_ref = meta.get("onec_series_ref_key")
        if not series_ref:
            return
        if os.getenv("ONEC_GIFT_CERTIFICATES_ENABLED", "true").lower() in {"0", "false", "no"}:
            return
        try:
            async with OneCGiftCertificateService() as onec:
                await onec.mark_series_sold(str(series_ref), sold=sold)
        except Exception as exc:
            logger.exception("Не удалось обновить признак Продан у серии сертификата в 1С")
            raise HTTPException(status_code=502, detail=f"Could not update certificate series in 1C: {exc}")

    def _ensure_spendable(self, cert: GiftCertificate) -> None:
        if cert.status not in ACTIVE_STATUSES:
            raise HTTPException(status_code=400, detail="Certificate is not active")
        if cert.expires_at and cert.expires_at < _now():
            cert.status = "expired"
            raise HTTPException(status_code=400, detail="Certificate is expired")
        if int(cert.balance_amount or 0) <= 0:
            raise HTTPException(status_code=400, detail="Certificate has no available balance")

    def _reserved_for_order_amount(self, cert: GiftCertificate, order_id: UUID) -> int:
        meta = cert.meta if isinstance(cert.meta, dict) else {}
        reservations = meta.get("reservations") if isinstance(meta.get("reservations"), dict) else {}
        return int(reservations.get(str(order_id)) or 0)

    def _add_tx(
        self,
        cert: GiftCertificate,
        transaction_type: str,
        amount: int,
        *,
        order_id: Optional[UUID] = None,
        store_id: Optional[UUID] = None,
        created_by: Optional[UUID] = None,
        source: Optional[str] = None,
        external_operation_id: Optional[str] = None,
        onec_document_id: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> GiftCertificateTransaction:
        if transaction_type == "reserve" and order_id:
            cert_meta = dict(cert.meta or {})
            reservations = dict(cert_meta.get("reservations") or {})
            reservations[str(order_id)] = int(reservations.get(str(order_id)) or 0) + int(amount or 0)
            cert_meta["reservations"] = reservations
            cert.meta = cert_meta
        if transaction_type in {"redeem", "release"} and order_id:
            cert_meta = dict(cert.meta or {})
            reservations = dict(cert_meta.get("reservations") or {})
            current = int(reservations.get(str(order_id)) or 0)
            next_amount = max(0, current - int(amount or 0))
            if next_amount:
                reservations[str(order_id)] = next_amount
            else:
                reservations.pop(str(order_id), None)
            cert_meta["reservations"] = reservations
            cert.meta = cert_meta

        tx = GiftCertificateTransaction(
            certificate_id=cert.id,
            transaction_type=transaction_type,
            amount=int(amount or 0),
            balance_after=int(cert.balance_amount or 0),
            reserved_after=int(cert.reserved_amount or 0),
            order_id=order_id,
            store_id=store_id,
            created_by=created_by,
            source=source,
            external_operation_id=external_operation_id,
            onec_document_id=onec_document_id,
            meta=meta,
        )
        self.db.add(tx)
        return tx
