"""
DirectorDataService — сервис доступа к живым данным БД для AI-директора.

Предоставляет методы для получения:
- Продажи сегодня/неделя/месяц
- Статистика покупателей (количество, сегменты, новые)
- Статистика товаров (категории, бренды, топ продаж)
- Аналитика по магазинам
- Остатки по складам из 1С
- Посещения магазинов
- Чеки и агрегированные продажи из 1С
- Детали покупателей (история покупок)
- Тренды продаж
"""
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timedelta, date
import logging
import os
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, text, case, literal_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_stock import ProductStock
from app.models.user import User
from app.models.sales_metric import SalesMetric
from app.models.sales_record import SalesRecord
from app.models.product_sales_analytics import ProductSalesAnalytics
from app.models.purchase_history import PurchaseHistory
from app.models.store import Store
from app.models.store_visit import StoreVisit
from app.models.marketing_campaign import MarketingCampaign
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.analytics_event import AnalyticsEvent
from app.models.website_visit import WebsiteVisit
from app.models.social_media_metric import SocialMediaMetric
from app.models.customer_message import CustomerMessage
from app.models.customer_segment import CustomerSegment
from app.models.user_segment import UserSegment
from app.models.saved_look import SavedLook
from app.models.look import Look
from app.models.stylist_chat_message import StylistChatMessage
from app.models.live_stylist_conversation import LiveStylistConversation

logger = logging.getLogger(__name__)


