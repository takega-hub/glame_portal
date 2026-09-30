from fastapi import HTTPException

from app.api import tilda_gift_certificate_checkout as checkout


def test_checkout_uses_kopeks_and_only_charges_the_balance():
    assert checkout._rub(0) == "0.00"
    assert checkout._rub(3000) == "30.00"
    assert checkout._rub(1) == "0.01"


def test_checkout_refuses_unsafe_return_urls(monkeypatch):
    monkeypatch.setenv("TILDA_GIFT_CERTIFICATE_ALLOWED_ORIGINS", "https://glamejewelry.ru")
    assert checkout._validate_return_url("https://glamejewelry.ru/catalog") == "https://glamejewelry.ru/catalog"
    for url in ("http://glamejewelry.ru", "//glamejewelry.ru", "javascript:alert(1)"):
        try:
            checkout._validate_return_url(url)
        except HTTPException as exc:
            assert exc.status_code == 422
        else:
            raise AssertionError(f"Unsafe URL was accepted: {url}")


def test_hosted_checkout_contract_keeps_certificate_data_off_yookassa_and_tilda():
    source = open(checkout.__file__, encoding="utf-8").read()
    assert '/public/tilda/gift-certificates/checkout' in source
    assert 'certificate_operation_id' in source
    assert 'confirmation_url' in source
    assert 'pin:' not in source
    assert 'number:' not in source


def test_yookassa_webhook_finalizes_hosted_certificate_payment_once():
    from app.api import yookassa_webhook

    source = open(yookassa_webhook.__file__, encoding="utf-8").read()
    assert '_process_tilda_certificate_payment' in source
    assert 'yookassa:{payment_id}:succeeded' in source
    assert 'yookassa:{payment_id}:canceled' in source
    assert 'await yookassa_service.get_payment(payment_id)' in source
