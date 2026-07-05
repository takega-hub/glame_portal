import asyncio
from datetime import datetime, timedelta, timezone

from app.models.gift_certificate import GiftCertificate
from app.services import gift_certificate_email_service as email_service
from app.services.gift_certificate_email_service import GiftCertificateEmailService


class FakeSMTP:
    sent_messages = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        FakeSMTP.sent_messages.append(message)


def test_send_gift_certificate_email_marks_sent(monkeypatch):
    FakeSMTP.sent_messages = []
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "mailer@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "gift@example.test")
    monkeypatch.setenv("SMTP_FROM_NAME", "GLAME Test")
    monkeypatch.setenv("SMTP_USE_SSL", "false")
    monkeypatch.setenv("SMTP_USE_STARTTLS", "true")
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)

    cert = GiftCertificate(
        number="GLM-2026-TEST-CERT",
        status="active",
        nominal_amount=1000000,
        balance_amount=1000000,
        recipient_email="recipient@example.test",
        recipient_name="Елена",
        message="С днем рождения!",
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        meta={"delivery_pin": "123456", "sender_name": "Анна"},
    )

    sent = asyncio.run(GiftCertificateEmailService(db=None).send_gift_certificate(cert))

    assert sent is True
    assert len(FakeSMTP.sent_messages) == 1
    message = FakeSMTP.sent_messages[0]
    assert message["To"] == "recipient@example.test"
    assert "GLM-2026-TEST-CERT" in message.get_body(preferencelist=("plain",)).get_content()
    assert cert.meta["email_delivery"]["status"] == "sent"


def test_send_gift_certificate_email_skips_without_recipient(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "gift@example.test")
    cert = GiftCertificate(
        number="GLM-2026-NOEMAIL",
        status="active",
        nominal_amount=500000,
        balance_amount=500000,
        meta={"delivery_pin": "111111"},
    )

    sent = asyncio.run(GiftCertificateEmailService(db=None).send_gift_certificate(cert))

    assert sent is False
    assert cert.meta["email_delivery"]["status"] == "skipped"
    assert cert.meta["email_delivery"]["reason"] == "recipient_email_empty"


def test_send_gift_certificate_sms_marks_sent(monkeypatch):
    sent = {}

    class FakeSMS:
        async def send_sms(self, number, text, sign="GLAME", date_send=None):
            sent["number"] = number
            sent["text"] = text
            sent["sign"] = sign
            return {"success": True, "data": {"id": 123}}

    monkeypatch.setattr(email_service, "get_sms_service", lambda: FakeSMS())
    cert = GiftCertificate(
        number="GLM-2026-SMS-CERT",
        status="active",
        nominal_amount=300000,
        balance_amount=300000,
        recipient_phone="79050275559",
        meta={"delivery_pin": "654321"},
    )

    result = asyncio.run(GiftCertificateEmailService(db=None).send_gift_certificate_sms(cert))

    assert result is True
    assert sent["number"] == "79050275559"
    assert "GLM-2026-SMS-CERT" in sent["text"]
    assert "654321" in sent["text"]
    assert cert.meta["sms_delivery"]["status"] == "sent"
