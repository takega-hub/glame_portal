from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_task import CrmTask, CrmTaskEvent
from app.models.sales_record import SalesRecord
from app.models.store import Store
from app.models.user import User
from app.services.crm_task_service import CrmTaskService
from app.services.store_aliases import MEGANOM_TO_MRIYA_START_DATE, effective_store_name

logger = logging.getLogger(__name__)

CRM_TOUCHPOINT_SOURCE = "post_purchase_touchpoint"
CRM_TOUCHPOINT_CAMPAIGN_ID = "post-purchase-touchpoints"
CRM_TOUCHPOINT_CAMPAIGN_NAME = "Касания после покупки"
DEFAULT_WARRANTY_DAYS = int(os.getenv("CRM_DEFAULT_WARRANTY_DAYS", "30"))
LEGACY_MEGANOM_MRIYA_START_DATE = MEGANOM_TO_MRIYA_START_DATE

# 1C иногда отдаёт в строке продажи только GUID сотрудника без печатного имени.
# Эти соответствия позволяют не терять назначение при генерации постоянной CRM-кампании.
KNOWN_SELLER_NAMES_BY_EXTERNAL_ID = {
    "eee9caf0-293b-11f1-83c6-fa163e4cc04e": "Бешлиева Аджере Айдеровна",
    "6ded351c-4a43-11f1-9b6c-fa163e4cc04e": "Максимычева Евгения Александровна",
    "1d5f839e-ba5a-11f0-836e-fa163e4cc04e": "Рогалевич Ирина Евгеньевна",
    "4a1f26ca-a92d-11f0-9b8f-fa163e4cc04e": "Уразгильдеева Екатерина Ринадовна",
    "359488bc-6bc4-11f1-864e-fa163e4cc04e": "Ширинская Ление Асановна",
}

# Если продавец из чека уже не сопоставляется с активным аккаунтом платформы,
# касание всё равно должно уйти ответственному за магазин/город.
CRM_TOUCHPOINT_STORE_FALLBACK_SELLER_NAMES = {
    "трк центрум": "Бешлиева Аджере Айдеровна",
    "центрум": "Бешлиева Аджере Айдеровна",
    "мрия": "Рогалевич Ирина Евгеньевна",
    "симферополь": "Бешлиева Аджере Айдеровна",
}


def _coerce_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _crm_display_store_name(value: Optional[str], event_date: Any = None) -> Optional[str]:
    return effective_store_name(value, event_date)


def _seller_external_id(user: Optional[User]) -> Optional[str]:
    if not user:
        return None
    prefs = user.preferences if isinstance(user.preferences, dict) else {}
    return (
        str(prefs.get("seller_external_id") or "").strip()
        or str(prefs.get("onec_seller_id") or "").strip()
        or str(prefs.get("employee_external_id") or "").strip()
        or None
    )


@dataclass(frozen=True)
class TouchpointRule:
    code: str
    title: str
    channel: str
    offset_days: int
    priority: int
    script_key: str


def touchpoint_rules(warranty_days: int = DEFAULT_WARRANTY_DAYS) -> List[TouchpointRule]:
    warranty_offset = max(int(warranty_days or DEFAULT_WARRANTY_DAYS) - 7, 0)
    return [
        TouchpointRule(
            code="post_purchase_care",
            title="Уход после покупки",
            channel="message",
            offset_days=1,
            priority=2,
            script_key="post_purchase_care_d1",
        ),
        TouchpointRule(
            code="warranty_check",
            title="Гарантийное касание",
            channel="call",
            offset_days=warranty_offset,
            priority=1,
            script_key="warranty_check_d_minus_7",
        ),
        TouchpointRule(
            code="cleaning_reminder",
            title="Напоминание о чистке",
            channel="message",
            offset_days=60,
            priority=3,
            script_key="cleaning_reminder_d60",
        ),
    ]


def _utc_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _clean_text(value: Any) -> Optional[str]:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text or None


def _raw_value(raw: Any, *keys: str) -> Optional[str]:
    if not isinstance(raw, dict):
        return None
    for key in keys:
        value = _clean_text(raw.get(key))
        if value and value != "00000000-0000-0000-0000-000000000000":
            return value
    return None


def _normalize_name(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("ё", "е").lower()).strip()


def _format_money_kopecks(value: int) -> str:
    rub = int(round((value or 0) / 100))
    return f"{rub:,}".replace(",", " ") + " ₽"


