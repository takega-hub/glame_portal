from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gift_certificate import GiftCertificate
from app.models.tilda_gift_certificate_operation import TildaGiftCertificateOperation
from app.services.gift_certificate_service import GiftCertificateService
from app.services.onec_gift_certificate_service import OneCGiftCertificateService


logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _amount(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _token_secret() -> bytes:
    secret = os.getenv("GIFT_CERTIFICATE_SECRET") or os.getenv("JWT_SECRET_KEY")
    if not secret:
        # A missing secret must never result in predictable public tokens.
        raise HTTPException(status_code=503, detail="Gift certificate service is temporarily unavailable")
    return secret.encode("utf-8")


def _encode_validation_token(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_token_secret(), raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=") + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")


def _decode_validation_token(token: str) -> dict[str, Any]:
    try:
        encoded_payload, encoded_signature = str(token or "").split(".", 1)
        payload_bytes = base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4))
        signature = base64.urlsafe_b64decode(encoded_signature + "=" * (-len(encoded_signature) % 4))
        expected = hmac.new(_token_secret(), payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(payload_bytes.decode("utf-8"))
        if not isinstance(payload, dict) or int(payload.get("exp") or 0) < int(_now().timestamp()):
            raise ValueError("expired")
        return payload
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=410, detail="Certificate validation has expired")


def _mask(number: str) -> str:
    value = GiftCertificateService.normalize_number(number)
    if len(value) <= 8:
        return "*" * max(4, len(value))
    return f"{value[:9]}****-{value[-5:]}"


