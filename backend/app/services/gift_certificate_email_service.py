from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import smtplib
from io import BytesIO
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image, ImageDraw, ImageFont

from app.models.gift_certificate import GiftCertificate
from app.models.app_setting import AppSetting
from app.services.sms_service import get_sms_service


logger = logging.getLogger(__name__)
EMAIL_SERVER_SETTING_KEY = "email_server_settings"
REPO_ROOT = Path(__file__).resolve().parents[3]
GIFT_CERTIFICATE_ASSET_DIR = REPO_ROOT / "mobile" / "glame_app" / "assets" / "images" / "gift_certificate"
FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


@dataclass(frozen=True)
class SMTPSettings:
    host: str
    port: int
    username: str | None
    password: str | None
    from_email: str
    from_name: str
    use_ssl: bool
    use_starttls: bool
    timeout: float


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _smtp_settings_from_env() -> SMTPSettings | None:
    host = (os.getenv("SMTP_HOST") or os.getenv("MAIL_HOST") or "").strip()
    from_email = (
        os.getenv("SMTP_FROM_EMAIL")
        or os.getenv("MAIL_FROM_EMAIL")
        or os.getenv("SMTP_USERNAME")
        or os.getenv("MAIL_USERNAME")
        or ""
    ).strip()
    if not host or not from_email:
        return None

    port = int(os.getenv("SMTP_PORT") or os.getenv("MAIL_PORT") or "587")
    use_ssl = _env_bool("SMTP_USE_SSL", port == 465)
    use_starttls = _env_bool("SMTP_USE_STARTTLS", not use_ssl)
    return SMTPSettings(
        host=host,
        port=port,
        username=(os.getenv("SMTP_USERNAME") or os.getenv("MAIL_USERNAME") or "").strip()
        or None,
        password=os.getenv("SMTP_PASSWORD") or os.getenv("MAIL_PASSWORD") or None,
        from_email=from_email,
        from_name=(
            os.getenv("SMTP_FROM_NAME")
            or os.getenv("MAIL_FROM_NAME")
            or "GLAME Jewelry"
        ).strip(),
        use_ssl=use_ssl,
        use_starttls=use_starttls,
        timeout=float(os.getenv("SMTP_TIMEOUT_SECONDS") or "20"),
    )


def _smtp_settings_from_payload(payload: dict, fallback: SMTPSettings | None = None) -> SMTPSettings | None:
    host = str(payload.get("host") or "").strip() or (fallback.host if fallback else "")
    from_email = str(payload.get("from_email") or "").strip() or (fallback.from_email if fallback else "")
    if not host or not from_email:
        return fallback

    port_raw = payload.get("port")
    try:
        port = int(port_raw if port_raw not in (None, "") else (fallback.port if fallback else 587))
    except (TypeError, ValueError):
        port = fallback.port if fallback else 587
    use_ssl = bool(payload.get("use_ssl")) if "use_ssl" in payload else (fallback.use_ssl if fallback else port == 465)
    use_starttls = (
        bool(payload.get("use_starttls"))
        if "use_starttls" in payload
        else (fallback.use_starttls if fallback else not use_ssl)
    )
    return SMTPSettings(
        host=host,
        port=port,
        username=str(payload.get("username") or "").strip() or (fallback.username if fallback else None),
        password=str(payload.get("password") or "") or (fallback.password if fallback else None),
        from_email=from_email,
        from_name=str(payload.get("from_name") or "").strip() or (fallback.from_name if fallback else "GLAME Jewelry"),
        use_ssl=use_ssl,
        use_starttls=use_starttls,
        timeout=float(payload.get("timeout") or (fallback.timeout if fallback else 20)),
    )


def public_smtp_settings(settings: SMTPSettings | None, *, source: str) -> dict:
    if not settings:
        return {
            "host": "",
            "port": 587,
            "username": "",
            "from_email": "",
            "from_name": "GLAME Jewelry",
            "use_ssl": False,
            "use_starttls": True,
            "password_set": False,
            "source": "default",
        }
    return {
        "host": settings.host,
        "port": settings.port,
        "username": settings.username or "",
        "from_email": settings.from_email,
        "from_name": settings.from_name,
        "use_ssl": settings.use_ssl,
        "use_starttls": settings.use_starttls,
        "password_set": bool(settings.password),
        "source": source,
    }


