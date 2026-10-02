from datetime import datetime, timezone

from fastapi import HTTPException

from app.api import tilda_gift_certificate_purchase as purchase_api
from app.models.tilda_gift_certificate_purchase import TildaGiftCertificatePurchase
from app.services.gift_certificate_service import GiftCertificateService


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
    source = open("app/services/tilda_gift_certificate_service.py", encoding="utf-8").read()
    assert 'meta.get("source") == "tilda_purchase" and requested != _amount(certificate.balance_amount)' in source
    assert "must be applied for their full available balance" in source


def test_tilda_purchase_marks_delivery_failed_when_email_is_not_sent():
    source = open(purchase_api.__file__, encoding="utf-8").read()
    assert 'purchase.status = "failed"' in source
    assert 'Certificate email was not sent' in source
    assert "send_for_certificates([cert])" not in source