class TildaGiftCertificateService:
    """Protected checkout flow used by Tilda and the payment webhook bridge."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.certificates = GiftCertificateService(db)

    @staticmethod
    def reservation_ttl() -> timedelta:
        minutes = max(1, int(os.getenv("GIFT_CERTIFICATE_RESERVATION_TTL_MINUTES", "30")))
        return timedelta(minutes=minutes)

    async def validate(
        self,
        *,
        number: str,
        pin: Optional[str],
        cart_total: int,
        cart_fingerprint: str,
        items: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        total = _amount(cart_total)
        fingerprint = str(cart_fingerprint or "").strip()
        if total <= 0 or not fingerprint:
            raise HTTPException(status_code=422, detail="Invalid cart")

        certificate = await self._get_or_import_certificate(number)
        # A legacy 1C series has no PIN; a platform-issued certificate requires it.
        require_pin = bool(certificate.pin_hash)
        certificate = await self.certificates.get_valid_certificate(
            number=certificate.number, pin=pin, require_pin=require_pin
        )
        applicable = min(_amount(certificate.balance_amount), self._non_certificate_total(total, items))
        if applicable <= 0:
            raise HTTPException(status_code=422, detail="Certificate cannot be applied to this cart")

        expires_at = _now() + timedelta(minutes=5)
        token_payload = {
            "certificate_id": str(certificate.id),
            "cart_total": total,
            "cart_fingerprint": fingerprint,
            "applicable_amount": applicable,
            "nonce": secrets.token_urlsafe(16),
            "exp": int(expires_at.timestamp()),
        }
        token = _encode_validation_token(token_payload)
        operation = TildaGiftCertificateOperation(
            certificate_id=certificate.id,
            operation_type="validation",
            status="active",
            sync_status="synced",
            amount=applicable,
            cart_total=total,
            cart_fingerprint=fingerprint,
            validation_token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            reservation_expires_at=expires_at,
        )
        self.db.add(operation)
        await self.db.flush()

        return {
            "valid": True,
            "certificate_mask": _mask(certificate.number),
            "available_amount": _amount(certificate.balance_amount),
            "applicable_amount": applicable,
            "amount_due": max(0, total - applicable),
            "currency": "RUB",
            "validation_token": token,
            "validation_expires_at": expires_at.isoformat(),
        }

    async def reserve(
        self,
        *,
        validation_token: str,
        amount: int,
        tilda_order_id: str,
        cart_total: int,
        cart_fingerprint: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        order_id = str(tilda_order_id or "").strip()
        fingerprint = str(cart_fingerprint or "").strip()
        total = _amount(cart_total)
        requested = _amount(amount)
        if not order_id or not fingerprint or total <= 0 or requested <= 0:
            raise HTTPException(status_code=422, detail="Invalid reserve request")

        request_hash = _stable_hash(
            {
                "validation_token": validation_token,
                "amount": requested,
                "tilda_order_id": order_id,
                "cart_total": total,
                "cart_fingerprint": fingerprint,
            }
        )
        existing = await self._idempotent(idempotency_key, request_hash)
        if existing:
            if existing.original_operation_id:
                parent, certificate = await self._locked_operation(existing.original_operation_id, lock=False)
                return self.serialize(parent, certificate=certificate)
            return await self._serialize_existing(existing)
        existing_order = (
            await self.db.execute(
                select(TildaGiftCertificateOperation)
                .where(TildaGiftCertificateOperation.operation_type == "reserve")
                .where(TildaGiftCertificateOperation.tilda_order_id == order_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing_order:
            if existing_order.cart_total != total or existing_order.cart_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="Order reservation has different cart data")
            return self.serialize(existing_order)

        token_data = _decode_validation_token(validation_token)
        token_hash = hashlib.sha256(validation_token.encode("utf-8")).hexdigest()
        validation = (
            await self.db.execute(
                select(TildaGiftCertificateOperation)
                .where(TildaGiftCertificateOperation.operation_type == "validation")
                .where(TildaGiftCertificateOperation.validation_token_hash == token_hash)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if not validation or validation.status != "active" or validation.reservation_expires_at < _now():
            raise HTTPException(status_code=410, detail="Certificate validation has expired")
        if (
            str(validation.certificate_id) != str(token_data.get("certificate_id"))
            or validation.cart_total != total
            or validation.cart_fingerprint != fingerprint
        ):
            raise HTTPException(status_code=409, detail="Certificate validation does not match the cart")

        certificate = (
            await self.db.execute(
                select(GiftCertificate).where(GiftCertificate.id == validation.certificate_id).with_for_update()
            )
        ).scalar_one_or_none()
        if not certificate:
            raise HTTPException(status_code=404, detail="Certificate not found")
        self.certificates._ensure_spendable(certificate)
        maximum = min(
            _amount(certificate.balance_amount),
            _amount(token_data.get("applicable_amount")),
            self._non_certificate_total(total, None),
            requested,
        )
        if maximum <= 0:
            raise HTTPException(status_code=422, detail="Certificate has no available balance")

        certificate.balance_amount = _amount(certificate.balance_amount) - maximum
        certificate.reserved_amount = _amount(certificate.reserved_amount) + maximum
        certificate.status = "reserved"
        expires_at = _now() + self.reservation_ttl()
        operation = TildaGiftCertificateOperation(
            certificate_id=certificate.id,
            operation_type="reserve",
            status="reserved",
            sync_status="synced",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            tilda_order_id=order_id,
            amount=maximum,
            cart_total=total,
            cart_fingerprint=fingerprint,
            reservation_expires_at=expires_at,
        )
        validation.status = "consumed"
        self.db.add(operation)
        await self.db.flush()
        self.certificates._add_tx(
            certificate,
            "reserve",
            maximum,
            source="tilda",
            external_operation_id=str(operation.id),
            meta={"tilda_order_id": order_id, "reservation_expires_at": expires_at.isoformat()},
        )
        return self.serialize(operation, certificate=certificate)

    async def confirm(
        self,
        *,
        operation_id: UUID,
        tilda_order_id: str,
        payment_status: str,
        payment_id: Optional[str],
        order_amount: int,
        payment_amount: int,
        items: Optional[list[dict[str, Any]]],
        idempotency_key: str,
    ) -> dict[str, Any]:
        request_hash = _stable_hash(
            {
                "operation_id": str(operation_id),
                "tilda_order_id": tilda_order_id,
                "payment_status": payment_status,
                "payment_id": payment_id,
                "order_amount": _amount(order_amount),
                "payment_amount": _amount(payment_amount),
                "items": items or [],
            }
        )
        existing = await self._idempotent(idempotency_key, request_hash)
        if existing:
            if existing.original_operation_id:
                parent, certificate = await self._locked_operation(existing.original_operation_id, lock=False)
                return self.serialize(parent, certificate=certificate)
            return await self._serialize_existing(existing)
        operation, certificate = await self._locked_reservation(operation_id)
        if operation.tilda_order_id != str(tilda_order_id or "").strip():
            raise HTTPException(status_code=409, detail="Operation does not match the order")
        if operation.status == "confirmed":
            return self.serialize(operation, certificate=certificate)
        if operation.status != "reserved" or operation.reservation_expires_at < _now():
            raise HTTPException(status_code=410, detail="Reservation has expired")
        if str(payment_status).lower() != "succeeded":
            raise HTTPException(status_code=422, detail="Payment is not successful")
        if _amount(order_amount) != _amount(operation.cart_total) or _amount(payment_amount) != max(0, _amount(order_amount) - _amount(operation.amount)):
            raise HTTPException(status_code=409, detail="Payment amount does not match the reservation")
        if self._cart_contains_certificate(items):
            raise HTTPException(status_code=422, detail="Gift certificate cannot purchase a gift certificate")

        operation.status = "confirmed"
        operation.payment_id = str(payment_id or "") or None
        operation.last_sync_attempt_at = _now()
        certificate.reserved_amount = max(0, _amount(certificate.reserved_amount) - _amount(operation.amount))
        certificate.status = "reserved" if certificate.reserved_amount else ("redeemed" if not certificate.balance_amount else "active")
        self.certificates._add_tx(
            certificate,
            "redeem",
            _amount(operation.amount),
            source="tilda",
            external_operation_id=str(operation.id),
            meta={"tilda_order_id": operation.tilda_order_id, "payment_id": operation.payment_id},
        )
        self.db.add(
            TildaGiftCertificateOperation(
                certificate_id=certificate.id,
                operation_type="redeem",
                status="confirmed",
                sync_status="synced",
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                tilda_order_id=operation.tilda_order_id,
                payment_id=operation.payment_id,
                original_operation_id=operation.id,
                amount=operation.amount,
            )
        )
        await self._sync_or_mark_pending(operation, certificate, "redeem")
        return self.serialize(operation, certificate=certificate)

    async def release(
        self,
        *,
        operation_id: UUID,
        tilda_order_id: str,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        request_hash = _stable_hash(
            {"operation_id": str(operation_id), "tilda_order_id": tilda_order_id, "reason": reason}
        )
        existing = await self._idempotent(idempotency_key, request_hash)
        if existing:
            if existing.original_operation_id:
                parent, certificate = await self._locked_operation(existing.original_operation_id, lock=False)
                return self.serialize(parent, certificate=certificate)
            return await self._serialize_existing(existing)
        operation, certificate = await self._locked_reservation(operation_id)
        if operation.tilda_order_id != str(tilda_order_id or "").strip():
            raise HTTPException(status_code=409, detail="Operation does not match the order")
        if operation.status in {"released", "expired"}:
            return self.serialize(operation, certificate=certificate)
        if operation.status == "confirmed":
            raise HTTPException(status_code=409, detail="Confirmed operation cannot be released")
        if operation.status != "reserved":
            raise HTTPException(status_code=409, detail="Operation cannot be released")

        certificate.reserved_amount = max(0, _amount(certificate.reserved_amount) - _amount(operation.amount))
        certificate.balance_amount = _amount(certificate.balance_amount) + _amount(operation.amount)
        certificate.status = "reserved" if certificate.reserved_amount else "active"
        operation.status = "released" if reason != "reservation_expired" else "expired"
        operation.meta = {**(operation.meta or {}), "release_reason": reason}
        self.certificates._add_tx(
            certificate,
            "release",
            _amount(operation.amount),
            source="tilda",
            external_operation_id=str(operation.id),
            meta={"tilda_order_id": operation.tilda_order_id, "reason": reason},
        )
        self.db.add(
            TildaGiftCertificateOperation(
                certificate_id=certificate.id,
                operation_type="release",
                status=operation.status,
                sync_status="synced",
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                tilda_order_id=operation.tilda_order_id,
                original_operation_id=operation.id,
                amount=operation.amount,
                meta={"reason": reason},
            )
        )
        return self.serialize(operation, certificate=certificate)

    async def refund(
        self,
        *,
        original_operation_id: UUID,
        tilda_order_id: str,
        refund_id: str,
        amount: int,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        value = _amount(amount)
        if not refund_id or value <= 0:
            raise HTTPException(status_code=422, detail="Invalid refund request")
        request_hash = _stable_hash(
            {
                "original_operation_id": str(original_operation_id),
                "tilda_order_id": tilda_order_id,
                "refund_id": refund_id,
                "amount": value,
                "reason": reason,
            }
        )
        existing = await self._idempotent(idempotency_key, request_hash)
        if existing:
            return await self._serialize_existing(existing)
        duplicate = (
            await self.db.execute(
                select(TildaGiftCertificateOperation)
                .where(TildaGiftCertificateOperation.operation_type == "refund")
                .where(TildaGiftCertificateOperation.refund_id == refund_id)
            )
        ).scalar_one_or_none()
        if duplicate:
            return await self._serialize_existing(duplicate)

        original, certificate = await self._locked_operation(original_operation_id)
        if original.operation_type != "reserve" or original.status != "confirmed":
            raise HTTPException(status_code=409, detail="Original operation is not confirmed")
        if original.tilda_order_id != str(tilda_order_id or "").strip():
            raise HTTPException(status_code=409, detail="Operation does not match the order")
        # SQLAlchemy returns an iterator; calculating explicitly avoids DB-specific SUM handling.
        refund_rows = (
            await self.db.execute(
                select(TildaGiftCertificateOperation.amount)
                .where(TildaGiftCertificateOperation.operation_type == "refund")
                .where(TildaGiftCertificateOperation.original_operation_id == original.id)
                .where(TildaGiftCertificateOperation.status == "confirmed")
            )
        ).scalars().all()
        refunded = sum(_amount(row) for row in refund_rows)
        remaining = max(0, _amount(original.amount) - refunded)
        if value > remaining:
            raise HTTPException(status_code=422, detail="Refund amount exceeds redeemed amount")
        if value != remaining:
            raise HTTPException(status_code=422, detail="Partial certificate refunds are not enabled yet")
        if not str(original.onec_document_id or "").strip():
            raise HTTPException(status_code=409, detail="Original 1C certificate document is not available for cancellation")

        operation = TildaGiftCertificateOperation(
            certificate_id=certificate.id,
            operation_type="refund",
            status="pending_sync",
            sync_status="pending_sync",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            tilda_order_id=original.tilda_order_id,
            refund_id=refund_id,
            original_operation_id=original.id,
            amount=value,
            last_sync_attempt_at=_now(),
            meta={"reason": reason},
        )
        self.db.add(operation)
        await self.db.flush()
        try:
            await self._cancel_in_one_c(original, certificate)
        except Exception:
            operation.error = "1C synchronization is pending"
            return self.serialize(operation, certificate=certificate)

        certificate.balance_amount = _amount(certificate.balance_amount) + value
        certificate.status = "active" if not certificate.reserved_amount else "reserved"
        operation.status = "confirmed"
        operation.sync_status = "synced"
        operation.error = None
        self.certificates._add_tx(
            certificate,
            "refund",
            value,
            source="tilda",
            external_operation_id=str(operation.id),
            meta={"tilda_order_id": operation.tilda_order_id, "refund_id": refund_id, "reason": reason},
        )
        return self.serialize(operation, certificate=certificate)

    async def get_operation(self, operation_id: UUID) -> dict[str, Any]:
        operation, certificate = await self._locked_operation(operation_id, lock=False)
        return self.serialize(operation, certificate=certificate)

    async def release_expired_reservations(self) -> int:
        rows = (
            await self.db.execute(
                select(TildaGiftCertificateOperation)
                .where(TildaGiftCertificateOperation.operation_type == "reserve")
                .where(TildaGiftCertificateOperation.status == "reserved")
                .where(TildaGiftCertificateOperation.reservation_expires_at < _now())
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        released = 0
        for operation in rows:
            certificate = (
                await self.db.execute(
                    select(GiftCertificate).where(GiftCertificate.id == operation.certificate_id).with_for_update()
                )
            ).scalar_one_or_none()
            if not certificate:
                continue
            certificate.reserved_amount = max(0, _amount(certificate.reserved_amount) - _amount(operation.amount))
            certificate.balance_amount = _amount(certificate.balance_amount) + _amount(operation.amount)
            certificate.status = "reserved" if certificate.reserved_amount else "active"
            operation.status = "expired"
            operation.meta = {**(operation.meta or {}), "release_reason": "reservation_expired"}
            self.certificates._add_tx(
                certificate,
                "release",
                _amount(operation.amount),
                source="tilda",
                external_operation_id=str(operation.id),
                meta={"tilda_order_id": operation.tilda_order_id, "reason": "reservation_expired"},
            )
            released += 1
        return released

    async def retry_pending_sync(self, limit: int = 100) -> int:
        rows = (
            await self.db.execute(
                select(TildaGiftCertificateOperation)
                .where(TildaGiftCertificateOperation.sync_status == "pending_sync")
                # Direct OData retry is currently verified only for debits.
                # Refunds need a reversal of the original 1C document.
                .where(TildaGiftCertificateOperation.operation_type == "reserve")
                # Retrying an unknown 1C create can debit the certificate
                # twice after a network failure. Only retry a document whose
                # 1C reference was already persisted.
                .where(TildaGiftCertificateOperation.onec_document_id.is_not(None))
                .order_by(TildaGiftCertificateOperation.created_at)
                .limit(max(1, min(limit, 500)))
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        synced = 0
        for operation in rows:
            certificate = (
                await self.db.execute(
                    select(GiftCertificate).where(GiftCertificate.id == operation.certificate_id).with_for_update()
                )
            ).scalar_one_or_none()
            if not certificate:
                continue
            operation.last_sync_attempt_at = _now()
            try:
                await self._post_to_one_c(operation, certificate, "refund" if operation.operation_type == "refund" else "redeem")
            except Exception:
                operation.error = "1C synchronization is pending"
                continue
            operation.sync_status = "synced"
            operation.error = None
            if operation.operation_type == "refund" and operation.status != "confirmed":
                certificate.balance_amount = _amount(certificate.balance_amount) + _amount(operation.amount)
                certificate.status = "active" if not certificate.reserved_amount else "reserved"
                operation.status = "confirmed"
                self.certificates._add_tx(
                    certificate,
                    "refund",
                    _amount(operation.amount),
                    source="tilda",
                    external_operation_id=str(operation.id),
                    meta={"tilda_order_id": operation.tilda_order_id, "refund_id": operation.refund_id},
                )
            synced += 1
        return synced

    async def _get_or_import_certificate(self, number: str) -> GiftCertificate:
        normalized = GiftCertificateService.normalize_number(number)
        certificate = (
            await self.db.execute(select(GiftCertificate).where(GiftCertificate.number == normalized))
        ).scalar_one_or_none()
        if certificate:
            return certificate
        try:
            async with OneCGiftCertificateService() as onec:
                series = await onec.find_series_by_number(normalized)
                if not series or not bool(series.get("Продан")):
                    raise HTTPException(status_code=404, detail="Certificate not found")
                owner = series.get("Owner")
                owner_ref = owner.get("Ref_Key") if isinstance(owner, dict) else owner
                nomenclature = await onec.get_nomenclature(str(owner_ref or ""))
                balance_rub = await onec.get_series_balance(str(series.get("Ref_Key") or ""))
        except HTTPException:
            raise
        except Exception:
            logger.warning("1C did not answer while importing a certificate", exc_info=True)
            raise HTTPException(status_code=503, detail="Certificate service is temporarily unavailable")
        if not nomenclature or nomenclature.get("ТипНоменклатуры") != "ПодарочныйСертификат":
            raise HTTPException(status_code=404, detail="Certificate not found")
        nominal = _amount(float(nomenclature.get("Номинал") or 0) * 100)
        balance = _amount(round(balance_rub * 100))
        if nominal <= 0 and balance <= 0:
            raise HTTPException(status_code=422, detail="Certificate nominal is not configured")
        certificate = GiftCertificate(
            number=normalized,
            pin_hash=None,
            status="active" if balance > 0 else "redeemed",
            currency="RUB",
            nominal_amount=max(nominal, balance),
            balance_amount=balance,
            reserved_amount=0,
            onec_certificate_id=str(series.get("Ref_Key") or "") or None,
            expires_at=None,
            meta={
                "source": "onec",
                "onec_series_ref_key": series.get("Ref_Key"),
                "onec_series_number": series.get("Description"),
                "onec_gift_nomenclature_ref_key": nomenclature.get("Ref_Key"),
                "last_onec_sync_at": _now().isoformat(),
                "sync_status": "synced",
            },
        )
        self.db.add(certificate)
        await self.db.flush()
        self.certificates._add_tx(certificate, "import", 0, source="onec")
        return certificate

    async def _idempotent(self, key: str, request_hash: str) -> Optional[TildaGiftCertificateOperation]:
        if not str(key or "").strip():
            raise HTTPException(status_code=422, detail="Idempotency-Key is required")
        existing = (
            await self.db.execute(
                select(TildaGiftCertificateOperation)
                .where(TildaGiftCertificateOperation.idempotency_key == key)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing and existing.request_hash != request_hash:
            raise HTTPException(status_code=409, detail="Idempotency key was used with another request")
        return existing

    async def _locked_reservation(self, operation_id: UUID) -> tuple[TildaGiftCertificateOperation, GiftCertificate]:
        operation, certificate = await self._locked_operation(operation_id)
        if operation.operation_type != "reserve":
            raise HTTPException(status_code=404, detail="Reservation not found")
        return operation, certificate

    async def _serialize_existing(self, operation: TildaGiftCertificateOperation) -> dict[str, Any]:
        certificate = (
            await self.db.execute(select(GiftCertificate).where(GiftCertificate.id == operation.certificate_id))
        ).scalar_one_or_none()
        return self.serialize(operation, certificate=certificate)

    async def _locked_operation(
        self, operation_id: UUID, *, lock: bool = True
    ) -> tuple[TildaGiftCertificateOperation, GiftCertificate]:
        stmt = select(TildaGiftCertificateOperation).where(TildaGiftCertificateOperation.id == operation_id)
        if lock:
            stmt = stmt.with_for_update()
        operation = (await self.db.execute(stmt)).scalar_one_or_none()
        if not operation:
            raise HTTPException(status_code=404, detail="Certificate operation not found")
        cert_stmt = select(GiftCertificate).where(GiftCertificate.id == operation.certificate_id)
        if lock:
            cert_stmt = cert_stmt.with_for_update()
        certificate = (await self.db.execute(cert_stmt)).scalar_one_or_none()
        if not certificate:
            raise HTTPException(status_code=404, detail="Certificate not found")
        return operation, certificate

    async def _sync_or_mark_pending(
        self, operation: TildaGiftCertificateOperation, certificate: GiftCertificate, action: str
    ) -> None:
        try:
            await self._post_to_one_c(operation, certificate, action)
            operation.sync_status = "synced"
            operation.error = None
        except Exception:
            # Payment is already successful; do not cancel it because 1C is
            # unavailable. The scheduler retries the same operation ID.
            operation.sync_status = "pending_sync"
            operation.error = "1C synchronization is pending"

    async def _post_to_one_c(
        self, operation: TildaGiftCertificateOperation, certificate: GiftCertificate, action: str
    ) -> None:
        if os.getenv("ONEC_GIFT_CERTIFICATES_ENABLED", "true").lower() in {"0", "false", "no"}:
            raise RuntimeError("1C gift certificate integration is disabled")
        certificate_meta = certificate.meta if isinstance(certificate.meta, dict) else {}
        payload = {
            "operation_id": str(operation.id),
            "idempotency_key": str(operation.id),
            "type": action,
            "certificate_series_ref_key": certificate.onec_certificate_id,
            "gift_nomenclature_ref_key": certificate_meta.get("onec_gift_nomenclature_ref_key"),
            "certificate_number": certificate.number,
            "amount": _amount(operation.amount),
            "currency": "RUB",
            "tilda_order_id": operation.tilda_order_id,
            "payment_id": operation.payment_id,
            "refund_id": operation.refund_id,
            "onec_document_id": operation.onec_document_id,
        }
        async with OneCGiftCertificateService() as onec:
            response = await onec.post_certificate_operation(payload)
        operation.onec_document_id = str(response.get("document_id") or response.get("Ref_Key") or "") or None

    async def _cancel_in_one_c(
        self, original: TildaGiftCertificateOperation, certificate: GiftCertificate
    ) -> None:
        async with OneCGiftCertificateService() as onec:
            await onec.cancel_certificate_debit(
                original_operation_id=str(original.id),
                document_id=str(original.onec_document_id or ""),
                series_ref=str(certificate.onec_certificate_id or ""),
                amount_kopeks=_amount(original.amount),
            )

    @staticmethod
    def _cart_contains_certificate(items: Optional[list[dict[str, Any]]]) -> bool:
        return any(bool(item.get("is_gift_certificate")) for item in (items or []) if isinstance(item, dict))

    def _non_certificate_total(self, total: int, items: Optional[list[dict[str, Any]]]) -> int:
        if not items:
            return total
        blocked = sum(
            _amount(item.get("unit_price")) * max(1, _amount(item.get("quantity")))
            for item in items
            if isinstance(item, dict) and bool(item.get("is_gift_certificate"))
        )
        return max(0, total - blocked)

    @staticmethod
    def serialize(
        operation: TildaGiftCertificateOperation, *, certificate: Optional[GiftCertificate] = None
    ) -> dict[str, Any]:
        certificate_mask = _mask(certificate.number) if certificate else None
        total = _amount(operation.cart_total)
        amount_due = max(0, total - _amount(operation.amount)) if total else None
        return {
            "operation_id": str(operation.id),
            "type": "redeem" if operation.operation_type == "reserve" else operation.operation_type,
            "status": operation.status,
            "sync_status": operation.sync_status,
            "tilda_order_id": operation.tilda_order_id,
            "certificate_mask": certificate_mask,
            "applied_amount": _amount(operation.amount) if operation.operation_type == "reserve" else None,
            "redeemed_amount": _amount(operation.amount) if operation.status == "confirmed" and operation.operation_type == "reserve" else None,
            "amount": _amount(operation.amount),
            "amount_due": amount_due,
            "balance_amount": _amount(certificate.balance_amount) if certificate else None,
            "reservation_expires_at": operation.reservation_expires_at.isoformat() if operation.reservation_expires_at else None,
            "last_sync_attempt_at": operation.last_sync_attempt_at.isoformat() if operation.last_sync_attempt_at else None,
            "error": operation.error,
        }