async def load_smtp_settings(db: AsyncSession | None) -> tuple[SMTPSettings | None, str]:
    fallback = _smtp_settings_from_env()
    if db is not None:
        try:
            row = (
                await db.execute(select(AppSetting).where(AppSetting.key == EMAIL_SERVER_SETTING_KEY))
            ).scalar_one_or_none()
            if row and row.value:
                payload = json.loads(str(row.value))
                if isinstance(payload, dict):
                    settings = _smtp_settings_from_payload(payload, fallback=fallback)
                    if settings:
                        return settings, "db"
        except Exception:
            logger.exception("Could not load email server settings from DB")
    if fallback:
        return fallback, "env"
    return None, "default"


def _format_rub(amount_kopeks: int) -> str:
    rub = max(0, int(amount_kopeks or 0)) // 100
    return f"{rub:,}".replace(",", " ") + " ₽"


def _format_date(value: datetime | None) -> str:
    if not value:
        return ""
    return value.astimezone(timezone.utc).strftime("%d.%m.%Y")


def _certificate_pin(cert: GiftCertificate) -> str | None:
    meta = cert.meta if isinstance(cert.meta, dict) else {}
    value = meta.get("delivery_pin")
    return str(value).strip() if value else None


def _sender_name(cert: GiftCertificate) -> str | None:
    meta = cert.meta if isinstance(cert.meta, dict) else {}
    value = meta.get("sender_name")
    return str(value).strip() if value else None


def _certificate_template_path(cert: GiftCertificate) -> Path:
    meta = cert.meta if isinstance(cert.meta, dict) else {}
    texture_id = str(meta.get("texture_id") or "").strip().lower()
    design = str(meta.get("design") if meta.get("design") is not None else "").strip()
    if "dark" in texture_id or design == "1":
        return GIFT_CERTIFICATE_ASSET_DIR / "glame_gift_certificate_template_02.png"
    return GIFT_CERTIFICATE_ASSET_DIR / "glame_gift_certificate_template_01.png"


def _certificate_amount_text(amount_kopeks: int) -> str:
    rub = max(0, int(amount_kopeks or 0)) // 100
    return f"{rub:,}".replace(",", " ")


def _render_certificate_image(cert: GiftCertificate) -> bytes | None:
    template_path = _certificate_template_path(cert)
    if not template_path.exists():
        return None

    with Image.open(template_path) as source:
        image = source.convert("RGBA")
    width, height = image.size
    meta = cert.meta if isinstance(cert.meta, dict) else {}
    texture_id = str(meta.get("texture_id") or "").strip().lower()
    design = str(meta.get("design") if meta.get("design") is not None else "").strip()
    is_dark = "dark" in texture_id or design == "1"

    amount = _certificate_amount_text(int(cert.nominal_amount or 0))
    draw = ImageDraw.Draw(image)
    font_size = max(118, int(height * 0.38))
    font = ImageFont.truetype(str(FONT_PATH), font_size) if FONT_PATH.exists() else ImageFont.load_default()
    color = (245, 246, 247, 255) if is_dark else (104, 104, 104, 255)

    bbox = draw.textbbox((0, 0), amount, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) / 2
    y = height * 0.27 - text_height * 0.12
    draw.text((x, y), amount, font=font, fill=color)

    output = BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


