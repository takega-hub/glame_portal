from __future__ import annotations

import asyncio
import html
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Iterable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_arrival_subscription import ProductArrivalSubscription
from app.models.product_stock import ProductStock
from app.services.gift_certificate_email_service import SMTPSettings, load_smtp_settings

logger = logging.getLogger(__name__)


class ProductArrivalNotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def available_quantity(self, product_id: UUID) -> float:
        result = await self.db.execute(
            select(func.coalesce(func.sum(ProductStock.available_quantity), 0.0)).where(
                ProductStock.product_id == product_id
            )
        )
        value = result.scalar_one_or_none()
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    async def process_pending(self, *, product_ids: Iterable[UUID] | None = None, limit: int = 500) -> dict:
        filters = [ProductArrivalSubscription.status == "pending"]
        product_ids_list = [item for item in (product_ids or []) if item]
        if product_ids_list:
            filters.append(ProductArrivalSubscription.variant_product_id.in_(product_ids_list))

        result = await self.db.execute(
            select(ProductArrivalSubscription, Product)
            .join(Product, Product.id == ProductArrivalSubscription.variant_product_id)
            .where(*filters)
            .order_by(ProductArrivalSubscription.requested_at.asc())
            .limit(limit)
        )
        rows = result.all()
        if not rows:
            return {"checked": 0, "sent": 0, "failed": 0, "skipped": 0}

        settings, _source = await load_smtp_settings(self.db)
        checked = sent = failed = skipped = 0
        now = datetime.now(timezone.utc)

        for subscription, product in rows:
            checked += 1
            subscription.last_checked_at = now
            quantity = await self.available_quantity(product.id)
            if quantity <= 0:
                skipped += 1
                continue

            if not settings:
                subscription.attempts = int(subscription.attempts or 0) + 1
                subscription.last_error = "SMTP is not configured"
                failed += 1
                continue

            try:
                recommendations = await self._available_recommendations(product)
                message = self._build_message(
                    settings,
                    subscription,
                    product,
                    recommendations=recommendations,
                )
                await asyncio.to_thread(self._send_message, settings, message)
                subscription.status = "sent"
                subscription.notified_at = datetime.now(timezone.utc)
                subscription.last_error = None
                sent += 1
            except Exception as exc:
                subscription.attempts = int(subscription.attempts or 0) + 1
                subscription.last_error = str(exc)[:1000]
                failed += 1
                logger.exception(
                    "Could not send product arrival email subscription=%s product=%s",
                    subscription.id,
                    product.id,
                )

        await self.db.commit()
        return {"checked": checked, "sent": sent, "failed": failed, "skipped": skipped}

    def _build_message(
        self,
        settings: SMTPSettings,
        subscription: ProductArrivalSubscription,
        product: Product,
        *,
        recommendations: list[Product] | None = None,
    ) -> EmailMessage:
        product_name = product.name or "Украшение GLAME"
        variant_label = subscription.variant_label or ""
        image_url = _absolute_public_url(_first_image(product))
        product_url = _product_url(product)
        subject = "Украшение снова в наличии"

        plain_lines = [
            "Хорошая новость — украшение, которое вы ждали, снова в наличии.",
            "",
            product_name,
        ]
        if variant_label:
            plain_lines.append(variant_label)
        plain_lines.extend(["", product_url, "", "GLAME Jewelry"])

        image_html = (
            f'<img src="{html.escape(image_url)}" alt="{html.escape(product_name)}" '
            'style="display:block;width:100%;max-width:260px;height:auto;margin:0;border:0;background:#f4f4f4;" />'
            if image_url
            else ""
        )
        variant_html = (
            f'<p style="margin:8px 0 0;color:#666;font-size:14px;">{html.escape(variant_label)}</p>'
            if variant_label
            else ""
        )
        recommendation_html = self._recommendations_html(recommendations or [])
        html_body = f"""<!doctype html>
<html>
  <body style="margin:0;background:#ffffff;color:#111111;font-family:Arial,sans-serif;">
    <div style="max-width:640px;margin:0 auto;padding:34px 28px;">
      <h1 style="margin:0 0 34px;font-size:26px;line-height:1.2;">Ваше украшение снова в наличии</h1>
      <div style="font-size:36px;letter-spacing:6px;margin-bottom:56px;">GLAME</div>
      <p style="max-width:520px;margin:0 0 28px;font-size:15px;line-height:1.45;text-transform:uppercase;">
        Хорошая новость — украшение, которое вы ждали, снова в наличии.
        Успейте оформить заказ, пока изделие доступно.
      </p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border:1px solid #e1e1e1;margin:0 0 26px 0;">
        <tr>
          <td style="width:42%;padding:18px;vertical-align:top;background:#f7f7f7;">{image_html}</td>
          <td style="padding:18px;vertical-align:top;">
            <h2 style="margin:0;font-size:18px;line-height:1.35;font-weight:600;">{html.escape(product_name)}</h2>
            {variant_html}
            <p style="margin:18px 0 0;color:#777;font-size:13px;">Изделие уже доступно к заказу.</p>
          </td>
        </tr>
      </table>
      <a href="{html.escape(product_url)}"
         style="display:block;margin-top:26px;background:#111111;color:#ffffff;text-decoration:none;text-align:center;padding:14px 18px;font-size:13px;letter-spacing:.4px;">
        ПЕРЕЙТИ К ТОВАРУ
      </a>
      {recommendation_html}
      <p style="margin-top:32px;color:#777;font-size:12px;line-height:1.5;">
        Вы получили это письмо, потому что оставили заявку на уведомление о поступлении в GLAME.
      </p>
    </div>
  </body>
</html>"""

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((settings.from_name, settings.from_email))
        message["To"] = subscription.email
        message.set_content("\n".join(plain_lines))
        message.add_alternative(html_body, subtype="html")
        return message

    async def _available_recommendations(self, product: Product, *, limit: int = 4) -> list[Product]:
        filters = [Product.id != product.id, Product.is_active == True]
        if product.brand:
            filters.append(Product.brand == product.brand)
        elif product.category:
            filters.append(Product.category == product.category)

        result = await self.db.execute(
            select(Product)
            .join(ProductStock, ProductStock.product_id == Product.id)
            .where(*filters)
            .group_by(Product.id)
            .having(func.coalesce(func.sum(ProductStock.available_quantity), 0.0) > 0)
            .order_by(Product.updated_at.desc().nullslast(), Product.name.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    def _recommendations_html(self, products: list[Product]) -> str:
        cards = []
        for product in products[:4]:
            image_url = _absolute_public_url(_first_image(product))
            image_html = (
                f'<img src="{html.escape(image_url)}" alt="{html.escape(product.name or "GLAME")}" '
                'style="display:block;width:100%;height:150px;object-fit:cover;background:#f4f4f4;border:0;" />'
                if image_url
                else '<div style="height:150px;background:#f4f4f4;"></div>'
            )
            cards.append(
                f"""
                <td style="width:50%;padding:0 8px 18px 0;vertical-align:top;">
                  <a href="{html.escape(_product_url(product))}" style="color:#111111;text-decoration:none;">
                    {image_html}
                    <div style="font-size:13px;line-height:1.3;margin-top:10px;font-weight:600;">
                      {html.escape(product.name or "Украшение GLAME")}
                    </div>
                  </a>
                </td>
                """
            )
        if not cards:
            return ""
        rows = []
        for index in range(0, len(cards), 2):
            pair = cards[index : index + 2]
            if len(pair) == 1:
                pair.append('<td style="width:50%;"></td>')
            rows.append(f"<tr>{''.join(pair)}</tr>")
        return f"""
        <div style="margin-top:38px;">
          <h3 style="margin:0 0 18px;font-size:15px;font-weight:500;text-transform:uppercase;">Может понравиться</h3>
          <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;">
            {''.join(rows)}
          </table>
        </div>
        """

    def _send_message(self, settings: SMTPSettings, message: EmailMessage) -> None:
        smtp_cls = smtplib.SMTP_SSL if settings.use_ssl else smtplib.SMTP
        with smtp_cls(settings.host, settings.port, timeout=settings.timeout) as smtp:
            if settings.use_starttls and not settings.use_ssl:
                smtp.starttls()
            if settings.username and settings.password:
                smtp.login(settings.username, settings.password)
            smtp.send_message(message)


def _first_image(product: Product) -> str | None:
    images = product.images if isinstance(product.images, list) else []
    for image in images:
        value = str(image or "").strip()
        if value:
            return value
    return None


def _absolute_public_url(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value
    base = (
        os.getenv("PUBLIC_STATIC_BASE_URL")
        or os.getenv("APP_PUBLIC_BASE_URL")
        or os.getenv("API_PUBLIC_BASE_URL")
        or "https://portal.glamejewelry.ru"
    ).rstrip("/")
    return f"{base}/{value.lstrip('/')}"


def _product_url(product: Product) -> str:
    base = (os.getenv("APP_DEEP_LINK_BASE_URL") or "https://app.glamejewelry.ru").rstrip("/")
    return f"{base}/#/product/{product.id}"
