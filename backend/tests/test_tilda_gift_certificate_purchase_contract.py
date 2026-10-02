import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import HTTPException

from app.api import tilda_gift_certificate_purchase as purchase_api
from app.models.gift_certificate import GiftCertificate
from app.models.tilda_gift_certificate_purchase import TildaGiftCertificatePurchase
from app.services.gift_certificate_service import GiftCertificateService
from app.services.tilda_gift_certificate_service import _require_full_tilda_purchase_redemption


def test_tilda_purchase_is_disabled_without_explicit_environment_flag(monkeypatch):
    monkeypatch.delenv("TILDA_GIFT_CERTIFICATE_PURCHASE_ENABLED", raising=False)
    assert purchase_api._enabled() is False
    monkeypatch.setenv("TILDA_GIFT_CERTIFICATE_PURCHASE_ENABLED", "true")
    assert purchase_api._enabled() is True


def test_tilda_purchase_receipt_uses_the_buyer_contact(monkeypatch):
    monkeypatch.setenv("TILDA_GIFT_CERTIFICATE_RECEIPT_VAT_CODE", "1")
    monkeypatch.setenv("TILDA_GIFT_CERTIFICATE_RECEIPT_PAYMENT_SUBJECT", "payment")
    monkeypatch.setenv("TILDA_GIFT_CERTIFICATE_RECEIPT_PAYMENT_MODE", "full_payment")
    certificate = TildaGiftCertificatePurchase(
        nominal_amount=300_000,
        buyer_contact={"email": "buyer@example.com"},
    )
    receipt = purchase_api._receipt(certificate)
    assert receipt["customer"] == {"email": "buyer@example.com"}
    assert receipt["items"][0]["amount"]["value"] == "3000.00"
    assert receipt["items"][0]["payment_subject"] == "payment"


def test_tilda_purchase_requires_receipt_settings(monkeypatch):
    monkeypatch.delenv("TILDA_GIFT_CERTIFICATE_RECEIPT_VAT_CODE", raising=False)
    certificate = TildaGiftCertificatePurchase(nominal_amount=300_000, buyer_contact={"phone": "+79990000000"})
    try:
        purchase_api._receipt(certificate)
    except HTTPException as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("Receipt settings must be required before payment creation")


def test_certificate_expiry_uses_calendar_months(monkeypatch):
    fixed_now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.gift_certificate_service._now", lambda: fixed_now)
    expiry = GiftCertificateService._expiry_date(expires_in_days=None, expires_in_months=6)
    assert expiry == datetime(2027, 2, 28, 12, 0, tzinfo=timezone.utc)


def test_tilda_purchase_reserve_rejects_partial_use():
    certificate = GiftCertificate(
        balance_amount=100_000,
        meta={"source": "tilda_purchase"},
    )
    try:
        _require_full_tilda_purchase_redemption(certificate, 50_000)
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("Partial use of a Tilda-purchased certificate must be rejected")

    _require_full_tilda_purchase_redemption(certificate, 100_000)
    _require_full_tilda_purchase_redemption(
        GiftCertificate(balance_amount=100_000, meta={"source": "platform"}),
        50_000,
    )


def test_tilda_purchase_marks_delivery_failed_when_email_is_not_sent(monkeypatch):
    purchase_id = uuid4()
    certificate_id = uuid4()
    purchase = TildaGiftCertificatePurchase(
        id=purchase_id,
        certificate_id=certificate_id,
        nominal_amount=300_000,
        status="pending_payment",
        delivery_mode="now",
    )
    certificate = GiftCertificate(
        id=certificate_id,
        status="pending",
        nominal_amount=300_000,
        balance_amount=0,
    )

    class FakeGiftCertificateService:
        def __init__(self, db):
            self.db = db

        async def ensure_onec_certificate_balance(self, cert, *, source):
            assert cert is certificate
            assert source == "tilda_purchase"

        def _add_tx(self, *args, **kwargs):
            return None

    class FakeGiftCertificateEmailService:
        def __init__(self, db):
            self.db = db

        async def send_gift_certificate(self, cert):
            assert cert is certificate
            return False

    async def run():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = purchase
        db.execute.return_value = result
        db.get.return_value = certificate
        yookassa = MagicMock()
        yookassa.get_payment = AsyncMock(
            return_value={
                "status": "succeeded",
                "paid": True,
                "metadata": {"purchase_id": str(purchase_id)},
                "amount": {"value": "3000.00", "currency": "RUB"},
            }
        )
        monkeypatch.setattr(purchase_api, "GiftCertificateService", FakeGiftCertificateService)
        monkeypatch.setattr(
            purchase_api,
            "GiftCertificateEmailService",
            FakeGiftCertificateEmailService,
        )

        handled = await purchase_api.process_purchase_payment(
            db,
            payment_id="payment-1",
            yookassa_service=yookassa,
        )
        return handled, db

    handled, db = asyncio.run(run())
    assert handled is True
    assert purchase.status == "failed"
    assert purchase.error == "Certificate email was not sent"
    assert purchase.sent_at is None
    assert certificate.status == "active"
    assert db.commit.await_count >= 1