def _first_name(value: Optional[str], fallback: str = "GLAME", *, surname_first: bool = False) -> str:
    text = _clean_text(value) or fallback
    parts = text.split()
    if not parts:
        return fallback
    if surname_first and len(parts) >= 2:
        return parts[1]
    return parts[0]


def _is_gift_purchase(doc: Dict[str, Any]) -> bool:
    gift_markers = ("подар", "сертификат", "gift", "certificate")
    for item in doc.get("items") or []:
        text = " ".join(
            str(item.get(key) or "")
            for key in ("name", "category", "brand", "article")
        ).lower()
        if any(marker in text for marker in gift_markers):
            return True
    return False


class CrmTouchpointService:
    """Создаёт CRM-задачи продавцам по жизненному циклу покупки."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.crm_service = CrmTaskService(db)

    async def generate_for_work_date(
        self,
        work_date: date,
        *,
        actor: Optional[User] = None,
        warranty_days: int = DEFAULT_WARRANTY_DAYS,
        limit_documents_per_rule: int = 2000,
    ) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "work_date": work_date.isoformat(),
            "warranty_days": warranty_days,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
            "by_rule": {},
        }
        for rule in touchpoint_rules(warranty_days=warranty_days):
            sale_date = work_date - timedelta(days=rule.offset_days)
            rule_result = await self._generate_rule(
                rule,
                work_date=work_date,
                sale_date=sale_date,
                actor=actor,
                limit_documents=limit_documents_per_rule,
                warranty_days=warranty_days,
            )
            summary["by_rule"][rule.code] = rule_result
            for key in ("created", "updated", "skipped"):
                summary[key] += int(rule_result.get(key) or 0)
            summary["errors"].extend(rule_result.get("errors") or [])
        return summary

    async def _generate_rule(
        self,
        rule: TouchpointRule,
        *,
        work_date: date,
        sale_date: date,
        actor: Optional[User],
        limit_documents: int,
        warranty_days: int,
    ) -> Dict[str, Any]:
        result = {
            "rule": rule.code,
            "sale_date": sale_date.isoformat(),
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
        }
        documents = await self._load_sale_documents(sale_date, limit_documents=limit_documents)
        if not documents:
            return result

        customer_ids_1c = {doc["customer_id_1c"] for doc in documents if doc.get("customer_id_1c")}
        store_ids = {doc["store_id"] for doc in documents if doc.get("store_id")}
        users_by_1c = await self._users_by_customer_1c(customer_ids_1c)
        stores_by_external_id = await self._stores_by_external_id(store_ids)
        staff = await self._staff_users()

        for doc in documents:
            try:
                customer = users_by_1c.get(doc["customer_id_1c"])
                if not customer:
                    result["skipped"] += 1
                    continue
                idempotency_key = self._idempotency_key(rule, doc, work_date)
                existing = await self._existing_task(idempotency_key)
                if existing:
                    result["skipped"] += 1
                    continue

                store = stores_by_external_id.get(doc.get("store_id") or "")
                store_name = _crm_display_store_name(getattr(store, "name", None) or doc.get("store_id"), doc.get("sale_date"))
                seller = self._match_seller(
                    doc.get("seller_name"),
                    staff,
                    seller_external_id=doc.get("seller_external_id"),
                    store_name=store_name,
                )
                task = CrmTask(
                    customer_id=customer.id,
                    assigned_seller_user_id=getattr(seller, "id", None),
                    assigned_seller_external_id=_seller_external_id(seller) or doc.get("seller_external_id"),
                    assigned_seller_name=(getattr(seller, "full_name", None) or doc.get("seller_name")),
                    store_id=doc.get("store_id"),
                    store_name=store_name,
                    work_date=work_date,
                    due_date=datetime.combine(work_date, time(hour=20), tzinfo=timezone.utc),
                    priority=rule.priority,
                    crm_group=rule.code,
                    reason=self._reason(rule, customer, doc, warranty_days=warranty_days),
                    seller_action=self._seller_action(rule),
                    script_key=rule.script_key,
                    script_text=self._script_text(rule, customer, doc, store_name=store_name),
                    status="new",
                    campaign_id=CRM_TOUCHPOINT_CAMPAIGN_ID,
                    campaign_name=CRM_TOUCHPOINT_CAMPAIGN_NAME,
                    source=CRM_TOUCHPOINT_SOURCE,
                    source_row_id=doc.get("document_id"),
                    source_idempotency_key=idempotency_key,
                    source_payload={
                        "touchpoint_rule": rule.code,
                        "touchpoint_title": rule.title,
                        "channel": rule.channel,
                        "sale_date": doc["sale_date"].isoformat() if hasattr(doc.get("sale_date"), "isoformat") else str(doc.get("sale_date")),
                        "work_date": work_date.isoformat(),
                        "document_id": doc.get("document_id"),
                        "external_ids": doc.get("external_ids") or [],
                        "sales_record_ids": doc.get("sales_record_ids") or [],
                        "customer_id_1c": doc.get("customer_id_1c"),
                        "store_id_1c": doc.get("store_id"),
                        "seller_external_id": doc.get("seller_external_id"),
                        "seller_name": doc.get("seller_name"),
                        "total_revenue_kopecks": doc.get("total_revenue_kopecks"),
                        "items": doc.get("items") or [],
                        "first_touchpoint_goal": (
                            "Закрепить корпоративный контакт GLAME в телефоне покупателя и объяснить, "
                            "по каким вопросам клиент может обратиться: консультация, подбор к образу, подарок, дистанционный сервис."
                        ) if rule.code == "post_purchase_care" else None,
                        "first_touchpoint_contact_rule": (
                            "Просьба сохранить контакт добавляется только в первое сообщение с корпоративного номера; "
                            "повторно не используется; если клиент уже общался с GLAME по этому номеру, фразу можно убрать."
                        ) if rule.code == "post_purchase_care" else None,
                        "gift_purchase_detected": _is_gift_purchase(doc) if rule.code == "post_purchase_care" else None,
                        "warranty_days": warranty_days,
                        "warranty_end_date": (doc["sale_date"].date() + timedelta(days=warranty_days)).isoformat() if hasattr(doc.get("sale_date"), "date") else None,
                    },
                    created_by_user_id=getattr(actor, "id", None),
                    updated_at=datetime.now(timezone.utc),
                )
                self.db.add(task)
                await self.db.flush()
                self.db.add(CrmTaskEvent(
                    task_id=task.id,
                    event_type="created_from_touchpoint_rule",
                    actor_user_id=getattr(actor, "id", None),
                    actor_name=self.crm_service._actor_name(actor),
                    previous_status=None,
                    next_status=task.status,
                    payload={"rule": rule.code, "document_id": doc.get("document_id"), "sale_date": sale_date.isoformat()},
                ))
                result["created"] += 1
            except Exception as exc:
                logger.exception("Failed to create CRM touchpoint task")
                result["errors"].append({"document_id": doc.get("document_id"), "rule": rule.code, "error": str(exc)})
        await self.db.commit()
        return result

    async def _load_sale_documents(self, sale_date: date, *, limit_documents: int) -> List[Dict[str, Any]]:
        start, end = _utc_bounds(sale_date)
        stmt = (
            select(SalesRecord)
            .where(
                SalesRecord.sale_date >= start,
                SalesRecord.sale_date < end,
                SalesRecord.customer_id.isnot(None),
                SalesRecord.customer_id != "",
                SalesRecord.customer_id != "00000000-0000-0000-0000-000000000000",
                SalesRecord.document_id.isnot(None),
                SalesRecord.document_id != "",
                SalesRecord.revenue > 0,
            )
            .order_by(SalesRecord.sale_date.asc(), SalesRecord.document_id.asc())
            .limit(max(limit_documents, 1) * 20)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            document_id = row.document_id or row.external_id or str(row.id)
            group_key = f"{row.customer_id}:{document_id}"
            raw = row.raw_data or {}
            seller_external_id = _raw_value(raw, "Продавец_Key", "Сотрудник_Key", "Кассир_Key", "Ответственный_Key", "Менеджер_Key")
            seller_name = _raw_value(raw, "Продавец", "Сотрудник", "Кассир", "Ответственный", "Менеджер")
            if not seller_name and seller_external_id:
                seller_name = KNOWN_SELLER_NAMES_BY_EXTERNAL_ID.get(seller_external_id)
            doc = grouped.setdefault(group_key, {
                "document_id": document_id,
                "customer_id_1c": row.customer_id,
                "sale_date": row.sale_date,
                "store_id": row.store_id,
                "seller_external_id": seller_external_id,
                "seller_name": seller_name,
                "total_revenue_kopecks": 0,
                "items": [],
                "external_ids": [],
                "sales_record_ids": [],
            })
            if row.sale_date and row.sale_date < doc["sale_date"]:
                doc["sale_date"] = row.sale_date
            if not doc.get("store_id") and row.store_id:
                doc["store_id"] = row.store_id
            if not doc.get("seller_external_id") and seller_external_id:
                doc["seller_external_id"] = seller_external_id
            if not doc.get("seller_name") and seller_name:
                doc["seller_name"] = seller_name
            doc["total_revenue_kopecks"] += int(round(float(row.revenue or 0) * 100))
            if row.external_id:
                doc["external_ids"].append(row.external_id)
            doc["sales_record_ids"].append(str(row.id))
            item_label = " · ".join([x for x in [row.product_article, row.product_name] if x])
            if item_label:
                doc["items"].append({
                    "article": row.product_article,
                    "name": row.product_name,
                    "category": row.product_category,
                    "brand": row.product_brand,
                    "quantity": row.quantity,
                    "revenue_kopecks": int(round(float(row.revenue or 0) * 100)),
                })
        return list(grouped.values())[:limit_documents]

    async def _users_by_customer_1c(self, customer_ids_1c: Iterable[str]) -> Dict[str, User]:
        values = [value for value in customer_ids_1c if value]
        if not values:
            return {}
        result = await self.db.execute(select(User).where(User.is_customer.is_(True), User.customer_id_1c.in_(values)))
        return {user.customer_id_1c: user for user in result.scalars().all() if user.customer_id_1c}

    async def _stores_by_external_id(self, store_ids: Iterable[str]) -> Dict[str, Store]:
        values = [value for value in store_ids if value]
        if not values:
            return {}
        result = await self.db.execute(select(Store).where(Store.external_id.in_(values)))
        return {store.external_id: store for store in result.scalars().all() if store.external_id}

    async def _staff_users(self) -> List[User]:
        result = await self.db.execute(
            select(User).where(User.is_customer.is_(False), User.role.in_(["seller", "manager", "admin"]), User.full_name.isnot(None))
        )
        return result.scalars().all()

    def _match_seller(
        self,
        seller_name: Optional[str],
        staff: List[User],
        *,
        seller_external_id: Optional[str] = None,
        store_name: Optional[str] = None,
    ) -> Optional[User]:
        fallback_name = self._fallback_seller_name_for_store(store_name)
        if fallback_name and "мрия" in _normalize_name(store_name):
            fallback_normalized = _normalize_name(fallback_name)
            for user in staff:
                if _normalize_name(user.full_name) == fallback_normalized:
                    return user

        external_id = (seller_external_id or "").strip()
        if external_id:
            for user in staff:
                prefs = user.preferences if isinstance(user.preferences, dict) else {}
                external_ids = {
                    str(prefs.get("seller_external_id") or "").strip(),
                    str(prefs.get("onec_seller_id") or "").strip(),
                    str(prefs.get("employee_external_id") or "").strip(),
                }
                extra_external_ids = prefs.get("seller_external_ids") or []
                if isinstance(extra_external_ids, str):
                    extra_external_ids = [extra_external_ids]
                external_ids.update(str(value or "").strip() for value in extra_external_ids)
                if external_id in external_ids:
                    return user

        normalized = _normalize_name(seller_name)
        if not normalized:
            if fallback_name:
                fallback_normalized = _normalize_name(fallback_name)
                for user in staff:
                    if _normalize_name(user.full_name) == fallback_normalized:
                        return user
            return None
        for user in staff:
            if _normalize_name(user.full_name) == normalized:
                return user
        seller_parts = normalized.split()
        if seller_parts:
            surname = seller_parts[0]
            matches = [user for user in staff if _normalize_name(user.full_name).split()[:1] == [surname]]
            if len(matches) == 1:
                return matches[0]
        if fallback_name:
            fallback_normalized = _normalize_name(fallback_name)
            for user in staff:
                if _normalize_name(user.full_name) == fallback_normalized:
                    return user
        return None

    def _fallback_seller_name_for_store(self, store_name: Optional[str]) -> Optional[str]:
        normalized_store = _normalize_name(store_name)
        if not normalized_store:
            return None
        for store_marker, seller_name in CRM_TOUCHPOINT_STORE_FALLBACK_SELLER_NAMES.items():
            if store_marker in normalized_store:
                return seller_name
        return None

    def _existing_task(self, idempotency_key: str):
        return self.db.scalar(select(CrmTask).where(CrmTask.source_idempotency_key == idempotency_key))

    def _idempotency_key(self, rule: TouchpointRule, doc: Dict[str, Any], work_date: date) -> str:
        return f"{CRM_TOUCHPOINT_SOURCE}:{rule.code}:{doc.get('document_id')}:{doc.get('customer_id_1c')}:{work_date.isoformat()}"

    def _reason(self, rule: TouchpointRule, customer: User, doc: Dict[str, Any], *, warranty_days: int) -> str:
        purchase_date = doc["sale_date"].date().isoformat() if hasattr(doc.get("sale_date"), "date") else str(doc.get("sale_date"))
        amount = _format_money_kopecks(int(doc.get("total_revenue_kopecks") or 0))
        if rule.code == "post_purchase_care":
            return (
                f"На следующий день после покупки от {purchase_date}: поблагодарить клиента, "
                "закрепить корпоративный контакт GLAME как личный сервисный канал и отправить короткие рекомендации по уходу. "
                f"Сумма чека: {amount}."
            )
        if rule.code == "warranty_check":
            return (
                f"Сервисное касание по покупке от {purchase_date}: напомнить клиенту, когда и в каком магазине была покупка, "
                "сказать, что GLAME всегда звонит покупателям перед окончанием гарантийного срока, и мягко уточнить, всё ли в порядке "
                "с украшениями, нет ли вопросов по чистке или хранению. Если всё хорошо — аккуратно открыть тему новинок или позиций, которые лучше увидеть вживую."
            )
        if rule.code == "cleaning_reminder":
            return f"Через 2 месяца после покупки от {purchase_date}: пригласить клиента принести украшение в GLAME, чтобы посмотреть состояние и при необходимости аккуратно почистить."
        return rule.title

    def _seller_action(self, rule: TouchpointRule) -> str:
        if rule.code == "post_purchase_care":
            return (
                "Отправить два коротких сообщения с корпоративного телефона. "
                "Цель первого касания: закрепить корпоративный контакт GLAME в телефоне покупателя и объяснить пользу канала "
                "(консультация по украшению, подбор к образу или подарку, дистанционный сервис). "
                "Просьбу сохранить контакт использовать только в первом сообщении; если клиент уже общался с GLAME по этому номеру, фразу можно убрать."
            )
        if rule.code == "warranty_check":
            return (
                "Позвонить покупателю по покупке: назвать дату и магазин, напомнить про сервисное касание перед окончанием гарантийного срока, "
                "уточнить, всё ли в порядке с украшениями, есть ли вопросы по чистке или хранению. "
                "Если всё хорошо — мягко предложить посмотреть новые позиции. Если есть проблема — сначала разобраться с изделием."
            )
        if rule.code == "cleaning_reminder":
            return "Отправить сообщение с корпоративного телефона: пригласить клиента на мягкую проверку состояния украшения и чистку при необходимости."
        return rule.title

    def _script_text(self, rule: TouchpointRule, customer: User, doc: Dict[str, Any], *, store_name: Optional[str] = None) -> str:
        name = _first_name(customer.full_name, fallback="", surname_first=True) if customer.full_name else ""
        name_prefix = f"{name}, " if name else "Здравствуйте! "
        seller_name = doc.get("seller_name") or "GLAME"
        seller_first_name = _first_name(seller_name, fallback="GLAME", surname_first=True)
        store_label = _clean_text(store_name) or "GLAME"
        purchase_date = doc["sale_date"].date().strftime("%d.%m.%Y") if hasattr(doc.get("sale_date"), "date") else ""
        if rule.code == "post_purchase_care":
            greeting = f"{name}, здравствуйте!" if name else "Здравствуйте!"
            regular_message_1 = (
                f"{greeting} Это {seller_first_name} из GLAME, {store_label}. "
                "Спасибо, что выбрали украшение у нас.\n\n"
                "Сохраните, пожалуйста, этот номер — это корпоративный контакт GLAME. "
                "Сюда можно написать, если понадобится консультация по украшению, помощь с подбором к образу или подарком. "
                "В том числе можем помочь дистанционно."
            )
            regular_message_2 = (
                "И коротко по уходу: украшение лучше хранить отдельно, снимать перед водой, спортом и сном, "
                "а парфюм и крем наносить до украшений. Пусть носится красиво и с удовольствием."
            )
            gift_message_1 = (
                f"{greeting} Это {seller_first_name} из GLAME, {store_label}. "
                "Спасибо, что выбрали подарок у нас.\n\n"
                "Сохраните, пожалуйста, этот номер — это корпоративный контакт GLAME. "
                "Сюда можно написать, если понадобится помощь с украшением или нужно будет снова подобрать подарок без долгого поиска. "
                "Можем помочь и дистанционно."
            )
            gift_message_2 = (
                "Коротко по уходу: украшение лучше хранить отдельно, снимать перед водой, спортом и сном, "
                "а парфюм и крем наносить до украшений. Если у получателя появятся вопросы, можно написать нам сюда."
            )
            if _is_gift_purchase(doc):
                return (
                    "Покупка похожа на подарок — используйте подарочный вариант.\n\n"
                    f"Сообщение 1:\n{gift_message_1}\n\n"
                    f"Сообщение 2:\n{gift_message_2}\n\n"
                    "Если это всё-таки покупка для себя, используйте основной вариант:\n\n"
                    f"Сообщение 1:\n{regular_message_1}\n\n"
                    f"Сообщение 2:\n{regular_message_2}"
                )
            return (
                f"Сообщение 1:\n{regular_message_1}\n\n"
                f"Сообщение 2:\n{regular_message_2}\n\n"
                "Если покупка была подарком, используйте вариант ниже:\n\n"
                f"Сообщение 1:\n{gift_message_1}\n\n"
                f"Сообщение 2:\n{gift_message_2}"
            )
        if rule.code == "warranty_check":
            greeting = f"{name}, здравствуйте!" if name else "Здравствуйте!"
            purchase_context = (
                f"Вы у нас покупали украшения {purchase_date} в магазине {store_label}. "
                "Помните нас? Мы всегда звоним нашим покупателям перед окончанием гарантийного срока, "
                "чтобы уточнить, что всё в порядке с украшениями, которые приобрели. "
                "Возможно, есть какие-то вопросы по чистке или хранению украшений?"
            )
            return (
                f"Звонок:\n{greeting} Это {seller_first_name} из GLAME, {store_label}.\n"
                f"{purchase_context}\n\n"
                "Если всё хорошо:\n"
                "Отлично, очень рада. Тогда не буду долго отвлекать.\n"
                f"У нас сейчас появились новые украшения, есть несколько позиций, которые действительно лучше увидеть вживую. "
                f"Когда будете рядом с {store_label} — зайдите, покажем Вам.\n\n"
                "Если клиент проявил интерес:\n"
                "Мы отобрали несколько красивых позиций из нового поступления. Я отправлю Вам фото после звонка, "
                "а если что-то понравится — сможем оставить к Вашему визиту.\n\n"
                "Если не в городе:\n"
                "Понимаю. Тогда отправлю Вам фото того, что сейчас появилось в GLAME. "
                "А когда будете в городе, зайдите — покажем вживую. Если что-то понравится, сможем оставить к Вашему приезду.\n\n"
                "Если проблема:\n"
                f"Понимаю Вас. Тогда сначала разберёмся с изделием. Пришлите, пожалуйста, фото при дневном свете "
                f"или принесите украшение в GLAME, {store_label}. Мы посмотрим и передадим вопрос на проверку.\n\n"
                "Сообщение после недозвона:\n"
                f"{greeting} Это {seller_first_name} из GLAME, {store_label}.\n"
                "Звонила по Вашей недавней покупке — хотели уточнить, всё ли хорошо с украшением в носке. "
                "Если есть вопрос по изделию, напишите нам, пожалуйста.\n\n"
                "И если будет настроение посмотреть что-то новое для себя, в магазине сейчас есть несколько красивых позиций — "
                f"можем показать в {store_label} или отправить фото."
            )
        if rule.code == "cleaning_reminder":
            greeting = f"{name}, здравствуйте!" if name else "Здравствуйте!"
            return (
                f"{greeting} Это {seller_first_name} из GLAME, {store_label}.\n"
                "Вы выбирали у нас украшение несколько месяцев назад. "
                "Если часто его носите, уже можно принести в GLAME — посмотрим состояние и при необходимости аккуратно почистим.\n"
                "Будем рады Вас видеть."
            )
        return rule.title
