"""Birthday CRM helpers for upcoming customer birthday cards.

The module is intentionally side-effect free for CRM output: it builds manager
cards and draft congratulation text, but never sends messages to customers.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from typing import TYPE_CHECKING

from app.services.sales_record_filters import is_analytics_eligible_product

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
else:
    AsyncSession = Any

ONE_HOUR_SECONDS = 60 * 60


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _customer_display_name(customer: Any) -> str:
    full_name = (getattr(customer, "full_name", None) or "").strip()
    if full_name:
        return full_name
    return (getattr(customer, "phone", None) or getattr(customer, "email", None) or "Клиент").strip()


def _first_name(customer: Any) -> str:
    name = _customer_display_name(customer)
    if name and name != "Клиент":
        return name.split()[0]
    return ""


def _receipt_doc_id(line: Any) -> str:
    return str(getattr(line, "document_id_1c", None) or getattr(line, "id", None) or "")


def _line_date(line: Any) -> datetime:
    value = getattr(line, "purchase_date", None)
    if not isinstance(value, datetime):
        return datetime.combine(date.min, time.min, tzinfo=timezone.utc)
    return _as_aware_utc(value)


def _line_amount(line: Any) -> int:
    try:
        return int(getattr(line, "total_amount", 0) or 0)
    except Exception:
        return 0


def _is_eligible_purchase_line(line: Any) -> bool:
    return is_analytics_eligible_product(
        product_name=getattr(line, "product_name", None),
        product_category=getattr(line, "category", None),
        product_article=getattr(line, "product_article", None),
        product_id=getattr(line, "product_id_1c", None) or getattr(line, "product_id", None),
        total_amount_kopecks=_line_amount(line),
    )


def next_birthday_date(birth_date: date, today: Optional[date] = None) -> date:
    """Return the next calendar birthday date for a stored birth date."""
    today = today or date.today()
    try:
        candidate = birth_date.replace(year=today.year)
    except ValueError:
        # 29 February: use 28 February in non-leap years for operational CRM.
        candidate = date(today.year, 2, 28)
    if candidate < today:
        try:
            candidate = birth_date.replace(year=today.year + 1)
        except ValueError:
            candidate = date(today.year + 1, 2, 28)
    return candidate


def days_until_birthday(birth_date: date, today: Optional[date] = None) -> int:
    return (next_birthday_date(birth_date, today) - (today or date.today())).days


def is_birthday_within_window(birth_date: Optional[date], today: Optional[date] = None, days_ahead: int = 3) -> bool:
    if not birth_date:
        return False
    return 0 <= days_until_birthday(birth_date, today) <= days_ahead


def calculate_real_purchase_profile(purchase_lines: Iterable[Any]) -> Dict[str, Any]:
    """Calculate real customer checks from receipt lines.

    Rules:
    - exclude accessory/supplementary materials from totals and check quality;
    - group lines by original receipt/document;
    - merge receipt documents of one customer when they are within one hour;
    - count/sum only resulting real receipt bundles.
    """
    lines = list(purchase_lines or [])
    eligible_lines = [line for line in lines if _is_eligible_purchase_line(line)]
    excluded_accessory_amount = sum(_line_amount(line) for line in lines if not _is_eligible_purchase_line(line))

    by_doc: Dict[str, List[Any]] = defaultdict(list)
    for line in eligible_lines:
        by_doc[_receipt_doc_id(line)].append(line)

    receipts: List[Dict[str, Any]] = []
    for doc_id, doc_lines in by_doc.items():
        dates = [_line_date(line) for line in doc_lines if getattr(line, "purchase_date", None)]
        purchase_date = min(dates) if dates else datetime.combine(date.min, time.min, tzinfo=timezone.utc)
        total_amount = sum(_line_amount(line) for line in doc_lines)
        if total_amount <= 0:
            continue
        receipts.append(
            {
                "document_ids": [doc_id] if doc_id else [],
                "purchase_date": purchase_date.isoformat(),
                "_dt": purchase_date,
                "total_amount": total_amount,
                "items_count": sum(int(getattr(line, "quantity", 1) or 1) for line in doc_lines),
                "item_names": [getattr(line, "product_name", None) for line in doc_lines if getattr(line, "product_name", None)],
            }
        )

    receipts.sort(key=lambda receipt: receipt["_dt"])
    bundles: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for receipt in receipts:
        if current is None:
            current = dict(receipt)
            continue
        gap = (receipt["_dt"] - current["_dt"]).total_seconds()
        if 0 <= gap <= ONE_HOUR_SECONDS:
            current["document_ids"].extend(receipt["document_ids"])
            current["total_amount"] += receipt["total_amount"]
            current["items_count"] += receipt["items_count"]
            current["item_names"].extend(receipt["item_names"])
            # keep first purchase_date as bundle start
        else:
            bundles.append(current)
            current = dict(receipt)
    if current is not None:
        bundles.append(current)

    for bundle in bundles:
        bundle.pop("_dt", None)
        bundle["document_ids"] = [doc for doc in dict.fromkeys(bundle["document_ids"]) if doc]

    total_spent = sum(bundle["total_amount"] for bundle in bundles)
    real_count = len(bundles)
    average = total_spent // real_count if real_count else 0
    high_quality_checks = sum(1 for bundle in bundles if bundle["total_amount"] >= 15_000_00)

    return {
        "real_receipts_count": real_count,
        "real_total_spent": total_spent,
        "average_receipt": average,
        "high_quality_checks": high_quality_checks,
        "excluded_accessory_amount": excluded_accessory_amount,
        "receipt_bundles": bundles,
    }


def segment_customer_for_birthday(profile: Dict[str, Any]) -> str:
    total = int(profile.get("real_total_spent") or 0)
    count = int(profile.get("real_receipts_count") or 0)
    high_quality = int(profile.get("high_quality_checks") or 0)
    average = int(profile.get("average_receipt") or 0)
    if total >= 100_000_00 or high_quality >= 3 or average >= 50_000_00:
        return "VIP"
    if total >= 50_000_00 or high_quality >= 2 or average >= 25_000_00:
        return "Premium"
    if total >= 15_000_00 or count >= 2:
        return "Core"
    if count >= 1:
        return "New"
    return "No purchases"


def recommend_birthday_bonus(segment: str, profile: Dict[str, Any], loyalty_points: int = 0) -> Dict[str, Any]:
    if segment == "VIP":
        return {
            "type": "manager_gesture",
            "title": "Персональный подарок + VIP-бонус по согласованию",
            "description": "Предложить цветы/премиальный комплимент и индивидуальный бонус. Требуется подтверждение Елены/менеджера.",
            "requires_approval": True,
        }
    if segment == "Premium":
        return {
            "type": "bonus_points",
            "title": "Повышенный birthday-бонус 7–10%",
            "description": "Начислить вручную после одобрения менеджера; не отправлять автоматически.",
            "requires_approval": True,
        }
    if segment == "Core":
        return {
            "type": "bonus_points",
            "title": "Birthday-бонус 5% или персональная подборка",
            "description": "Мягкий повод вернуться за украшением к дню рождения.",
            "requires_approval": True,
        }
    if segment == "New":
        return {
            "type": "personal_selection",
            "title": "Комплимент к следующей покупке",
            "description": "Сделать акцент на внимании и персональной подборке, без агрессивной скидки.",
            "requires_approval": True,
        }
    return {
        "type": "greeting_only",
        "title": "Теплое поздравление без скидочного давления",
        "description": "Нет реальных чеков для бонусной сегментации; предложить персональную помощь стилиста.",
        "requires_approval": True,
    }


def build_draft_message(customer: Any, segment: str, bonus: Dict[str, Any]) -> str:
    first = _first_name(customer)
    greeting_name = f", {first}" if first else ""
    if segment == "VIP":
        return (
            f"Здравствуйте{greeting_name}! Команда GLAME поздравляет вас с днем рождения. "
            "Мы подготовили для вас персональный комплимент и будем рады подобрать украшение под ваше настроение и образ. "
            "Если удобно, напишите нам — стилист GLAME все организует."
        )
    if segment in {"Premium", "Core"}:
        return (
            f"Здравствуйте{greeting_name}! Поздравляем вас с днем рождения от GLAME ✨ "
            f"Для вас подготовлен {bonus.get('title', 'персональный birthday-бонус')}. "
            "Будем рады помочь выбрать украшение, которое станет красивым акцентом вашего праздника."
        )
    return (
        f"Здравствуйте{greeting_name}! GLAME поздравляет вас с днем рождения ✨ "
        "Желаем красоты, легкости и ярких моментов. Если захотите подобрать украшение к празднику, наш стилист с удовольствием поможет."
    )


def build_birthday_crm_card(customer: Any, purchase_lines: Iterable[Any], today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    profile = calculate_real_purchase_profile(purchase_lines)
    segment = segment_customer_for_birthday(profile)
    bonus = recommend_birthday_bonus(segment, profile, int(getattr(customer, "loyalty_points", 0) or 0))
    birth_date = getattr(customer, "birth_date", None)
    next_birthday = next_birthday_date(birth_date, today) if birth_date else None
    card = {
        "customer_id": str(getattr(customer, "id", "")),
        "full_name": getattr(customer, "full_name", None),
        "phone": getattr(customer, "phone", None),
        "email": getattr(customer, "email", None),
        "birth_date": birth_date.isoformat() if birth_date else None,
        "next_birthday": next_birthday.isoformat() if next_birthday else None,
        "days_until_birthday": (next_birthday - today).days if next_birthday else None,
        "crm_segment": segment,
        "stored_customer_segment": getattr(customer, "customer_segment", None),
        "loyalty_points": int(getattr(customer, "loyalty_points", 0) or 0),
        "recommended_bonus": bonus,
        "draft_message": build_draft_message(customer, segment, bonus),
        "auto_send": False,
        "status": "draft",
        **profile,
    }
    return card


class BirthdayCrmService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_upcoming_cards(self, today: Optional[date] = None, days_ahead: int = 3, limit: int = 100) -> Dict[str, Any]:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.models.purchase_history import PurchaseHistory
        from app.models.user import User

        today = today or date.today()
        users_result = await self.db.execute(
            select(User)
            .where(User.is_customer == True, User.birth_date.isnot(None))
            .order_by(User.birth_date)
        )
        users = [u for u in users_result.scalars().all() if is_birthday_within_window(u.birth_date, today, days_ahead)]
        users = sorted(users, key=lambda u: days_until_birthday(u.birth_date, today))[:limit]

        cards: List[Dict[str, Any]] = []
        for user in users:
            purchases_result = await self.db.execute(
                select(PurchaseHistory)
                .options(selectinload(PurchaseHistory.product))
                .where(PurchaseHistory.user_id == user.id)
                .order_by(PurchaseHistory.purchase_date)
            )
            cards.append(build_birthday_crm_card(user, purchases_result.scalars().all(), today=today))

        return {
            "today": today.isoformat(),
            "days_ahead": days_ahead,
            "total": len(cards),
            "auto_send": False,
            "cards": cards,
        }