class GiftCertificateEmailService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def send_for_certificates(self, certificates: Iterable[GiftCertificate]) -> None:
        for cert in certificates:
            try:
                await self.send_gift_certificate(cert)
            except Exception as exc:
                self._remember_delivery_status(cert, "failed", error=str(exc))
                logger.exception("Could not send gift certificate email for %s", cert.id)
            try:
                await self.send_gift_certificate_sms(cert)
            except Exception as exc:
                self._remember_sms_delivery_status(cert, "failed", error=str(exc))
                logger.exception("Could not send gift certificate SMS for %s", cert.id)

    async def send_gift_certificate(self, cert: GiftCertificate) -> bool:
        recipient = str(cert.recipient_email or "").strip()
        if not recipient:
            self._remember_delivery_status(cert, "skipped", reason="recipient_email_empty")
            return False

        meta = cert.meta if isinstance(cert.meta, dict) else {}
        delivery = meta.get("email_delivery") if isinstance(meta.get("email_delivery"), dict) else {}
        if delivery.get("status") == "sent":
            return False

        settings, _source = await load_smtp_settings(self.db)
        if not settings:
            self._remember_delivery_status(cert, "failed", error="SMTP is not configured")
            logger.warning("SMTP is not configured; gift certificate email was not sent")
            return False

        message = self._build_message(settings, cert, recipient)
        await asyncio.to_thread(self._send_message, settings, message)
        self._remember_delivery_status(cert, "sent")
        return True

    async def send_gift_certificate_sms(self, cert: GiftCertificate) -> bool:
        phone = str(cert.recipient_phone or "").strip()
        if not phone:
            self._remember_sms_delivery_status(cert, "skipped", reason="recipient_phone_empty")
            return False

        meta = cert.meta if isinstance(cert.meta, dict) else {}
        delivery = meta.get("sms_delivery") if isinstance(meta.get("sms_delivery"), dict) else {}
        if delivery.get("status") == "sent":
            return False

        sms_service = get_sms_service()
        if not sms_service:
            self._remember_sms_delivery_status(cert, "failed", error="SMS service is not configured")
            logger.warning("SMS service is not configured; gift certificate SMS was not sent")
            return False

        pin = _certificate_pin(cert)
        nominal = _format_rub(int(cert.nominal_amount or 0))
        text = f"GLAME: podarochnyj sertifikat {nominal}. Seriya {cert.number}."
        if pin:
            text += f" PIN {pin}."
        text += " Pokazhite seriyu prodavcu ili vvedite v prilozhenii."

        response = await sms_service.send_sms(phone, text, sign=os.getenv("GIFT_CERTIFICATE_SMS_SIGN", "GLAME"))
        self._remember_sms_delivery_status(cert, "sent", response=response)
        return True

    async def send_test_email(self, recipient: str) -> bool:
        recipient = str(recipient or "").strip()
        if not recipient:
            raise ValueError("recipient email is required")
        settings, _source = await load_smtp_settings(self.db)
        if not settings:
            raise RuntimeError("SMTP is not configured")
        message = EmailMessage()
        message["Subject"] = "Тестовое письмо GLAME"
        message["From"] = formataddr((settings.from_name, settings.from_email))
        message["To"] = recipient
        message.set_content(
            "Это тестовое письмо из настроек почтового сервера GLAME.\n\nЕсли вы его получили, SMTP настроен корректно."
        )
        message.add_alternative(
            """<!doctype html><html><body style="font-family:Arial,sans-serif">
<h2>GLAME</h2>
<p>Это тестовое письмо из настроек почтового сервера.</p>
<p>Если вы его получили, SMTP настроен корректно.</p>
</body></html>""",
            subtype="html",
        )
        await asyncio.to_thread(self._send_message, settings, message)
        return True

    def _build_message(
        self,
        settings: SMTPSettings,
        cert: GiftCertificate,
        recipient: str,
    ) -> EmailMessage:
        nominal = _format_rub(int(cert.nominal_amount or 0))
        subject = f"Ваш подарочный сертификат GLAME на {nominal}"
        sender_name = _sender_name(cert)
        pin = _certificate_pin(cert)
        expires = _format_date(cert.expires_at)

        plain_lines = [
            "Здравствуйте!",
            "",
            "Вам подарили электронный сертификат GLAME.",
            f"Номинал: {nominal}",
            f"Серия: {cert.number}",
        ]
        if pin:
            plain_lines.append(f"PIN: {pin}")
        if expires:
            plain_lines.append(f"Действителен до: {expires}")
        if sender_name:
            plain_lines.extend(["", f"Отправитель: {sender_name}"])
        if cert.message:
            plain_lines.extend(["", str(cert.message).strip()])
        plain_lines.extend(
            [
                "",
                "Покажите серию сертификата продавцу в магазине или введите ее при оформлении заказа в приложении.",
                "",
                "GLAME Jewelry",
                "glamejewelry.ru",
            ]
        )

        certificate_image = _render_certificate_image(cert)
        image_cid = "glame-gift-certificate"
        html_body = self._build_html(
            cert,
            nominal=nominal,
            pin=pin,
            expires=expires,
            sender_name=sender_name,
            image_cid=image_cid if certificate_image else None,
        )

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((settings.from_name, settings.from_email))
        message["To"] = recipient
        message.set_content("\n".join(plain_lines))
        message.add_alternative(html_body, subtype="html")
        if certificate_image:
            html_part = message.get_payload()[-1]
            html_part.add_related(
                certificate_image,
                maintype="image",
                subtype="png",
                cid=f"<{image_cid}>",
                filename="glame-gift-certificate.png",
            )
        return message

    def _build_html(
        self,
        cert: GiftCertificate,
        *,
        nominal: str,
        pin: str | None,
        expires: str,
        sender_name: str | None,
        image_cid: str | None = None,
    ) -> str:
        message_html = ""
        if cert.message:
            message_html = (
                "<div style=\"margin-top:24px;padding:18px;border:1px solid #d8d8d8;\">"
                f"{html.escape(str(cert.message).strip()).replace(chr(10), '<br>')}"
                "</div>"
            )
        sender_html = f"<p><b>Отправитель:</b> {html.escape(sender_name)}</p>" if sender_name else ""
        pin_html = f"<p><b>PIN:</b> {html.escape(pin)}</p>" if pin else ""
        expires_html = f"<p><b>Действителен до:</b> {html.escape(expires)}</p>" if expires else ""
        image_html = (
            f'<img src="cid:{html.escape(image_cid)}" alt="Подарочный сертификат GLAME" '
            'style="display:block;width:100%;max-width:590px;height:auto;margin:0 0 22px 0;border:0;" />'
            if image_cid
            else ""
        )
        return f"""<!doctype html>
<html>
  <body style="margin:0;background:#111111;color:#f1f2f3;font-family:Arial,sans-serif;">
    <div style="max-width:640px;margin:0 auto;padding:32px 20px;">
      <div style="font-size:28px;letter-spacing:6px;margin-bottom:28px;">GLAME</div>
      <div style="background:#ffffff;color:#111111;padding:26px;">
        {image_html}
        <p style="font-size:18px;margin:22px 0 8px;"><b>Серия:</b> {html.escape(cert.number or "")}</p>
        {pin_html}
        {expires_html}
        {sender_html}
        {message_html}
        <p style="margin-top:28px;color:#555;line-height:1.5;">
          Покажите серию сертификата продавцу в магазине или введите ее при оформлении заказа в приложении.
        </p>
      </div>
      <p style="color:#aeb0b4;font-size:12px;line-height:1.5;margin-top:18px;">
        Сертификат не подлежит возврату и обмену. Подробные условия использования доступны в приложении GLAME.
      </p>
    </div>
  </body>
</html>"""

    def _send_message(self, settings: SMTPSettings, message: EmailMessage) -> None:
        smtp_cls = smtplib.SMTP_SSL if settings.use_ssl else smtplib.SMTP
        with smtp_cls(settings.host, settings.port, timeout=settings.timeout) as smtp:
            if settings.use_starttls and not settings.use_ssl:
                smtp.starttls()
            if settings.username and settings.password:
                smtp.login(settings.username, settings.password)
            smtp.send_message(message)

    def _remember_delivery_status(
        self,
        cert: GiftCertificate,
        status: str,
        *,
        error: str | None = None,
        reason: str | None = None,
    ) -> None:
        meta = dict(cert.meta or {})
        delivery: dict[str, str] = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if error:
            delivery["error"] = error[:500]
        if reason:
            delivery["reason"] = reason
        meta["email_delivery"] = delivery
        cert.meta = meta

    def _remember_sms_delivery_status(
        self,
        cert: GiftCertificate,
        status: str,
        *,
        error: str | None = None,
        reason: str | None = None,
        response: dict | None = None,
    ) -> None:
        meta = dict(cert.meta or {})
        delivery: dict[str, object] = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if error:
            delivery["error"] = error[:500]
        if reason:
            delivery["reason"] = reason
        if response:
            delivery["response"] = response
        meta["sms_delivery"] = delivery
        cert.meta = meta