class DirectorDataService:
    """Сервис для выполнения запросов к живым данным БД"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _store_match_keys(name: Optional[str]) -> List[str]:
        """Ключи сопоставления магазинов между 1С и счетчиками посещений."""
        if not name:
            return []

        normalized = (
            str(name)
            .strip()
            .lower()
            .replace("ё", "е")
            .replace(",", " ")
            .replace(".", " ")
            .replace("-", " ")
        )
        normalized = " ".join(normalized.split())

        keys = {normalized}
        if "centrum" in normalized or "центрум" in normalized or "центр" in normalized:
            keys.update({"centrum", "центрум", "трк центрум"})
        if "yalta" in normalized or "ялта" in normalized:
            keys.update({"yalta", "ялта", "ялта набережная 18"})

        return list(keys)

    # ───────────────────────────── ПРОДАЖИ ─────────────────────────────

    async def get_today_sales(self) -> Dict[str, Any]:
        """Продажи за сегодня: выручка, количество чеков, товаров. Primary source: sales_records."""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        records_result = await self.db.execute(
            select(
                func.count(func.distinct(SalesRecord.document_id)).label("checks_count"),
                func.coalesce(func.sum(SalesRecord.revenue), 0).label("total_revenue"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("items_sold"),
                func.max(SalesRecord.sale_date).label("last_sale_at"),
            )
            .where(SalesRecord.sale_date >= today_start)
        )
        records_row = records_result.one_or_none()
        checks_count = int(records_row.checks_count or 0) if records_row else 0
        if checks_count:
            total_revenue = float(records_row.total_revenue or 0)
            return {
                "period": "today",
                "date": today_start.isoformat(),
                "orders_count": checks_count,
                "checks_count": checks_count,
                "total_revenue": total_revenue,
                "total_revenue_rub": round(total_revenue, 2),
                "items_sold": float(records_row.items_sold or 0),
                "average_check_rub": round(total_revenue / checks_count, 2),
                "last_sale_at": records_row.last_sale_at.isoformat() if records_row.last_sale_at else None,
                "source": "sales_records",
            }

        orders_result = await self.db.execute(
            select(
                func.count(Order.id).label("order_count"),
                func.coalesce(func.sum(Order.total_amount), 0).label("total_revenue"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("items_sold"),
            )
            .select_from(Order)
            .outerjoin(OrderItem, OrderItem.order_id == Order.id)
            .where(
                and_(
                    Order.created_at >= today_start,
                    Order.status.in_(["completed", "paid", "delivered"]),
                )
            )
        )
        row = orders_result.one_or_none()
        return {
            "period": "today",
            "date": today_start.isoformat(),
            "orders_count": row.order_count if row else 0,
            "checks_count": row.order_count if row else 0,
            "total_revenue": row.total_revenue if row else 0,
            "total_revenue_rub": round((row.total_revenue or 0) / 100, 2),
            "items_sold": row.items_sold if row else 0,
            "source": "orders_fallback",
        }

    async def get_sales_for_period(self, days: int = 7) -> Dict[str, Any]:
        """Продажи за N дней. Primary source: sales_records из 1С."""
        since = datetime.now() - timedelta(days=days)

        records_result = await self.db.execute(
            select(
                func.count(func.distinct(SalesRecord.document_id)).label("checks_count"),
                func.coalesce(func.sum(SalesRecord.revenue), 0).label("total_revenue"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("items_sold"),
                func.count(func.distinct(SalesRecord.customer_id)).label("unique_customers"),
                func.max(SalesRecord.sale_date).label("last_sale_at"),
            )
            .where(SalesRecord.sale_date >= since)
        )
        records_row = records_result.one_or_none()
        checks_count = int(records_row.checks_count or 0) if records_row else 0
        if checks_count:
            total_revenue = float(records_row.total_revenue or 0)
            return {
                "period": f"last_{days}_days",
                "days": days,
                "since": since.isoformat(),
                "orders_count": checks_count,
                "checks_count": checks_count,
                "total_revenue": total_revenue,
                "total_revenue_rub": round(total_revenue, 2),
                "items_sold": float(records_row.items_sold or 0),
                "unique_customers": int(records_row.unique_customers or 0),
                "average_check": round(total_revenue / checks_count, 2),
                "average_check_rub": round(total_revenue / checks_count, 2),
                "last_sale_at": records_row.last_sale_at.isoformat() if records_row.last_sale_at else None,
                "source": "sales_records",
            }

        orders_result = await self.db.execute(
            select(
                func.count(Order.id).label("order_count"),
                func.coalesce(func.sum(Order.total_amount), 0).label("total_revenue"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("items_sold"),
                func.count(func.distinct(Order.user_id)).label("unique_customers"),
            )
            .select_from(Order)
            .outerjoin(OrderItem, OrderItem.order_id == Order.id)
            .where(
                and_(
                    Order.created_at >= since,
                    Order.status.in_(["completed", "paid", "delivered"]),
                )
            )
        )
        row = orders_result.one_or_none()

        # Средний чек
        order_count = row.order_count or 0
        total_revenue = row.total_revenue or 0
        avg_check = round(total_revenue / order_count, 2) if order_count > 0 else 0

        return {
            "period": f"last_{days}_days",
            "days": days,
            "since": since.isoformat(),
            "orders_count": order_count,
            "checks_count": order_count,
            "total_revenue": total_revenue,
            "total_revenue_rub": round(total_revenue / 100, 2),
            "items_sold": row.items_sold or 0,
            "unique_customers": row.unique_customers or 0,
            "average_check": avg_check,
            "average_check_rub": round(avg_check / 100, 2),
            "source": "orders_fallback",
        }

    async def get_daily_sales_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """Ежедневный тренд продаж за N дней"""
        since = datetime.now() - timedelta(days=days)

        result = await self.db.execute(
            select(
                func.date(Order.created_at).label("day"),
                func.count(Order.id).label("orders_count"),
                func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
            )
            .where(
                and_(
                    Order.created_at >= since,
                    Order.status.in_(["completed", "paid", "delivered"]),
                )
            )
            .group_by(func.date(Order.created_at))
            .order_by(func.date(Order.created_at))
        )
        rows = result.all()
        return [
            {
                "date": str(r.day),
                "orders_count": r.orders_count,
                "revenue": r.revenue,
                "revenue_rub": round(r.revenue / 100, 2),
            }
            for r in rows
        ]

    async def get_recent_orders(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Последние заказы с суммой и статусом"""
        result = await self.db.execute(
            select(
                Order.id,
                Order.status,
                Order.total_amount,
                Order.created_at,
                User.email,
                User.full_name,
                User.discount_card_number,
            )
            .outerjoin(User, User.id == Order.user_id)
            .order_by(desc(Order.created_at))
            .limit(limit)
        )
        rows = result.all()
        return [
            {
                "order_id": str(r.id),
                "status": r.status,
                "total_amount": r.total_amount,
                "total_amount_rub": round(r.total_amount / 100, 2) if r.total_amount else 0,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "customer_email": r.email,
                "customer_name": r.full_name,
                "discount_card": r.discount_card_number,
            }
            for r in rows
        ]

    # ───────────────────────────── ПОКУПАТЕЛИ ─────────────────────────────

    async def get_customer_summary(self) -> Dict[str, Any]:
        """Общая статистика по покупателям"""
        total = await self.db.execute(
            select(func.count(User.id)).where(User.is_customer == True)
        )
        total_customers = total.scalar() or 0

        # По сегментам
        segments_result = await self.db.execute(
            select(User.customer_segment, func.count(User.id).label("cnt"))
            .where(User.is_customer == True)
            .group_by(User.customer_segment)
        )
        segments = {row.customer_segment or "unknown": row.cnt for row in segments_result.all()}

        # Новые за последние 30 дней
        month_ago = datetime.now() - timedelta(days=30)
        new_customers = await self.db.execute(
            select(func.count(User.id)).where(
                and_(User.is_customer == True, User.created_at >= month_ago)
            )
        )

        # Покупатели с purchase_history
        buyers_result = await self.db.execute(
            select(func.count(func.distinct(PurchaseHistory.user_id)))
        )
        buyers = buyers_result.scalar() or 0

        # Всего накоплено баллов лояльности
        loyalty_result = await self.db.execute(
            select(func.coalesce(func.sum(User.loyalty_points), 0))
        )
        total_loyalty_points = loyalty_result.scalar() or 0

        return {
            "total_customers": total_customers,
            "by_segment": segments,
            "new_last_30_days": new_customers.scalar() or 0,
            "customers_with_purchases": buyers,
            "total_loyalty_points": total_loyalty_points,
            "available_customer_data": self.get_customer_data_capabilities(),
        }

    def get_customer_data_capabilities(self) -> Dict[str, Any]:
        """Что директор может видеть по покупателям в БД и кабинете покупателя."""
        return {
            "profile": [
                "id", "phone", "email", "full_name", "city", "gender", "discount_card_number",
                "customer_id_1c", "discount_card_id_1c", "persona", "preferences",
                "customer_segment", "rfm_score", "purchase_preferences",
                "preferred_store_name", "secondary_store_name", "synced_at",
            ],
            "loyalty": [
                "loyalty_points", "loyalty_transactions", "transaction_type", "points",
                "balance_after", "reason", "description", "source", "expires_at",
            ],
            "purchase_history": [
                "purchase_date", "document_id_1c", "store_id_1c", "store_name",
                "product_name", "product_article", "category", "brand", "quantity",
                "price", "total_amount",
            ],
            "communications": [
                "generated_customer_messages", "message", "cta", "event_type", "event_brand",
                "event_store", "status", "sent_at", "payload",
            ],
            "stylist": [
                "live_stylist_conversations", "conversation_status", "scenario", "source",
                "assigned_stylist", "internal_notes", "result_purchase_status",
                "stylist_chat_messages", "attachments",
            ],
            "app_behavior": [
                "analytics_events", "page_view", "ui_click", "product_view", "look_view",
                "chat_message", "channel", "utm", "event_data",
            ],
            "saved_content": [
                "saved_looks", "favorite/generated", "notes", "is_purchased",
                "recommended_occasions", "look_name",
            ],
        }

    async def find_customer(
        self,
        query: str,
        search_by: str = "auto",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Поиск покупателя по discount_card, email, phone, имени"""
        conditions = [User.is_customer == True]
        search_pattern = f"%{query}%"

        if search_by == "card":
            conditions.append(User.discount_card_number.ilike(search_pattern))
        elif search_by == "email":
            conditions.append(User.email.ilike(search_pattern))
        elif search_by == "phone":
            conditions.append(User.phone.ilike(search_pattern))
        elif search_by == "name":
            conditions.append(User.full_name.ilike(search_pattern))
        else:
            conditions.append(
                func.lower(User.full_name).ilike(search_pattern)
                | func.lower(User.email).ilike(search_pattern)
                | User.discount_card_number.ilike(search_pattern)
                | User.phone.ilike(search_pattern)
            )

        result = await self.db.execute(
            select(User).where(and_(*conditions)).limit(limit)
        )
        users = result.scalars().all()
        return [
            {
                "id": str(u.id),
                "full_name": u.full_name,
                "email": u.email,
                "phone": u.phone,
                "discount_card_number": u.discount_card_number,
                "customer_segment": u.customer_segment,
                "city": u.city,
                "gender": u.gender,
                "total_purchases": u.total_purchases,
                "total_spent_rub": round(u.total_spent / 100, 2) if u.total_spent else 0,
                "average_check_rub": round(u.average_check / 100, 2) if u.average_check else 0,
                "last_purchase_date": u.last_purchase_date.isoformat() if u.last_purchase_date else None,
                "loyalty_points": u.loyalty_points,
                "preferred_store": u.preferred_store_name,
            }
            for u in users
        ]

    async def resolve_customer(self, query: str) -> Optional[User]:
        """Найти покупателя по UUID, телефону, email, карте, 1С ID или имени."""
        raw = (query or "").strip()
        if not raw:
            return None

        try:
            uid = UUID(raw)
            result = await self.db.execute(select(User).where(User.id == uid, User.is_customer == True))
            user = result.scalar_one_or_none()
            if user:
                return user
        except Exception:
            pass

        phone_digits = "".join(ch for ch in raw if ch.isdigit())
        search = f"%{raw}%"
        conditions = [
            User.discount_card_number.ilike(search),
            User.customer_id_1c.ilike(search),
            User.discount_card_id_1c.ilike(search),
            User.email.ilike(search),
            User.full_name.ilike(search),
        ]
        if phone_digits:
            conditions.append(User.phone.ilike(f"%{phone_digits[-10:]}%"))

        result = await self.db.execute(
            select(User)
            .where(and_(User.is_customer == True, or_(*conditions)))
            .order_by(desc(User.last_purchase_date), desc(User.total_spent))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_customer_full_profile(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """Полный паспорт покупателя: профиль, покупки, баллы, сообщения, стилист, поведение."""
        user = await self.resolve_customer(query)
        if not user:
            matches = await self.find_customer(query, limit=10)
            return {
                "status": "not_found",
                "query": query,
                "matches": matches,
                "available_customer_data": self.get_customer_data_capabilities(),
            }

        uid = user.id

        segments_result = await self.db.execute(
            select(CustomerSegment)
            .join(UserSegment, UserSegment.segment_id == CustomerSegment.id)
            .where(UserSegment.user_id == uid)
            .order_by(CustomerSegment.name)
        )
        segments = segments_result.scalars().all()

        purchase_result = await self.db.execute(
            select(PurchaseHistory, Store.name.label("store_name"))
            .outerjoin(Store, Store.external_id == PurchaseHistory.store_id_1c)
            .where(PurchaseHistory.user_id == uid)
            .order_by(desc(PurchaseHistory.purchase_date))
            .limit(limit)
        )
        purchase_rows = purchase_result.all()

        loyalty_result = await self.db.execute(
            select(LoyaltyTransaction)
            .where(LoyaltyTransaction.user_id == uid)
            .order_by(desc(LoyaltyTransaction.created_at))
            .limit(limit)
        )
        loyalty_rows = loyalty_result.scalars().all()

        messages_result = await self.db.execute(
            select(CustomerMessage)
            .where(CustomerMessage.user_id == uid)
            .order_by(desc(CustomerMessage.created_at))
            .limit(limit)
        )
        message_rows = messages_result.scalars().all()

        conversations_result = await self.db.execute(
            select(LiveStylistConversation)
            .where(LiveStylistConversation.customer_user_id == uid)
            .order_by(desc(LiveStylistConversation.last_message_at), desc(LiveStylistConversation.created_at))
            .limit(10)
        )
        conversations = conversations_result.scalars().all()
        conversation_ids = [c.id for c in conversations]
        stylist_messages: List[StylistChatMessage] = []
        if conversation_ids:
            stylist_messages = (
                await self.db.execute(
                    select(StylistChatMessage)
                    .where(StylistChatMessage.conversation_id.in_(conversation_ids))
                    .order_by(desc(StylistChatMessage.created_at))
                    .limit(limit * 2)
                )
            ).scalars().all()

        saved_result = await self.db.execute(
            select(SavedLook, Look.name.label("look_name"))
            .outerjoin(Look, Look.id == SavedLook.look_id)
            .where(SavedLook.user_id == uid)
            .order_by(desc(SavedLook.created_at))
            .limit(limit)
        )
        saved_rows = saved_result.all()

        app_events_result = await self.db.execute(
            select(AnalyticsEvent)
            .where(AnalyticsEvent.user_id == uid)
            .order_by(desc(AnalyticsEvent.timestamp))
            .limit(limit)
        )
        app_events = app_events_result.scalars().all()

        website_result = await self.db.execute(
            select(WebsiteVisit)
            .where(WebsiteVisit.user_id == uid)
            .order_by(desc(WebsiteVisit.created_at))
            .limit(limit)
        )
        website_visits = website_result.scalars().all()

        return {
            "status": "available",
            "available_customer_data": self.get_customer_data_capabilities(),
            "profile": {
                "id": str(user.id),
                "full_name": user.full_name,
                "phone": user.phone,
                "email": user.email,
                "city": user.city,
                "gender": user.gender,
                "discount_card_number": user.discount_card_number,
                "customer_id_1c": user.customer_id_1c,
                "discount_card_id_1c": user.discount_card_id_1c,
                "persona": user.persona,
                "preferences": user.preferences or {},
                "customer_segment": user.customer_segment,
                "segments": [{"id": str(s.id), "name": s.name} for s in segments],
                "rfm_score": user.rfm_score or {},
                "purchase_preferences": user.purchase_preferences or {},
                "loyalty_points": int(user.loyalty_points or 0),
                "total_purchases": int(user.total_purchases or 0),
                "total_spent_rub": round((user.total_spent or 0) / 100, 2),
                "average_check_rub": round((user.average_check or 0) / 100, 2) if user.average_check else None,
                "last_purchase_date": user.last_purchase_date.isoformat() if user.last_purchase_date else None,
                "preferred_store_name": user.preferred_store_name,
                "preferred_store_share": user.preferred_store_share,
                "secondary_store_name": user.secondary_store_name,
                "synced_at": user.synced_at.isoformat() if user.synced_at else None,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            },
            "purchase_history": [
                {
                    "id": str(p.id),
                    "purchase_date": p.purchase_date.isoformat() if p.purchase_date else None,
                    "document_id_1c": p.document_id_1c,
                    "store_id_1c": p.store_id_1c,
                    "store_name": store_name,
                    "product_name": p.product_name,
                    "product_article": p.product_article,
                    "product_id_1c": p.product_id_1c,
                    "brand": p.brand,
                    "category": p.category,
                    "quantity": p.quantity,
                    "price_rub": round((p.price or 0) / 100, 2),
                    "total_amount_rub": round((p.total_amount or 0) / 100, 2),
                    "sync_metadata": p.sync_metadata or {},
                }
                for p, store_name in purchase_rows
            ],
            "loyalty_transactions": [
                {
                    "id": str(t.id),
                    "transaction_type": t.transaction_type,
                    "points": t.points,
                    "balance_after": t.balance_after,
                    "reason": t.reason,
                    "description": t.description,
                    "source": t.source,
                    "source_id": t.source_id,
                    "expires_at": t.expires_at.isoformat() if t.expires_at else None,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in loyalty_rows
            ],
            "customer_messages": [
                {
                    "id": str(m.id),
                    "message": m.message,
                    "cta": m.cta,
                    "segment": m.segment,
                    "event_type": m.event_type,
                    "event_brand": m.event_brand,
                    "event_store": m.event_store,
                    "status": m.status,
                    "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "payload": m.payload or {},
                }
                for m in message_rows
            ],
            "stylist": {
                "conversations": [
                    {
                        "id": str(c.id),
                        "source": c.source,
                        "scenario": c.scenario,
                        "status": c.status,
                        "priority": c.priority,
                        "unread_for_stylist_count": c.unread_for_stylist_count,
                        "unread_for_customer_count": c.unread_for_customer_count,
                        "recommended_product_ids": c.recommended_product_ids or [],
                        "internal_notes": c.internal_notes,
                        "result_purchase_status": c.result_purchase_status,
                        "result_notes": c.result_notes,
                        "meta": c.meta or {},
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                        "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
                    }
                    for c in conversations
                ],
                "messages": [
                    {
                        "id": str(m.id),
                        "conversation_id": str(m.conversation_id) if m.conversation_id else None,
                        "role": m.role,
                        "text": m.text,
                        "attachments": m.attachments or [],
                        "payload": m.payload or {},
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in stylist_messages
                ],
            },
            "saved_looks": [
                {
                    "id": str(saved.id),
                    "look_id": str(saved.look_id),
                    "look_name": look_name,
                    "save_type": saved.save_type,
                    "notes": saved.notes,
                    "is_purchased": saved.is_purchased,
                    "purchased_at": saved.purchased_at.isoformat() if saved.purchased_at else None,
                    "recommended_occasions": saved.recommended_occasions or [],
                    "generation_context": saved.generation_context or {},
                    "created_at": saved.created_at.isoformat() if saved.created_at else None,
                }
                for saved, look_name in saved_rows
            ],
            "behavior": {
                "analytics_events": [
                    {
                        "id": str(e.id),
                        "event_type": e.event_type,
                        "channel": e.channel,
                        "product_id": str(e.product_id) if e.product_id else None,
                        "look_id": str(e.look_id) if e.look_id else None,
                        "utm_source": e.utm_source,
                        "utm_medium": e.utm_medium,
                        "utm_campaign": e.utm_campaign,
                        "event_data": e.event_data or {},
                        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    }
                    for e in app_events
                ],
                "website_visits": [
                    {
                        "id": str(v.id),
                        "page_url": v.page_url,
                        "referrer": v.referrer,
                        "device_type": v.device_type,
                        "browser": v.browser,
                        "duration": v.duration,
                        "is_bounce": v.is_bounce,
                        "created_at": v.created_at.isoformat() if v.created_at else None,
                    }
                    for v in website_visits
                ],
            },
        }

    async def get_customer_purchase_history(
        self, customer_id: UUID, limit: int = 20
    ) -> Dict[str, Any]:
        """История покупок конкретного покупателя"""
        customer = await self.db.execute(
            select(User).where(User.id == customer_id)
        )
        user = customer.scalar_one_or_none()
        if not user:
            return {"customer": None, "purchases": [], "total": 0}

        result = await self.db.execute(
            select(PurchaseHistory)
            .where(PurchaseHistory.user_id == customer_id)
            .order_by(desc(PurchaseHistory.purchase_date))
            .limit(limit)
        )
        purchases = result.scalars().all()

        return {
            "customer": {
                "id": str(user.id),
                "full_name": user.full_name,
                "email": user.email,
                "discount_card": user.discount_card_number,
                "segment": user.customer_segment,
                "total_purchases": user.total_purchases,
                "total_spent_rub": round(user.total_spent / 100, 2) if user.total_spent else 0,
            },
            "purchases": [
                {
                    "id": str(p.id),
                    "purchase_date": p.purchase_date.isoformat() if p.purchase_date else None,
                    "product_name": p.product_name,
                    "product_article": p.product_article,
                    "brand": p.brand,
                    "category": p.category,
                    "quantity": p.quantity,
                    "price_rub": round(p.price / 100, 2) if p.price else 0,
                    "total_amount_rub": round(p.total_amount / 100, 2) if p.total_amount else 0,
                }
                for p in purchases
            ],
            "total": len(purchases),
        }

    # ───────────────────────────── ТОВАРЫ ─────────────────────────────

    async def get_product_summary(self) -> Dict[str, Any]:
        """Статистика по товарам: всего, по категориям, по брендам"""
        total = await self.db.execute(
            select(func.count(Product.id)).where(Product.is_active == True)
        )
        total_products = total.scalar() or 0

        # По категориям
        by_category = await self.db.execute(
            select(Product.category, func.count(Product.id).label("cnt"))
            .where(Product.is_active == True)
            .group_by(Product.category)
            .order_by(desc("cnt"))
        )

        # По брендам
        by_brand = await self.db.execute(
            select(Product.brand, func.count(Product.id).label("cnt"))
            .where(Product.is_active == True)
            .group_by(Product.brand)
            .order_by(desc("cnt"))
        )

        # Core assortment
        core = await self.db.execute(
            select(func.count(Product.id)).where(
                and_(Product.is_active == True, Product.is_core_assortment == True)
            )
        )

        return {
            "total_active_products": total_products,
            "core_assortment": core.scalar() or 0,
            "by_category": {row.category or "unknown": row.cnt for row in by_category.all()},
            "by_brand": {row.brand or "unknown": row.cnt for row in by_brand.all()},
        }

    async def get_top_selling_products(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Топ продаваемых товаров из агрегированной аналитики"""
        result = await self.db.execute(
            select(ProductSalesAnalytics)
            .where(
                ProductSalesAnalytics.period_type == "month",
                ProductSalesAnalytics.period_date
                >= date.today().replace(day=1),
            )
            .order_by(desc(ProductSalesAnalytics.total_quantity))
            .limit(limit)
        )
        products = result.scalars().all()

        if not products:
            # Fallback: из order_items через order
            fallback = await self.db.execute(
                select(
                    Product.name,
                    Product.brand,
                    Product.article,
                    func.sum(OrderItem.quantity).label("total_qty"),
                    func.sum(OrderItem.line_total).label("total_rev"),
                )
                .select_from(OrderItem)
                .join(Product, Product.id == OrderItem.product_id)
                .join(Order, Order.id == OrderItem.order_id)
                .where(Order.status.in_(["completed", "paid", "delivered"]))
                .group_by(Product.id, Product.name, Product.brand, Product.article)
                .order_by(desc("total_qty"))
                .limit(limit)
            )
            rows = fallback.all()
            return [
                {
                    "name": r.name,
                    "brand": r.brand,
                    "article": r.article,
                    "total_sold": r.total_qty,
                    "total_revenue_rub": round(r.total_rev / 100, 2) if r.total_rev else 0,
                }
                for r in rows
            ]

        return [
            {
                "product_name": p.product_name,
                "article": p.product_article,
                "brand": p.brand,
                "category": p.category,
                "total_sold": p.total_quantity,
                "total_revenue_rub": round(p.total_revenue / 100, 2) if p.total_revenue else 0,
                "orders_count": p.orders_count,
                "avg_price_rub": round(p.avg_price / 100, 2) if p.avg_price else 0,
            }
            for p in products
        ]

    async def search_products(
        self, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Поиск товаров по названию, артикулу, бренду, категории"""
        pattern = f"%{query}%"
        result = await self.db.execute(
            select(Product)
            .where(
                and_(
                    Product.is_active == True,
                    (
                        Product.name.ilike(pattern)
                        | Product.article.ilike(pattern)
                        | Product.brand.ilike(pattern)
                        | Product.category.ilike(pattern)
                        | Product.vendor_code.ilike(pattern)
                        | Product.barcode.ilike(pattern)
                    ),
                )
            )
            .limit(limit)
        )
        products = result.scalars().all()
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "brand": p.brand,
                "category": p.category,
                "price": p.price,
                "price_rub": round(p.price / 100, 2) if p.price else 0,
                "article": p.article,
                "is_core_assortment": p.is_core_assortment,
                "supports_brand_concept": p.supports_brand_concept,
            }
            for p in products
        ]

    # ───────────────────────────── МАГАЗИНЫ ─────────────────────────────

    async def get_stores_summary(self, days: Optional[int] = None) -> List[Dict[str, Any]]:
        """Список магазинов и их продажи/чеки. Primary source: sales_records.store_id -> stores.external_id."""
        filters = [SalesRecord.store_id.isnot(None)]
        period_label = "all_time"
        visits_by_external_id: Dict[str, Dict[str, Any]] = {}
        visits_by_name: Dict[str, Dict[str, Any]] = {}
        if days:
            since = datetime.combine(date.today() - timedelta(days=days), datetime.min.time())
            until = datetime.combine(date.today(), datetime.min.time())
            filters.append(SalesRecord.sale_date >= since)
            filters.append(SalesRecord.sale_date < until)
            period_label = f"last_{days}_days"

            visits_result = await self.db.execute(
                select(
                    Store.id.label("store_uuid"),
                    Store.external_id.label("external_id"),
                    Store.name.label("store_name"),
                    func.coalesce(func.sum(StoreVisit.visitor_count), 0).label("visitors"),
                    func.coalesce(func.sum(StoreVisit.sales_count), 0).label("visit_sales"),
                    func.coalesce(func.sum(StoreVisit.revenue), 0).label("visit_revenue"),
                    func.max(StoreVisit.date).label("last_visit_date"),
                )
                .select_from(StoreVisit)
                .join(Store, Store.id == StoreVisit.store_id)
                .where(and_(StoreVisit.date >= since, StoreVisit.date < until))
                .group_by(Store.id, Store.external_id, Store.name)
            )
            for row in visits_result.all():
                visit_data = {
                    "store_uuid": str(row.store_uuid),
                    "visitors": int(row.visitors or 0),
                    "visit_sales": int(row.visit_sales or 0),
                    "visit_revenue_rub": round(float(row.visit_revenue or 0), 2),
                    "last_visit_date": row.last_visit_date.isoformat() if row.last_visit_date else None,
                }
                if row.external_id:
                    visits_by_external_id[str(row.external_id)] = visit_data
                if row.store_name:
                    for key in self._store_match_keys(row.store_name):
                        visits_by_name[key] = visit_data

        records_result = await self.db.execute(
            select(
                SalesRecord.store_id.label("store_external_id"),
                func.coalesce(Store.name, SalesRecord.store_id).label("store_name"),
                Store.city.label("city"),
                func.count(SalesRecord.id).label("rows_count"),
                func.count(func.distinct(SalesRecord.document_id)).label("checks_count"),
                func.coalesce(func.sum(SalesRecord.revenue), 0).label("total_revenue"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("items_sold"),
                func.max(SalesRecord.sale_date).label("last_sale_at"),
            )
            .outerjoin(Store, Store.external_id == SalesRecord.store_id)
            .where(and_(*filters))
            .group_by(SalesRecord.store_id, Store.name, Store.city)
            .order_by(desc("total_revenue"))
        )
        rows = records_result.all()
        if rows:
            stores = []
            for row in rows:
                visit_data = visits_by_external_id.get(str(row.store_external_id)) or {}
                if not visit_data:
                    for key in self._store_match_keys(row.store_name):
                        visit_data = visits_by_name.get(key) or {}
                        if visit_data:
                            break
                visitors = int(visit_data.get("visitors") or 0)
                checks_count = int(row.checks_count or 0)
                stores.append({
                    "id": row.store_external_id,
                    "store_id": row.store_external_id,
                    "external_id": row.store_external_id,
                    "name": row.store_name,
                    "city": row.city,
                    "address": None,
                    "records_count": int(row.rows_count or 0),
                    "total_revenue_rub": round(float(row.total_revenue or 0), 2),
                    "total_orders": checks_count,
                    "checks_count": checks_count,
                    "items_sold": float(row.items_sold or 0),
                    "average_check_rub": round(float(row.total_revenue or 0) / checks_count, 2)
                    if checks_count else 0,
                    "visitors": visitors,
                    "visit_sales": int(visit_data.get("visit_sales") or 0),
                    "visit_revenue_rub": visit_data.get("visit_revenue_rub", 0),
                    "revenue_per_visitor_rub": round(float(row.total_revenue or 0) / visitors, 2)
                    if visitors else 0,
                    "visit_conversion_rate": round((checks_count / visitors) * 100, 2) if visitors else 0,
                    "last_visit_date": visit_data.get("last_visit_date"),
                    "last_sale_at": row.last_sale_at.isoformat() if row.last_sale_at else None,
                    "period": period_label,
                    "source": "sales_records",
                })
            return stores

        result = await self.db.execute(select(Store).where(Store.is_active == True))
        stores = result.scalars().all()

        store_list = []
        for s in stores:
            metrics = await self.db.execute(
                select(
                    func.count(SalesMetric.id).label("records"),
                    func.coalesce(func.sum(SalesMetric.revenue), 0).label("total_revenue"),
                    func.coalesce(func.sum(SalesMetric.order_count), 0).label("total_orders"),
                ).where(SalesMetric.store_id == s.id)
            )
            m = metrics.one_or_none()
            visit_data = visits_by_external_id.get(str(s.external_id)) if s.external_id else {}
            if not visit_data:
                for key in self._store_match_keys(s.name):
                    visit_data = visits_by_name.get(key) or {}
                    if visit_data:
                        break
            visitors = int(visit_data.get("visitors") or 0)
            orders_count = int(m.total_orders or 0) if m else 0
            store_list.append({
                "id": str(s.id),
                "name": s.name,
                "city": s.city,
                "address": s.address,
                "total_revenue_rub": round((m.total_revenue or 0), 2),
                "total_orders": orders_count,
                "checks_count": orders_count,
                "visitors": visitors,
                "visit_sales": int(visit_data.get("visit_sales") or 0),
                "visit_revenue_rub": visit_data.get("visit_revenue_rub", 0),
                "revenue_per_visitor_rub": round(float(m.total_revenue or 0) / visitors, 2)
                if visitors and m else 0,
                "visit_conversion_rate": round((orders_count / visitors) * 100, 2) if visitors else 0,
                "last_visit_date": visit_data.get("last_visit_date"),
                "source": "sales_metrics_fallback",
            })

        return store_list

    async def get_inventory_summary(self) -> Dict[str, Any]:
        """Сводка остатков по складам из product_stocks, синхронизированных с 1С."""
        totals_result = await self.db.execute(
            select(
                func.count(ProductStock.id).label("stock_records"),
                func.coalesce(func.sum(ProductStock.quantity), 0).label("total_quantity"),
                func.coalesce(func.sum(ProductStock.available_quantity), 0).label("available_quantity"),
                func.max(ProductStock.last_synced_at).label("last_synced_at"),
                func.coalesce(func.sum(case((ProductStock.available_quantity <= 0, 1), else_=0)), 0).label("critical_count"),
                func.coalesce(func.sum(case((and_(ProductStock.available_quantity > 0, ProductStock.available_quantity <= 3), 1), else_=0)), 0).label("low_count"),
            )
        )
        totals = totals_result.one_or_none()

        by_store_result = await self.db.execute(
            select(
                ProductStock.store_id,
                Store.name.label("store_name"),
                func.count(ProductStock.id).label("sku_count"),
                func.coalesce(func.sum(ProductStock.available_quantity), 0).label("available_quantity"),
                func.coalesce(func.sum(case((ProductStock.available_quantity <= 0, 1), else_=0)), 0).label("critical_count"),
            )
            .outerjoin(Store, Store.external_id == ProductStock.store_id)
            .group_by(ProductStock.store_id, Store.name)
            .order_by(desc("critical_count"))
            .limit(20)
        )

        critical_result = await self.db.execute(
            select(
                Product.name,
                Product.article,
                Product.brand,
                Product.category,
                ProductStock.store_id,
                Store.name.label("store_name"),
                ProductStock.available_quantity,
            )
            .join(Product, Product.id == ProductStock.product_id)
            .outerjoin(Store, Store.external_id == ProductStock.store_id)
            .where(ProductStock.available_quantity <= 0)
            .order_by(Product.name)
            .limit(15)
        )

        return {
            "stock_records": int(totals.stock_records or 0) if totals else 0,
            "total_quantity": float(totals.total_quantity or 0) if totals else 0,
            "available_quantity": float(totals.available_quantity or 0) if totals else 0,
            "critical_count": int(totals.critical_count or 0) if totals else 0,
            "low_count": int(totals.low_count or 0) if totals else 0,
            "last_synced_at": totals.last_synced_at.isoformat() if totals and totals.last_synced_at else None,
            "by_store": [
                {
                    "store_id": row.store_id,
                    "store_name": row.store_name or row.store_id,
                    "sku_count": int(row.sku_count or 0),
                    "available_quantity": float(row.available_quantity or 0),
                    "critical_count": int(row.critical_count or 0),
                }
                for row in by_store_result.all()
            ],
            "critical_products": [
                {
                    "name": row.name,
                    "article": row.article,
                    "brand": row.brand,
                    "category": row.category,
                    "store_id": row.store_id,
                    "store_name": row.store_name or row.store_id,
                    "available_quantity": float(row.available_quantity or 0),
                }
                for row in critical_result.all()
            ],
        }

    async def get_store_visits_summary(self, days: int = 7) -> Dict[str, Any]:
        """Посещения магазинов и конверсия за период."""
        since = datetime.combine(date.today() - timedelta(days=days), datetime.min.time())
        until = datetime.combine(date.today(), datetime.min.time())
        totals_result = await self.db.execute(
            select(
                func.coalesce(func.sum(StoreVisit.visitor_count), 0).label("visitors"),
                func.coalesce(func.sum(StoreVisit.sales_count), 0).label("sales"),
                func.coalesce(func.sum(StoreVisit.revenue), 0).label("revenue"),
                func.max(StoreVisit.date).label("last_visit_date"),
            )
            .where(and_(StoreVisit.date >= since, StoreVisit.date < until))
        )
        totals = totals_result.one_or_none()

        by_store_result = await self.db.execute(
            select(
                Store.name,
                Store.city,
                func.coalesce(func.sum(StoreVisit.visitor_count), 0).label("visitors"),
                func.coalesce(func.sum(StoreVisit.sales_count), 0).label("sales"),
                func.coalesce(func.sum(StoreVisit.revenue), 0).label("revenue"),
            )
            .join(Store, Store.id == StoreVisit.store_id)
            .where(and_(StoreVisit.date >= since, StoreVisit.date < until))
            .group_by(Store.id, Store.name, Store.city)
            .order_by(desc("visitors"))
            .limit(20)
        )

        visitors = int(totals.visitors or 0) if totals else 0
        sales = int(totals.sales or 0) if totals else 0
        return {
            "period": f"last_{days}_days",
            "days": days,
            "date_from": since.date().isoformat(),
            "date_to": (until.date() - timedelta(days=1)).isoformat(),
            "visitors": visitors,
            "sales": sales,
            "revenue_rub": round(float(totals.revenue or 0), 2) if totals else 0,
            "conversion_rate": round((sales / visitors) * 100, 2) if visitors else 0,
            "last_visit_date": totals.last_visit_date.isoformat() if totals and totals.last_visit_date else None,
            "by_store": [
                {
                    "store_name": row.name,
                    "city": row.city,
                    "visitors": int(row.visitors or 0),
                    "sales": int(row.sales or 0),
                    "revenue_rub": round(float(row.revenue or 0), 2),
                    "conversion_rate": round((int(row.sales or 0) / int(row.visitors or 0)) * 100, 2)
                    if int(row.visitors or 0) else 0,
                }
                for row in by_store_result.all()
            ],
        }

    async def get_app_usage_summary(self, days: int = 7) -> Dict[str, Any]:
        """Счетчик действий пользователей в клиентском приложении: экраны, клики и поведение."""
        since = datetime.now() - timedelta(days=days)
        channel_filter = AnalyticsEvent.channel.in_(["mobile_app", "app", "flutter_app"])

        events_result = await self.db.execute(
            select(AnalyticsEvent.event_type, func.count(AnalyticsEvent.id).label("cnt"))
            .where(and_(AnalyticsEvent.timestamp >= since, channel_filter))
            .group_by(AnalyticsEvent.event_type)
            .order_by(desc("cnt"))
        )

        totals_result = await self.db.execute(
            select(
                func.count(AnalyticsEvent.id).label("events"),
                func.count(func.distinct(AnalyticsEvent.session_id)).label("sessions"),
                func.count(func.distinct(AnalyticsEvent.user_id)).label("users"),
            )
            .where(and_(AnalyticsEvent.timestamp >= since, channel_filter))
        )
        totals = totals_result.one_or_none()

        page_url = literal_column("analytics_events.event_data ->> 'page_url'")
        pages_result = await self.db.execute(
            select(page_url.label("page_url"), func.count(AnalyticsEvent.id).label("views"))
            .where(
                and_(
                    AnalyticsEvent.timestamp >= since,
                    channel_filter,
                    AnalyticsEvent.event_type == "page_view",
                )
            )
            .group_by(page_url)
            .order_by(desc("views"))
            .limit(20)
        )

        click_label = literal_column("analytics_events.event_data ->> 'label'")
        clicks_result = await self.db.execute(
            select(click_label.label("label"), func.count(AnalyticsEvent.id).label("clicks"))
            .where(
                and_(
                    AnalyticsEvent.timestamp >= since,
                    channel_filter,
                    AnalyticsEvent.event_type == "ui_click",
                )
            )
            .group_by(click_label)
            .order_by(desc("clicks"))
            .limit(20)
        )

        return {
            "period": f"last_{days}_days",
            "days": days,
            "source": "analytics_events",
            "channel": "mobile_app",
            "status": "available" if totals and int(totals.events or 0) > 0 else "no_data",
            "events": int(totals.events or 0) if totals else 0,
            "sessions": int(totals.sessions or 0) if totals else 0,
            "users": int(totals.users or 0) if totals else 0,
            "events_by_type": {row.event_type: int(row.cnt or 0) for row in events_result.all() if row.event_type},
            "top_pages": [
                {"page_url": row.page_url or "unknown", "views": int(row.views or 0)}
                for row in pages_result.all()
            ],
            "top_clicks": [
                {"label": row.label or "unknown", "clicks": int(row.clicks or 0)}
                for row in clicks_result.all()
            ],
        }

    async def get_website_traffic_summary(self, days: int = 7) -> Dict[str, Any]:
        """Посещаемость сайта: локальный счетчик и, если настроена, Яндекс.Метрика."""
        since = datetime.now() - timedelta(days=days)
        until = datetime.now()

        visits_result = await self.db.execute(
            select(
                func.count(WebsiteVisit.id).label("visits"),
                func.count(func.distinct(WebsiteVisit.session_id)).label("sessions"),
                func.count(func.distinct(WebsiteVisit.user_id)).label("users"),
                func.avg(WebsiteVisit.duration).label("avg_duration"),
                func.sum(case((WebsiteVisit.is_bounce == "yes", 1), else_=0)).label("bounces"),
                func.max(WebsiteVisit.created_at).label("last_visit_at"),
            )
            .where(WebsiteVisit.created_at >= since)
        )
        visits = visits_result.one_or_none()

        page_result = await self.db.execute(
            select(
                WebsiteVisit.page_url,
                func.count(WebsiteVisit.id).label("visits"),
                func.avg(WebsiteVisit.duration).label("avg_duration"),
            )
            .where(WebsiteVisit.created_at >= since)
            .group_by(WebsiteVisit.page_url)
            .order_by(desc("visits"))
            .limit(20)
        )

        event_result = await self.db.execute(
            select(
                AnalyticsEvent.event_type,
                func.count(AnalyticsEvent.id).label("cnt"),
            )
            .where(and_(AnalyticsEvent.timestamp >= since, AnalyticsEvent.channel == "website"))
            .group_by(AnalyticsEvent.event_type)
            .order_by(desc("cnt"))
            .limit(20)
        )

        local_visits = int(visits.visits or 0) if visits else 0
        bounces = int(visits.bounces or 0) if visits else 0
        metrika: Dict[str, Any] = {"status": "not_configured"}
        if os.getenv("YANDEX_METRIKA_COUNTER_ID") and os.getenv("YANDEX_METRIKA_OAUTH_TOKEN"):
            try:
                from app.services.yandex_metrika_service import YandexMetrikaService

                async with YandexMetrikaService() as ym_service:
                    metrika = await asyncio.wait_for(ym_service.get_all_metrics(since, until), timeout=8)
                    metrika["status"] = "available"
            except Exception as e:
                logger.warning("Yandex Metrika summary unavailable: %s", e)
                metrika = {"status": "error", "error": str(e)}

        return {
            "period": f"last_{days}_days",
            "days": days,
            "source": "website_visits + analytics_events + yandex_metrika",
            "status": "available" if local_visits or metrika.get("status") == "available" else "no_data",
            "local": {
                "visits": local_visits,
                "sessions": int(visits.sessions or 0) if visits else 0,
                "users": int(visits.users or 0) if visits else 0,
                "avg_duration_seconds": round(float(visits.avg_duration or 0), 2) if visits else 0,
                "bounce_rate": round((bounces / local_visits) * 100, 2) if local_visits else 0,
                "last_visit_at": visits.last_visit_at.isoformat() if visits and visits.last_visit_at else None,
            },
            "events_by_type": {row.event_type: int(row.cnt or 0) for row in event_result.all() if row.event_type},
            "top_pages": [
                {
                    "page_url": row.page_url,
                    "visits": int(row.visits or 0),
                    "avg_duration_seconds": round(float(row.avg_duration or 0), 2),
                }
                for row in page_result.all()
            ],
            "metrika": metrika,
        }

    async def get_instagram_analytics_summary(self, days: int = 7) -> Dict[str, Any]:
        """Instagram analytics из сохраненных метрик и статус подключения Graph API."""
        since = datetime.now() - timedelta(days=days)
        totals_result = await self.db.execute(
            select(
                func.count(SocialMediaMetric.id).label("records"),
                func.coalesce(func.sum(SocialMediaMetric.likes), 0).label("likes"),
                func.coalesce(func.sum(SocialMediaMetric.comments), 0).label("comments"),
                func.coalesce(func.sum(SocialMediaMetric.views), 0).label("views"),
                func.coalesce(func.sum(SocialMediaMetric.reach), 0).label("reach"),
                func.coalesce(func.avg(SocialMediaMetric.engagement), 0).label("avg_engagement"),
                func.max(SocialMediaMetric.date).label("last_metric_date"),
            )
            .where(and_(SocialMediaMetric.platform == "instagram", SocialMediaMetric.date >= since))
        )
        totals = totals_result.one_or_none()

        posts_result = await self.db.execute(
            select(SocialMediaMetric)
            .where(
                and_(
                    SocialMediaMetric.platform == "instagram",
                    SocialMediaMetric.metric_type == "post",
                    SocialMediaMetric.date >= since,
                )
            )
            .order_by(desc(SocialMediaMetric.engagement), desc(SocialMediaMetric.reach))
            .limit(10)
        )

        records = int(totals.records or 0) if totals else 0
        api_configured = bool(os.getenv("INSTAGRAM_ACCESS_TOKEN") and os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID"))
        return {
            "period": f"last_{days}_days",
            "days": days,
            "source": "social_media_metrics + instagram_graph_api",
            "status": "available" if records else ("configured_no_synced_data" if api_configured else "not_configured_or_no_data"),
            "api_configured": api_configured,
            "records": records,
            "likes": int(totals.likes or 0) if totals else 0,
            "comments": int(totals.comments or 0) if totals else 0,
            "views": int(totals.views or 0) if totals else 0,
            "reach": int(totals.reach or 0) if totals else 0,
            "avg_engagement": round(float(totals.avg_engagement or 0), 2) if totals else 0,
            "last_metric_date": totals.last_metric_date.isoformat() if totals and totals.last_metric_date else None,
            "top_posts": [
                {
                    "post_id": row.post_id,
                    "date": row.date.isoformat() if row.date else None,
                    "likes": row.likes or 0,
                    "comments": row.comments or 0,
                    "views": row.views or 0,
                    "reach": row.reach or 0,
                    "engagement": row.engagement or 0,
                    "caption": ((row.meta_data or {}).get("caption") or "")[:160],
                    "permalink": (row.meta_data or {}).get("permalink"),
                }
                for row in posts_result.scalars().all()
            ],
        }

    async def get_analytics_agent_data_context(self, days: int = 7) -> Dict[str, Any]:
        """Единый контекст данных для AI Analytics."""
        return {
            "offline_store_visits": await self.get_store_visits_summary(days),
            "website_traffic": await self.get_website_traffic_summary(days),
            "mobile_app_behavior": await self.get_app_usage_summary(days),
            "instagram_analytics": await self.get_instagram_analytics_summary(days),
            "sales_metrics": await self.get_sales_metrics_summary(days),
            "generated_at": datetime.now().isoformat(),
        }

    async def get_sales_metrics_summary(self, days: int = 7) -> Dict[str, Any]:
        """Агрегированные продажи и чеки. Primary source: sales_records; sales_metrics как fallback."""
        since = datetime.now() - timedelta(days=days)
        source_status = await self.get_sales_sources_status(days)
        records_result = await self.db.execute(
            select(
                func.coalesce(func.sum(SalesRecord.revenue), 0).label("revenue"),
                func.count(func.distinct(SalesRecord.document_id)).label("checks_count"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("items_sold"),
                func.max(SalesRecord.sale_date).label("last_metric_date"),
                func.count(SalesRecord.id).label("records_count"),
            )
            .where(SalesRecord.sale_date >= since)
        )
        records_row = records_result.one_or_none()
        records_checks = int(records_row.checks_count or 0) if records_row else 0
        if records_checks:
            revenue = float(records_row.revenue or 0)
            return {
                "period": f"last_{days}_days",
                "days": days,
                "revenue_rub": round(revenue, 2),
                "checks_count": records_checks,
                "items_sold": float(records_row.items_sold or 0),
                "average_check_rub": round(revenue / records_checks, 2),
                "last_metric_date": records_row.last_metric_date.isoformat() if records_row.last_metric_date else None,
                "records_count": int(records_row.records_count or 0),
                "source": "sales_records",
                "source_status": source_status,
            }

        result = await self.db.execute(
            select(
                func.coalesce(func.sum(SalesMetric.revenue), 0).label("revenue"),
                func.coalesce(func.sum(SalesMetric.order_count), 0).label("checks_count"),
                func.coalesce(func.sum(SalesMetric.items_sold), 0).label("items_sold"),
                func.max(SalesMetric.date).label("last_metric_date"),
            )
            .where(SalesMetric.date >= since)
        )
        row = result.one_or_none()
        checks_count = int(row.checks_count or 0) if row else 0
        revenue = float(row.revenue or 0) if row else 0.0
        return {
            "period": f"last_{days}_days",
            "days": days,
            "revenue_rub": round(revenue, 2),
            "checks_count": checks_count,
            "items_sold": int(row.items_sold or 0) if row else 0,
            "average_check_rub": round(revenue / checks_count, 2) if checks_count else 0,
            "last_metric_date": row.last_metric_date.isoformat() if row and row.last_metric_date else None,
            "source": "sales_metrics_fallback",
            "source_status": source_status,
        }

    async def get_sales_sources_status(self, days: int = 7) -> Dict[str, Any]:
        """Диагностика свежести и полноты источников продаж для директора."""
        since = datetime.now() - timedelta(days=days)

        records_result = await self.db.execute(
            select(
                func.count(SalesRecord.id).label("rows_count"),
                func.count(func.distinct(SalesRecord.document_id)).label("checks_count"),
                func.coalesce(func.sum(SalesRecord.revenue), 0).label("revenue"),
                func.max(SalesRecord.sale_date).label("last_at"),
            )
            .where(SalesRecord.sale_date >= since)
        )
        records = records_result.one_or_none()

        metrics_result = await self.db.execute(
            select(
                func.count(SalesMetric.id).label("rows_count"),
                func.coalesce(func.sum(SalesMetric.order_count), 0).label("checks_count"),
                func.coalesce(func.sum(SalesMetric.revenue), 0).label("revenue"),
                func.max(SalesMetric.date).label("last_at"),
            )
            .where(SalesMetric.date >= since)
        )
        metrics = metrics_result.one_or_none()

        orders_result = await self.db.execute(
            select(
                func.count(Order.id).label("rows_count"),
                func.coalesce(func.sum(Order.total_amount), 0).label("revenue_cents"),
                func.max(Order.created_at).label("last_at"),
            )
            .where(Order.created_at >= since)
        )
        orders = orders_result.one_or_none()

        visits_result = await self.db.execute(
            select(
                func.count(StoreVisit.id).label("rows_count"),
                func.coalesce(func.sum(StoreVisit.visitor_count), 0).label("visitors"),
                func.coalesce(func.sum(StoreVisit.sales_count), 0).label("sales_count"),
                func.max(StoreVisit.date).label("last_at"),
            )
            .where(StoreVisit.date >= since)
        )
        visits = visits_result.one_or_none()

        return {
            "period": f"last_{days}_days",
            "primary_sales_source": "sales_records",
            "sales_records": {
                "rows_count": int(records.rows_count or 0) if records else 0,
                "checks_count": int(records.checks_count or 0) if records else 0,
                "revenue_rub": round(float(records.revenue or 0), 2) if records else 0,
                "last_at": records.last_at.isoformat() if records and records.last_at else None,
            },
            "sales_metrics": {
                "rows_count": int(metrics.rows_count or 0) if metrics else 0,
                "checks_count": int(metrics.checks_count or 0) if metrics else 0,
                "revenue_rub": round(float(metrics.revenue or 0), 2) if metrics else 0,
                "last_at": metrics.last_at.isoformat() if metrics and metrics.last_at else None,
            },
            "orders": {
                "rows_count": int(orders.rows_count or 0) if orders else 0,
                "revenue_rub": round(float(orders.revenue_cents or 0) / 100, 2) if orders else 0,
                "last_at": orders.last_at.isoformat() if orders and orders.last_at else None,
            },
            "store_visits": {
                "rows_count": int(visits.rows_count or 0) if visits else 0,
                "visitors": int(visits.visitors or 0) if visits else 0,
                "sales_count": int(visits.sales_count or 0) if visits else 0,
                "last_at": visits.last_at.isoformat() if visits and visits.last_at else None,
            },
        }

    # ───────────────────────────── КАМПАНИИ ─────────────────────────────

    async def get_active_campaigns(self) -> List[Dict[str, Any]]:
        """Активные маркетинговые кампании"""
        result = await self.db.execute(
            select(MarketingCampaign)
            .where(MarketingCampaign.status == "active")
            .order_by(desc(MarketingCampaign.created_at))
        )
        campaigns = result.scalars().all()
        return [
            {
                "id": str(c.id),
                "name": c.name,
                "type": c.type,
                "status": c.status,
                "start_date": c.start_date.isoformat() if c.start_date else None,
                "end_date": c.end_date.isoformat() if c.end_date else None,
                "budget_rub": c.budget,
                "channels": c.channels or [],
                "metrics": c.metrics or {},
            }
            for c in campaigns
        ]

    # ───────────────────────────── УНИВЕРСАЛЬНЫЙ МЕТОД ─────────────────────────────

    async def get_general_stats(self) -> Dict[str, Any]:
        """Сводка всех основных метрик для быстрого ответа"""
        today = await self.get_today_sales()
        week = await self.get_sales_for_period(7)
        customers = await self.get_customer_summary()
        products = await self.get_product_summary()
        inventory = await self.get_inventory_summary()
        visits = await self.get_store_visits_summary(7)
        sales_metrics = await self.get_sales_metrics_summary(7)
        stores_sales = await self.get_stores_summary(7)

        return {
            "today": today,
            "last_7_days": week,
            "customers": customers,
            "products": products,
            "inventory": inventory,
            "store_visits": visits,
            "sales_metrics": sales_metrics,
            "stores_sales": stores_sales,
            "generated_at": datetime.now().isoformat(),
        }

    DATA_TOOLS_DESCRIPTION = """
Доступные инструменты для работы с данными:

1. **get_general_stats()** — Общая сводка: продажи сегодня, за неделю, статистика покупателей, товаров.
2. **get_today_sales()** — Продажи сегодня: количество заказов, выручка, товаров продано.
3. **get_sales_for_period(days)** — Продажи за N дней: заказы, выручка, средний чек, уникальные покупатели.
4. **get_daily_sales_trend(days)** — Ежедневный тренд продаж за N дней.
5. **get_recent_orders(limit)** — Последние заказы (статус, сумма, покупатель).
6. **get_customer_summary()** — Статистика покупателей: всего, по сегментам, новые, баллы лояльности.
7. **find_customer(query, search_by)** — Поиск покупателя (по карте, email, телефону, имени).
8. **get_customer_purchase_history(customer_id)** — История покупок конкретного покупателя.
8a. **get_customer_data_capabilities()** — Какие данные доступны по покупателям: профиль, баллы, покупки, сообщения, стилист, поведение.
8b. **get_customer_full_profile(query)** — Полный паспорт покупателя по телефону/email/карте/UUID/имени: профиль, сегменты, RFM, баллы и транзакции, история покупок, старые сообщения, переписка со стилистом, сохраненные образы, события приложения и сайта.
9. **get_product_summary()** — Статистика товаров: всего, по категориям, по брендам.
10. **get_top_selling_products(limit)** — Топ продаваемых товаров.
11. **search_products(query)** — Поиск товаров по названию, артикулу, бренду.
12. **get_stores_summary()** — Список магазинов с продажами.
13. **get_active_campaigns()** — Активные маркетинговые кампании.
14. **get_inventory_summary()** — Остатки по складам из 1С: критические остатки, low stock, дата синхронизации.
15. **get_store_visits_summary(days)** — Посещения магазинов, продажи и конверсия.
16. **get_sales_metrics_summary(days)** — Чеки, выручка, средний чек и товары из sales_metrics / 1С.
17. **get_website_traffic_summary(days)** — Посещаемость сайта: локальные website_visits, события website и Яндекс.Метрика, если настроена.
18. **get_app_usage_summary(days)** — Поведенческие факторы клиентского Flutter-приложения: экраны, клики, просмотры товаров/образов.
19. **get_instagram_analytics_summary(days)** — Instagram: сохраненные метрики постов, охваты, реакции и статус Graph API.
20. **get_analytics_agent_data_context(days)** — Единый пакет данных для AI Analytics: офлайн-посещения, сайт, приложение, Instagram и продажи.

ВАЖНО: Используй эти инструменты, когда пользователь спрашивает о данных. 
Не говори «у меня нет доступа к данным», «нет подключения к CRM», «не вижу продажи/остатки/чеки/посещения» — используй инструменты выше для получения точной информации.
"""
