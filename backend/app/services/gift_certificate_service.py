from __future__ import annotations

import hashlib
import hmac
import logging
import os
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


def hash_certificate_pin(pin: str) -> str:
    secret = os.getenv("GIFT_CERTIFICATE_SECRET") or os.getenv("JWT_SECRET_KEY") or "glame-gift-secret"
    return hmac.new(secret.encode("utf-8"), str(pin).encode("utf-8"), hashlib.sha256).hexdigest()


def generate_certificate_number() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    part1 = "".join(secrets.choice(alphabet) for _ in range(4))
    part2 = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"GLM-{datetime.now(timezone.utc).year}-{part1}-{part2}"


def generate_certificate_pin() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


class GiftCertificateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_pending_certificate(
        self,
        *,
        buyer_user_id: UUID,
        recipient_user_id: Optional[UUID] = None,
        nominal_amount: int,
        order_id: UUID,
        recipient_name: Optional[str] = None,
        recipient_phone: Optional[str] = None,
        recipient_email: Optional[str] = None,
        message: Optional[str] = None,
        expires_in_days: int = 365,
        meta: Optional[dict[str, Any]] = None,
    ) -> tuple[GiftCertificate, str]:
        nominal = _rub(nominal_amount)
        if nominal <= 0:
            raise HTTPException(status_code=400, detail="Certificate nominal must be positive")

        pin = generate_certificate_pin()
        for _ in range(10):
            number = generate_certificate_number()
            exists = (
                await self.db.execute(select(GiftCertificate).where(GiftCertificate.number == number))
            ).scalar_one_or_none()
            if not exists:
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate certificate number")

        cert_meta = dict(meta or {})
        cert_meta.setdefault("delivery_pin", pin)
        onec_series = None
        onec_nomenclature = None
        if os.getenv("ONEC_GIFT_CERTIFICATES_ENABLED", "true").lower() not in {"0", "false", "no"}:
            try:
                async with OneCGiftCertificateService() as onec:
                    onec_nomenclature = await onec.find_gift_nomenclature_by_nominal(nominal)
                    if not onec_nomenclature:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Gift certificate nominal {nominal // 100} RUB is not configured in 1C",
                        )
                    onec_series = await onec.create_series(
                        certificate_number=number,
                        gift_nomenclature_ref=str(onec_nomenclature["Ref_Key"]),
                        sold=False,
                    )
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

        cert = GiftCertificate(
            number=number,
            pin_hash=hash_certificate_pin(pin),
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
            expires_at=_now() + timedelta(days=max(1, int(expires_in_days or 365))),
            meta=cert_meta or None,
        )
        self.db.add(cert)
        await self.db.flush()
        self._add_tx(cert, "issue_pending", 0, order_id=order_id, source="platform")
        return cert, pin

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
            await self._mark_onec_series_sold(cert, sold=True)
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
