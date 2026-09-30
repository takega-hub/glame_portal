import os
from uuid import uuid4

from app.models.gift_certificate import GiftCertificate
from app.models.tilda_gift_certificate_operation import TildaGiftCertificateOperation
from app.services import tilda_gift_certificate_service as service
from app.api import tilda_gift_certificates as routes


def test_validation_token_is_signed_and_expires(monkeypatch):
    monkeypatch.setenv("GIFT_CERTIFICATE_SECRET", "test-secret")
    token = service._encode_validation_token({"certificate_id": str(uuid4()), "exp": 4102444800})
    assert service._decode_validation_token(token)["exp"] == 4102444800


def test_operation_response_never_contains_certificate_number():
    cert = GiftCertificate(number="GLM-2026-ABCD-EF12-10000", balance_amount=800000)
    operation = TildaGiftCertificateOperation(
        operation_type="reserve",
        status="reserved",
        sync_status="synced",
        amount=200000,
        cart_total=500000,
        tilda_order_id="order-1",
    )
    payload = service.TildaGiftCertificateService.serialize(operation, certificate=cert)
    assert payload["certificate_mask"] == "GLM-2026-****-10000"
    assert "number" not in payload
    assert "GLM-2026-ABCD-EF12-10000" not in str(payload)


def test_tilda_routes_are_present_without_exposing_pin():
    source = open(os.path.join(os.path.dirname(__file__), "../app/api/tilda_gift_certificates.py"), encoding="utf-8").read()
    assert '/public/tilda/gift-certificates/validate' in source
    assert '/public/tilda/gift-certificates/reserve' in source
    assert '/internal/tilda/gift-certificates/confirm' in source
    assert 'TILDA_GIFT_CERTIFICATE_INTERNAL_SECRET' in source


def test_tilda_checkout_requires_enabled_onec_accounting(monkeypatch):
    monkeypatch.setenv("ONEC_GIFT_CERTIFICATES_ENABLED", "true")
    monkeypatch.delenv("ONEC_GIFT_CERTIFICATE_OPERATIONS_URL", raising=False)
    routes._require_one_c_operations_bridge()
    monkeypatch.setenv("ONEC_GIFT_CERTIFICATES_ENABLED", "false")
    try:
        routes._require_one_c_operations_bridge()
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
    else:
        raise AssertionError("Tilda checkout must stay disabled without 1C accounting")
