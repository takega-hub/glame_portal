import logging
import re
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from app.models.user import User
from app.services.onec_customers_service import OneCCustomersService

logger = logging.getLogger(__name__)


class CustomerCityRefreshService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.onec_service: Optional[OneCCustomersService] = None

    async def _get_onec_service(self) -> OneCCustomersService:
        if not self.onec_service:
            self.onec_service = OneCCustomersService()
        return self.onec_service

    @staticmethod
    def _extract_city(customer_data: Optional[Dict[str, Any]]) -> Optional[str]:
        if not customer_data:
            return None

        city = customer_data.get("Город") or customer_data.get("City") or customer_data.get("НаселенныйПункт")

        if not city:
            address_data = customer_data.get("Состав") or customer_data.get("Адрес") or customer_data.get("Address")
            if isinstance(address_data, dict):
                address_rf = address_data.get("АдресРФ") or address_data.get("Адрес")
                if isinstance(address_rf, dict):
                    city = (
                        address_rf.get("Город")
                        or address_rf.get("City")
                        or address_rf.get("НаселенныйПункт")
                    )
                if not city:
                    city = (
                        address_data.get("Город")
                        or address_data.get("City")
                        or address_data.get("НаселенныйПункт")
                    )
            elif isinstance(address_data, list) and address_data:
                first_item = address_data[0]
                if isinstance(first_item, dict):
                    address_rf = first_item.get("АдресРФ") or first_item.get("Адрес")
                    if isinstance(address_rf, dict):
                        city = (
                            address_rf.get("Город")
                            or address_rf.get("City")
                            or address_rf.get("НаселенныйПункт")
                        )
                    if not city:
                        city = (
                            first_item.get("Город")
                            or first_item.get("City")
                            or first_item.get("НаселенныйПункт")
                        )

        if not city:
            contact_info = customer_data.get("КонтактнаяИнформация") or customer_data.get("ContactInfo")
            if isinstance(contact_info, list):
                for ci in contact_info:
                    if not isinstance(ci, dict):
                        continue
                    ci_type = ci.get("Тип") or ci.get("Type") or ""
                    if "Адрес" in str(ci_type) or "Address" in str(ci_type):
                        city = ci.get("Город") or ci.get("City")
                        if not city:
                            presentation = ci.get("Представление") or ci.get("Presentation")
                            if isinstance(presentation, str):
                                m = re.search(r"(?:г\.?|город)\s+([А-ЯЁA-Z][а-яёa-z\- ]+)", presentation)
                                if m:
                                    city = m.group(1).strip()
                        if city:
                            break
            elif isinstance(contact_info, dict):
                city = contact_info.get("Город") or contact_info.get("City")

        if not city:
            s = customer_data.get("Представление") or customer_data.get("Комментарий") or ""
            if isinstance(s, str):
                for known in ["Симферополь", "Севастополь", "Ялта", "Евпатория", "Керчь", "Феодосия", "Алушта"]:
                    if known.lower() in s.lower():
                        city = known
                        break

        return city if city else None

    async def refresh_for_user(self, user_id: UUID) -> Dict[str, int]:
        onec = await self._get_onec_service()
        stmt = select(User).where(User.id == user_id, User.is_customer == True)
        res = await self.db.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            return {"processed": 0, "updated": 0, "skipped": 0, "errors": 0}
        try:
            customer_data = None
            if user.customer_id_1c:
                customer_data = await onec.fetch_customer_details(user.customer_id_1c)
            city = self._extract_city(customer_data)
            if city and city != getattr(user, "city", None):
                user.city = city
                await self.db.commit()
                return {"processed": 1, "updated": 1, "skipped": 0, "errors": 0}
            return {"processed": 1, "updated": 0, "skipped": 1, "errors": 0}
        except Exception as e:
            logger.error("city refresh error for %s: %s", user_id, e)
            await self.db.rollback()
            return {"processed": 1, "updated": 0, "skipped": 0, "errors": 1}

    async def refresh_all(self, limit: int = 1000, only_empty: bool = True) -> Dict[str, int]:
        onec = await self._get_onec_service()
        stats = {"processed": 0, "updated": 0, "skipped": 0, "errors": 0}
        offset = 0
        batch = 200
        while stats["processed"] < limit:
            conditions = [User.is_customer == True]
            if only_empty:
                conditions.append(User.city.is_(None))
            stmt = select(User).where(and_(*conditions)).order_by(User.created_at).offset(offset).limit(min(batch, limit - stats["processed"]))
            res = await self.db.execute(stmt)
            users = res.scalars().all()
            if not users:
                break
            for u in users:
                try:
                    customer_data = None
                    if u.customer_id_1c:
                        customer_data = await onec.fetch_customer_details(u.customer_id_1c)
                    city = self._extract_city(customer_data)
                    if city and city != getattr(u, "city", None):
                        u.city = city
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                    stats["processed"] += 1
                except Exception as e:
                    logger.error("city refresh error for %s: %s", u.id, e)
                    stats["errors"] += 1
                    stats["processed"] += 1
            await self.db.commit()
            offset += len(users)
        return stats
