"""
CRM interaction attribution.

Marks customer interactions as positive when a purchase appears shortly after the
contact. The result is stored in CustomerMessage.payload so the messages tab can
show both the original interaction and its business outcome.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_message import CustomerMessage
from app.models.purchase_history import PurchaseHistory


class CrmInteractionAttributionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _purchase_key(purchase: PurchaseHistory) -> str:
        if purchase.document_id_1c:
            return f"doc:{purchase.document_id_1c}"
        return f"row:{purchase.id}"

    @classmethod
    def _summarize_purchases(
        cls,
        purchases: list[PurchaseHistory],
        *,
        window_end: datetime,
    ) -> dict[str, Any]:
        grouped: dict[str, dict[str, Any]] = {}
        for purchase in purchases:
            key = cls._purchase_key(purchase)
            item = grouped.setdefault(
                key,
                {
                    "purchase_ids": [],
                    "document_id_1c": purchase.document_id_1c,
                    "purchase_date": purchase.purchase_date,
                    "store_id_1c": purchase.store_id_1c,
                    "total_amount": 0,
                    "items_count": 0,
                },
            )
            item["purchase_ids"].append(str(purchase.id))
            item["items_count"] += 1
            item["total_amount"] += int(purchase.total_amount or 0)
            if purchase.purchase_date and (
                not item["purchase_date"] or purchase.purchase_date < item["purchase_date"]
            ):
                item["purchase_date"] = purchase.purchase_date
            if not item["store_id_1c"] and purchase.store_id_1c:
                item["store_id_1c"] = purchase.store_id_1c

        docs = sorted(grouped.values(), key=lambda item: item["purchase_date"])
        total_amount = sum(max(0, int(item["total_amount"] or 0)) for item in docs)
        now = datetime.now(timezone.utc)
        if window_end.tzinfo is None:
            now = now.replace(tzinfo=None)
        converted = total_amount > 0
        return {
            "converted": converted,
            "status": "positive" if converted else ("pending" if now < window_end else "no_purchase_14d"),
            "purchase_count": len([item for item in docs if int(item["total_amount"] or 0) > 0]),
            "revenue_kopecks": total_amount,
            "revenue_rub": round(total_amount / 100, 2),
            "first_purchase_at": docs[0]["purchase_date"].isoformat() if docs and docs[0]["purchase_date"] else None,
            "purchases": [
                {
                    **item,
                    "purchase_date": item["purchase_date"].isoformat() if item["purchase_date"] else None,
                }
                for item in docs[:20]
            ],
        }

    async def update_purchase_conversions(
        self,
        *,
        window_days: int = 14,
        user_ids: list[UUID] | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        stmt = (
            select(CustomerMessage)
            .where(CustomerMessage.created_at.isnot(None))
            .order_by(CustomerMessage.created_at.asc())
        )
        if user_ids:
            stmt = stmt.where(CustomerMessage.user_id.in_(user_ids))

        messages = (await self.db.execute(stmt)).scalars().all()
        updated = 0
        converted = 0
        total_revenue = 0

        for message in messages:
            is_crm_call = message.event_type == "crm_call" or (message.payload or {}).get("source") == "seller_crm_task"
            has_interaction = is_crm_call or message.status in {"sent", "delivered", "completed"} or bool(message.sent_at)
            payload = dict(message.payload or {})
            if not has_interaction:
                result = {
                    "window_days": window_days,
                    "window_start": None,
                    "window_end": None,
                    "converted": False,
                    "status": "not_interacted",
                    "purchase_count": 0,
                    "revenue_kopecks": 0,
                    "revenue_rub": 0,
                    "first_purchase_at": None,
                    "purchases": [],
                }
                if payload.get("conversion_result") != result:
                    payload["conversion_result"] = result
                    payload["interaction_result"] = "not_interacted"
                    message.payload = payload
                    updated += 1
                continue

            start = message.sent_at or message.created_at
            if not start:
                continue
            end = start + timedelta(days=window_days)
            purchases = (
                await self.db.execute(
                    select(PurchaseHistory)
                    .where(
                        and_(
                            PurchaseHistory.user_id == message.user_id,
                            PurchaseHistory.purchase_date >= start,
                            PurchaseHistory.purchase_date <= end,
                            PurchaseHistory.total_amount > 0,
                        )
                    )
                    .order_by(PurchaseHistory.purchase_date.asc())
                )
            ).scalars().all()

            summary = self._summarize_purchases(list(purchases), window_end=end)
            result = {
                "window_days": window_days,
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                **summary,
            }

            if payload.get("conversion_result") == result:
                continue

            payload["conversion_result"] = result
            if result["converted"]:
                payload["interaction_result"] = "positive_purchase_after_contact"
                converted += 1
                total_revenue += int(result["revenue_kopecks"] or 0)
            elif result["status"] == "pending":
                payload["interaction_result"] = "pending_purchase_window"
            else:
                payload["interaction_result"] = "no_purchase_after_contact_14d"

            message.payload = payload
            updated += 1

        if commit:
            await self.db.commit()

        return {
            "messages_scanned": len(messages),
            "updated": updated,
            "converted": converted,
            "total_revenue_rub": round(total_revenue / 100, 2),
            "window_days": window_days,
        }
