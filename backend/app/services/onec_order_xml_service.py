from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.user import User


def _rub(amount_kopeks: int) -> str:
    return f"{(int(amount_kopeks or 0) / 100):.2f}"


def _text(parent: Element, name: str, value: Any) -> Element:
    node = SubElement(parent, name)
    node.text = "" if value is None else str(value)
    return node


def _requisite(parent: Element, name: str, value: Any) -> None:
    requisites = parent.find("ЗначенияРеквизитов")
    if requisites is None:
        requisites = SubElement(parent, "ЗначенияРеквизитов")
    item = SubElement(requisites, "ЗначениеРеквизита")
    _text(item, "Наименование", name)
    _text(item, "Значение", value)


class OneCOrderXMLService:
    """
    Формирует CommerceML 2.05 XML с заказами для загрузки в 1С:УНФ через
    стандартный механизм "Обмен с сайтом".
    """

    def build_orders_xml(
        self,
        rows: Iterable[Dict[str, Any]],
        generated_at: Optional[datetime] = None,
    ) -> str:
        dt = generated_at or datetime.now(timezone.utc)
        root = Element(
            "КоммерческаяИнформация",
            {
                "ВерсияСхемы": "2.05",
                "ДатаФормирования": dt.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )

        for row in rows:
            self._append_order(root, row)

        xml_bytes = tostring(root, encoding="utf-8", xml_declaration=True)
        return xml_bytes.decode("utf-8")

    def _append_order(self, root: Element, row: Dict[str, Any]) -> None:
        order: Order = row["order"]
        user: Optional[User] = row.get("user")
        items: List[OrderItem] = row.get("items") or []
        products: Dict[Any, Product] = row.get("products") or {}
        payments = row.get("payments") or []

        doc = SubElement(root, "Документ")
        _text(doc, "Ид", order.id)
        _text(doc, "Номер", str(order.id)[:8])
        _text(doc, "Дата", order.created_at.strftime("%Y-%m-%d") if order.created_at else "")
        _text(doc, "ХозОперация", "Заказ товара")
        _text(doc, "Роль", "Продавец")
        _text(doc, "Валюта", "руб")
        _text(doc, "Курс", "1")
        _text(doc, "Сумма", _rub(order.total_amount))

        self._append_counterparty(doc, order, user)
        self._append_goods(doc, order, items, products)
        self._append_discounts(doc, order)

        payment_method = self._resolve_payment_method(payments)
        _requisite(doc, "Статус заказа", order.status)
        _requisite(doc, "Метод оплаты", payment_method)
        _requisite(doc, "Оплачен", "true" if order.status == "paid" else "false")
        _requisite(doc, "Сумма доставки", _rub(order.delivery_amount))
        _requisite(doc, "Сумма скидки", _rub(order.discount_amount))

        meta = order.meta if isinstance(order.meta, dict) else {}
        bonus = meta.get("bonus_payment") if isinstance(meta.get("bonus_payment"), dict) else {}
        if bonus:
            _requisite(doc, "Оплата бонусами", _rub(int(bonus.get("amount") or 0)))
            _requisite(doc, "Списано бонусов", int(bonus.get("points") or 0))

        gift_purchase = (
            meta.get("gift_certificate_purchase")
            if isinstance(meta.get("gift_certificate_purchase"), dict)
            else {}
        )
        if gift_purchase:
            _requisite(doc, "Тип заказа", "Продажа подарочного сертификата")
            _requisite(doc, "Номинал сертификата", _rub(int(gift_purchase.get("nominal_amount") or 0)))
            _requisite(doc, "Номер сертификата", gift_purchase.get("certificate_number") or "")

        gift_payment = (
            meta.get("gift_certificate_payment")
            if isinstance(meta.get("gift_certificate_payment"), dict)
            else {}
        )
        if gift_payment:
            _requisite(doc, "Оплата сертификатом", _rub(int(gift_payment.get("amount") or 0)))
            _requisite(doc, "Номер сертификата", gift_payment.get("number") or "")
            _requisite(doc, "Статус оплаты сертификатом", gift_payment.get("status") or "")

        delivery = order.delivery if isinstance(order.delivery, dict) else {}
        if delivery:
            _requisite(doc, "Способ доставки", delivery.get("method") or delivery.get("type") or "")
            _requisite(doc, "Комментарий доставки", delivery.get("comment") or "")

    def _append_counterparty(self, doc: Element, order: Order, user: Optional[User]) -> None:
        contact = order.contact if isinstance(order.contact, dict) else {}
        name = (
            contact.get("name")
            or getattr(user, "full_name", None)
            or getattr(user, "phone", None)
            or "Покупатель интернет-магазина"
        )
        phone = contact.get("phone") or getattr(user, "phone", None) or ""
        email = contact.get("email") or getattr(user, "email", None) or ""
        counterparty_id = getattr(user, "customer_id_1c", None) or getattr(user, "id", None) or phone or order.user_id

        counterparties = SubElement(doc, "Контрагенты")
        counterparty = SubElement(counterparties, "Контрагент")
        _text(counterparty, "Ид", counterparty_id)
        _text(counterparty, "Наименование", name)
        _text(counterparty, "Роль", "Покупатель")
        _text(counterparty, "ПолноеНаименование", name)

        contacts = SubElement(counterparty, "Контакты")
        if phone:
            contact_node = SubElement(contacts, "Контакт")
            _text(contact_node, "Тип", "Телефон")
            _text(contact_node, "Значение", phone)
        if email:
            contact_node = SubElement(contacts, "Контакт")
            _text(contact_node, "Тип", "Почта")
            _text(contact_node, "Значение", email)

    def _append_goods(
        self,
        doc: Element,
        order: Order,
        items: List[OrderItem],
        products: Dict[Any, Product],
    ) -> None:
        goods = SubElement(doc, "Товары")
        meta = order.meta if isinstance(order.meta, dict) else {}
        gift_purchase = (
            meta.get("gift_certificate_purchase")
            if isinstance(meta.get("gift_certificate_purchase"), dict)
            else {}
        )
        if gift_purchase:
            nominal = int(gift_purchase.get("nominal_amount") or order.subtotal_amount or 0)
            node = SubElement(goods, "Товар")
            _text(node, "Ид", "GLAME-GIFT-CERTIFICATE")
            _text(node, "Артикул", "GLAME-GIFT-CERTIFICATE")
            _text(node, "Наименование", f"Подарочный сертификат GLAME на {_rub(nominal)}")
            _text(node, "БазоваяЕдиница", "шт")
            _text(node, "ЦенаЗаЕдиницу", _rub(nominal))
            _text(node, "Количество", "1")
            _text(node, "Сумма", _rub(nominal))
            _requisite(node, "ВидНоменклатуры", "Услуга")
            _requisite(node, "ТипПозиции", "Подарочный сертификат")
            _requisite(node, "НомерСертификата", gift_purchase.get("certificate_number") or "")

        for item in items:
            product = products.get(item.product_id)
            product_id = getattr(product, "external_id", None) or item.product_id
            product_name = getattr(product, "name", None) or f"Товар {item.product_id}"
            unit = getattr(product, "unit", None) or "шт"

            node = SubElement(goods, "Товар")
            _text(node, "Ид", product_id)
            _text(node, "Артикул", getattr(product, "article", None) or "")
            _text(node, "Наименование", product_name)
            _text(node, "БазоваяЕдиница", unit)
            _text(node, "ЦенаЗаЕдиницу", _rub(item.unit_price))
            _text(node, "Количество", int(item.quantity or 0))
            _text(node, "Сумма", _rub(item.line_total))
            _requisite(node, "ВидНоменклатуры", "Товар")

        if int(order.delivery_amount or 0) > 0:
            node = SubElement(goods, "Товар")
            _text(node, "Ид", "GLAME-DELIVERY")
            _text(node, "Наименование", "Доставка")
            _text(node, "БазоваяЕдиница", "усл")
            _text(node, "ЦенаЗаЕдиницу", _rub(order.delivery_amount))
            _text(node, "Количество", "1")
            _text(node, "Сумма", _rub(order.delivery_amount))
            _requisite(node, "ВидНоменклатуры", "Услуга")

    def _append_discounts(self, doc: Element, order: Order) -> None:
        meta = order.meta if isinstance(order.meta, dict) else {}
        bonus = meta.get("bonus_payment") if isinstance(meta.get("bonus_payment"), dict) else {}
        bonus_amount = int(bonus.get("amount") or 0) if bonus else 0
        other_discount = max(0, int(order.discount_amount or 0) - bonus_amount)
        if bonus_amount <= 0 and other_discount <= 0:
            return

        discounts = SubElement(doc, "Скидки")
        if bonus_amount > 0:
            node = SubElement(discounts, "Скидка")
            _text(node, "Наименование", "Оплата бонусами")
            _text(node, "Сумма", _rub(bonus_amount))
            _text(node, "УчтеноВСумме", "true")
        if other_discount > 0:
            node = SubElement(discounts, "Скидка")
            _text(node, "Наименование", "Скидка интернет-магазина")
            _text(node, "Сумма", _rub(other_discount))
            _text(node, "УчтеноВСумме", "true")

    @staticmethod
    def _resolve_payment_method(payments: List[Any]) -> str:
        if not payments:
            return ""
        latest = payments[0]
        provider = str(getattr(latest, "provider", "") or "")
        if provider == "bonus":
            return "Бонусы"
        if provider == "gift_certificate":
            return "Подарочный сертификат"
        if provider == "cod":
            return "При получении"
        if provider == "yookassa":
            return "Картой онлайн"
        return provider


async def collect_order_xml_rows(
    db: AsyncSession,
    order_id: Optional[Any] = None,
    updated_since: Optional[datetime] = None,
    include_canceled: bool = False,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    stmt = select(Order).order_by(desc(Order.created_at))
    if order_id:
        stmt = stmt.where(Order.id == order_id)
    if updated_since:
        stmt = stmt.where(Order.updated_at >= updated_since)
    if not include_canceled:
        stmt = stmt.where(Order.status != "canceled")

    orders = (await db.execute(stmt.limit(limit))).scalars().all()
    rows: List[Dict[str, Any]] = []
    for order in orders:
        user = (
            await db.execute(select(User).where(User.id == order.user_id))
        ).scalar_one_or_none()
        items = (
            await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
        ).scalars().all()
        product_ids = [item.product_id for item in items]
        products = {}
        if product_ids:
            product_rows = (
                await db.execute(select(Product).where(Product.id.in_(product_ids)))
            ).scalars().all()
            products = {product.id: product for product in product_rows}
        payments = (
            await db.execute(
                select(Payment)
                .where(Payment.order_id == order.id)
                .order_by(desc(Payment.created_at))
            )
        ).scalars().all()
        rows.append(
            {
                "order": order,
                "user": user,
                "items": items,
                "products": products,
                "payments": payments,
            }
        )
    return rows


async def build_orders_xml_from_db(
    db: AsyncSession,
    order_id: Optional[Any] = None,
    updated_since: Optional[datetime] = None,
    include_canceled: bool = False,
) -> str:
    rows = await collect_order_xml_rows(
        db,
        order_id=order_id,
        updated_since=updated_since,
        include_canceled=include_canceled,
    )
    return OneCOrderXMLService().build_orders_xml(rows)


async def write_orders_xml_snapshot(
    db: AsyncSession,
    path: str = "static/1c_exchange/orders.xml",
) -> str:
    xml = await build_orders_xml_from_db(db)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(xml, encoding="utf-8")
    return str(target)
