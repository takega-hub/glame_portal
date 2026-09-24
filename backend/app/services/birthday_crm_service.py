"""Birthday CRM helpers for upcoming customer birthday cards.

The module builds manager cards, CRM tasks and, for certificate tiers, issues
an electronic GLAME certificate. Customer SMS auto-send is disabled for birthday
CRM: texts are prepared for manager review only.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.services.sales_record_filters import is_analytics_eligible_product
from app.services.store_aliases import MEGANOM_TO_MRIYA_START_DATE, effective_store_name

CRM_BIRTHDAY_SOURCE = "birthday_crm"
CRM_BIRTHDAY_CAMPAIGN_ID = "birthday-greetings"
CRM_BIRTHDAY_CAMPAIGN_NAME = "Поздравление с ДР"
DEFAULT_BIRTHDAY_DAYS_AHEAD = 3
LEGACY_MEGANOM_MRIYA_START_DATE = MEGANOM_TO_MRIYA_START_DATE
BIRTHDAY_CERTIFICATE_AMOUNT_KOPECKS = 5_000_00
BIRTHDAY_CERTIFICATE_VALIDITY_DAYS = 30
BIRTHDAY_CERTIFICATE_SMS_TIMEZONE = ZoneInfo("Europe/Moscow")
BIRTHDAY_CERTIFICATE_SMS_START_HOUR = 10
BIRTHDAY_CERTIFICATE_SMS_END_HOUR = 18

BIRTHDAY_STORE_MANAGER_NAMES = {
    "трк центрум": "Бешлиева Аджере Айдеровна",
    "центрум": "Бешлиева Аджере Айдеровна",
    "мрия": "Рогалевич Ирина Евгеньевна",
    "симферополь": "Бешлиева Аджере Айдеровна",
    "ялта": "Рогалевич Ирина Евгеньевна",
}

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


def _crm_display_store_name(value: Optional[str]) -> Optional[str]:
    return effective_store_name(value, date.today())


def _crm_customer_store_name(customer: Any) -> Optional[str]:
    return effective_store_name(
        getattr(customer, "preferred_store_name", None)
        or getattr(customer, "secondary_store_name", None)
        or getattr(customer, "city", None),
        date.today(),
        getattr(customer, "preferred_store_external_id", None),
    )


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
    """Return the approved birthday gift rule based on real lifetime spend.

    ``segment`` and ``loyalty_points`` are kept for API compatibility, but the
    birthday gift itself is now calculated only from ``real_total_spent``.
    Bonus-point tiers are separated from certificate/service-action tiers so
    100k+ customers never enter the bonus-accrual flow.
    """
    total = int(profile.get("real_total_spent") or 0)
    if total >= 300_000_00:
        return {
            "type": "gift_certificate",
            "title": "Сертификат GLAME 5 000 ₽ + личный звонок + цветы",
            "description": "VIP-сценарий: сертификат GLAME, личный звонок и согласованная передача цветов. Не начислять бонусные баллы.",
            "bonus_points": None,
            "gift_certificate": {"amount_kopecks": BIRTHDAY_CERTIFICATE_AMOUNT_KOPECKS},
            "certificate_kopecks": BIRTHDAY_CERTIFICATE_AMOUNT_KOPECKS,
            "service_actions": ["personal_call", "flowers"],
            "requires_approval": True,
        }
    if total >= 100_000_00:
        return {
            "type": "gift_certificate",
            "title": "Сертификат GLAME 5 000 ₽ + личный звонок",
            "description": "Сервисный сценарий: сертификат GLAME и личный звонок. Не начислять бонусные баллы.",
            "bonus_points": None,
            "gift_certificate": {"amount_kopecks": BIRTHDAY_CERTIFICATE_AMOUNT_KOPECKS},
            "certificate_kopecks": BIRTHDAY_CERTIFICATE_AMOUNT_KOPECKS,
            "service_actions": ["personal_call"],
            "requires_approval": True,
        }
    if total >= 50_000_00:
        points = 2000
    elif total >= 20_000_00:
        points = 1000
    else:
        points = 500
    return {
        "type": "bonus_points",
        "title": f"{points:,}".replace(",", " ") + " бонусов",
        "description": "Бонусные баллы ко дню рождения; автосообщение клиенту не отправляется.",
        "bonus_points": points,
        "gift_certificate": None,
        "certificate_kopecks": None,
        "service_actions": [],
        "requires_approval": False,
    }


def build_draft_message(customer: Any, segment: str, bonus: Dict[str, Any]) -> str:
    first = _first_name(customer)
    greeting_name = f", {first}" if first else ""
    if bonus.get("type") == "gift_certificate":
        return (
            f"Здравствуйте{greeting_name}! Команда GLAME поздравляет вас с днем рождения ✨ "
            f"Для вас подготовлен {bonus.get('title', 'сертификат GLAME')}. "
            "Менеджер GLAME свяжется лично, чтобы согласовать удобный формат поздравления."
        )
    if bonus.get("type") == "bonus_points":
        return (
            f"Здравствуйте{greeting_name}! Поздравляем вас с днем рождения от GLAME ✨ "
            f"Для вас подготовлен подарок — {bonus.get('title', 'бонусы')} на бонусный счёт. "
            "Будем рады помочь выбрать украшение, которое станет красивым акцентом вашего праздника."
        )
    return (
        f"Здравствуйте{greeting_name}! GLAME поздравляет вас с днем рождения ✨ "
        "Желаем красоты, легкости и ярких моментов. Если захотите выбрать украшение к празднику, наш стилист с удовольствием поможет."
    )


def _format_bonus_valid_until(next_birthday: date) -> str:
    # D−3 is the communication/accrual start, not the gift validity period.
    # Birthday bonus points are valid for 30 calendar days from the birthday.
    return (next_birthday + timedelta(days=30)).strftime("%d.%m.%Y")


def _format_certificate_valid_until(next_birthday: date) -> str:
    return (next_birthday + timedelta(days=BIRTHDAY_CERTIFICATE_VALIDITY_DAYS)).strftime("%d.%m.%Y")


def _certificate_expires_at_for_birthday(next_birthday: date) -> datetime:
    return datetime.combine(
        next_birthday + timedelta(days=BIRTHDAY_CERTIFICATE_VALIDITY_DAYS),
        time.min,
        tzinfo=timezone.utc,
    )


def _certificate_expires_in_days(today: date, next_birthday: date) -> int:
    # D−3 is the start of communication/accrual, not the gift validity period.
    return max(1, (next_birthday - today).days + BIRTHDAY_CERTIFICATE_VALIDITY_DAYS)


def _format_certificate_expires_at(cert: Any, fallback_birthday: date) -> str:
    expires_at = getattr(cert, "expires_at", None)
    if isinstance(expires_at, datetime):
        return expires_at.astimezone(timezone.utc).strftime("%d.%m.%Y")
    return _format_certificate_valid_until(fallback_birthday)


def _birthday_certificate_sms_window(now: Optional[datetime] = None) -> Dict[str, Any]:
    now_msk = (now or datetime.now(timezone.utc)).astimezone(BIRTHDAY_CERTIFICATE_SMS_TIMEZONE)
    starts_at = now_msk.replace(
        hour=BIRTHDAY_CERTIFICATE_SMS_START_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    ends_at = now_msk.replace(
        hour=BIRTHDAY_CERTIFICATE_SMS_END_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    return {
        "timezone": "Europe/Moscow",
        "start_hour": BIRTHDAY_CERTIFICATE_SMS_START_HOUR,
        "end_hour": BIRTHDAY_CERTIFICATE_SMS_END_HOUR,
        "now": now_msk.isoformat(),
        "allowed": starts_at <= now_msk < ends_at,
    }


def _birthday_certificate_sms_text(customer: Any, cert: Any, pin: str, expires_at_text: str) -> str:
    name = _first_name(customer) or _customer_display_name(customer)
    amount = int(getattr(cert, "nominal_amount", 0) or 0) // 100
    template = os.getenv("CRM_BIRTHDAY_CERTIFICATE_SMS_TEMPLATE", "").strip()
    if template:
        return template.format(
            name=name,
            amount=amount,
            amount_rub=f"{amount:,}".replace(",", " "),
            number=getattr(cert, "number", ""),
            pin=pin,
            expires_at=expires_at_text,
        )
    amount_text = f"{amount:,}".replace(",", " ")
    return (
        f"{name}, здравствуйте!\n\n"
        "У Вас совсем скоро день рождения — начинается новый личный год, со своими планами, "
        "событиями, желаниями и, надеемся, красивыми переменами.\n\n"
        f"К этой дате мы хотим порадовать Вас подарком от GLAME — электронным сертификатом на {amount_text} ₽.\n\n"
        f"Ваш сертификат: № {getattr(cert, 'number', '')}\n"
        f"Действует до {expires_at_text}.\n\n"
        "Пусть в новом году жизни будет больше того, что действительно Ваше — людей, впечатлений, "
        "решений и вещей, в которых Вы чувствуете себя собой.\n\n"
        "А если захочется начать его с нового украшения, мы рядом и поможем с выбором в магазине "
        "или дистанционно.\n\n"
        "С уважением,\n"
        "команда GLAME"
    )


def birthday_tier(profile: Dict[str, Any]) -> Dict[str, Any]:
    total = int(profile.get("real_total_spent") or 0)
    if total >= 300_000_00:
        return {
            "code": "vip_300_plus",
            "title": "VIP 300 000 ₽+",
            "channel": "call",
            "certificate_kopecks": BIRTHDAY_CERTIFICATE_AMOUNT_KOPECKS,
            "gift_certificate": {"amount_kopecks": BIRTHDAY_CERTIFICATE_AMOUNT_KOPECKS},
            "certificate_validity_days": BIRTHDAY_CERTIFICATE_VALIDITY_DAYS,
            "service_actions": ["personal_call", "flowers"],
            "flowers": True,
        }
    if total >= 100_000_00:
        return {
            "code": "vip_100_300",
            "title": "VIP 100 000–299 999 ₽",
            "channel": "call",
            "certificate_kopecks": BIRTHDAY_CERTIFICATE_AMOUNT_KOPECKS,
            "gift_certificate": {"amount_kopecks": BIRTHDAY_CERTIFICATE_AMOUNT_KOPECKS},
            "certificate_validity_days": BIRTHDAY_CERTIFICATE_VALIDITY_DAYS,
            "service_actions": ["personal_call"],
            "flowers": False,
        }
    if total >= 50_000_00:
        return {"code": "bonus_2000", "title": "50 000–99 999 ₽", "channel": "message", "bonus_points": 2000, "bonus_validity_days": 30}
    if total >= 20_000_00:
        return {"code": "bonus_1000", "title": "20 000–49 999 ₽", "channel": "message", "bonus_points": 1000, "bonus_validity_days": 30}
    return {"code": "bonus_500", "title": "до 20 000 ₽", "channel": "message", "bonus_points": 500, "bonus_validity_days": 30}


def _birthday_message(customer: Any, tier: Dict[str, Any], next_birthday: date, today: date) -> str:
    name = _first_name(customer) or _customer_display_name(customer)
    days = (next_birthday - today).days
    if tier["code"] == "vip_300_plus":
        return (
            f"{name}, добрый день! Это GLAME ✨\n\n"
            "Хотели лично поздравить Вас с днем рождения от нашей команды. "
            "Желаем Вам красоты, вдохновения и особенных моментов каждый день.\n\n"
            "В честь Вашего праздника GLAME подготовил для Вас персональный сертификат на 5 000 ₽, "
            "а также цветы от нашей команды. Сертификат действует 30 дней.\n\n"
            "Будем рады согласовать, как Вам будет удобнее получить поздравление — в бутике или с доставкой."
        )
    if tier["code"] == "vip_100_300":
        return (
            f"{name}, поздравляем Вас с днем рождения! ✨\n\n"
            "Желаем Вам красоты, вдохновения, ярких впечатлений и особенных моментов каждый день. "
            "Нам очень приятно, что Вы выбираете GLAME и разделяете с нами любовь к украшениям.\n\n"
            "В честь Вашего праздника GLAME подготовил для Вас персональный сертификат на 5 000 ₽. "
            "Сертификат действует 30 дней.\n\n"
            "Мы будем рады лично поздравить Вас и помочь выбрать украшение, которое станет красивым акцентом Вашего праздника."
        )
    points = int(tier.get("bonus_points") or 0)
    valid_until = _format_bonus_valid_until(next_birthday)
    if days > 0:
        return (
            f"{name}, Ваш день рождения уже совсем скоро ✨\n\n"
            "Желаем Вам красоты, вдохновения и приятных моментов каждый день. "
            "Нам очень приятно, что Вы разделяете с нами любовь к красивым украшениям и особенным деталям.\n\n"
            f"GLAME заранее подготовил для Вас подарок — {points:,}".replace(",", " ")
            + f" бонусов на бонусный счёт. Они действуют до {valid_until} включительно.\n\n"
            "Будем рады видеть Вас в бутике. А если сейчас не получается до нас добраться — "
            "с удовольствием подберём для Вас украшение дистанционно. Мы на связи и поможем с доставкой."
        )
    return (
        f"{name}, поздравляем Вас с днем рождения! ✨\n\n"
        "Желаем красоты, вдохновения и приятных моментов каждый день. "
        "Нам очень приятно, что Вы разделяете с нами любовь к красивым украшениям и особенным деталям.\n\n"
        f"В честь праздника GLAME дарит Вам {points:,}".replace(",", " ")
        + f" бонусов на бонусный счёт. Они действуют до {valid_until} включительно.\n\n"
        "Будем рады видеть Вас в бутике. А если сейчас не получается до нас добраться — "
        "с удовольствием подберём для Вас украшение дистанционно. Мы на связи и поможем с доставкой."
    )


def _birthday_script(customer: Any, tier: Dict[str, Any], next_birthday: date, today: date) -> str:
    name = _first_name(customer) or _customer_display_name(customer)
    if tier["code"] == "vip_300_plus":
        return (
            f"{name}, добрый день! Это {{имя}}, GLAME.\n\n"
            "Я звоню, чтобы лично поздравить Вас с днем рождения от всей команды GLAME. "
            "Желаем Вам красоты, вдохновения, ярких впечатлений и особенных моментов каждый день.\n\n"
            "В честь Вашего праздника мы подготовили для Вас персональный сертификат на 5 000 ₽. "
            "Сертификат действует 30 дней.\n\n"
            "Также мы хотели бы передать Вам цветы от GLAME. Подскажите, пожалуйста, как Вам будет удобнее: "
            "получить их в бутике или согласовать доставку?\n\n"
            f"Если не дозвонились, отправьте сообщение:\n{_birthday_message(customer, tier, next_birthday, today)}"
        )
    if tier["code"] == "vip_100_300":
        return (
            f"{name}, добрый день! Это {{имя продавца/администратора}}, GLAME.\n\n"
            "Я звоню, чтобы лично поздравить Вас с днем рождения от всей команды GLAME. "
            "Хотим пожелать Вам красоты, вдохновения и приятных моментов каждый день.\n\n"
            "Мы очень ценим, что Вы выбираете GLAME, поэтому в честь Вашего праздника подготовили для Вас "
            "персональный сертификат на 5 000 ₽.\n\n"
            "Вы можете использовать его в бутике в течение 30 дней. Если Вам будет удобно, мы можем заранее "
            "подобрать для Вас украшения под Ваш стиль, образ или повод.\n\n"
            "Если клиентка не в городе — предложить дистанционный подбор, фото/видео и доставку."
        )
    return _birthday_message(customer, tier, next_birthday, today)


def _birthday_seller_action(tier: Dict[str, Any]) -> str:
    if tier["code"] == "vip_300_plus":
        return (
            "Позвонить лично, поздравить от команды GLAME, сообщить о сертификате 5 000 ₽, "
            "аккуратно согласовать передачу цветов: в бутике, доставкой или другим удобным форматом. "
            "Не отправлять цветы без подтверждения адреса/удобства. Зафиксировать результат."
        )
    if tier["code"] == "vip_100_300":
        return (
            "Связаться лично, лучше звонком. Поздравить от GLAME, сообщить о персональном сертификате 5 000 ₽, "
            "предложить подготовить украшения заранее под стиль/событие/образ. Не говорить “бонусы” и не подавать как скидку. "
            "Зафиксировать результат."
        )
    return (
        "Написать клиентке по готовому тексту. Не начислять бонусы вручную: они должны быть начислены/проверены системой. "
        "Если клиентка отвечает — мягко предложить подбор, новинки, вариант под образ/подарок/событие, дистанционный подбор и доставку. "
        "Зафиксировать результат контакта."
    )


def _append_certificate_notification_to_script(script_text: str, certificate_message_text: Optional[str]) -> str:
    if not certificate_message_text:
        return script_text
    return (
        f"{script_text.rstrip()}\n\n"
        "Сообщение клиенту с данными сертификата:\n"
        f"{certificate_message_text.strip()}"
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

    async def generate_tasks(
        self,
        today: Optional[date] = None,
        *,
        days_ahead: int = DEFAULT_BIRTHDAY_DAYS_AHEAD,
        limit: int = 500,
        actor: Optional[Any] = None,
    ) -> Dict[str, Any]:
        from sqlalchemy import and_, extract, or_, select
        from sqlalchemy.orm import selectinload

        from app.models.crm_task import CrmTask, CrmTaskEvent
        from app.models.customer_message import CustomerMessage
        from app.models.purchase_history import PurchaseHistory
        from app.models.user import User
        from app.services.crm_task_service import CrmTaskService
        from app.services.gift_certificate_service import GiftCertificateService

        today = today or date.today()
        crm_service = CrmTaskService(self.db)
        gift_service = GiftCertificateService(self.db)
        staff = (await self.db.execute(
            select(User).where(User.is_customer.is_(False), User.role.in_(["seller", "manager", "admin"]), User.full_name.isnot(None))
        )).scalars().all()

        birthday_dates = [today + timedelta(days=offset) for offset in range(days_ahead + 1)]
        birthday_conditions = [
            and_(extract("month", User.birth_date) == value.month, extract("day", User.birth_date) == value.day)
            for value in birthday_dates
        ]
        users_result = await self.db.execute(
            select(User)
            .where(
                User.is_customer == True,  # noqa: E712
                User.birth_date.isnot(None),
                or_(*birthday_conditions),
            )
            .order_by(User.birth_date)
            .limit(limit)
        )
        customers = [u for u in users_result.scalars().all() if is_birthday_within_window(u.birth_date, today, days_ahead)]
        customers = sorted(customers, key=lambda u: days_until_birthday(u.birth_date, today))[:limit]
        customer_ids = [customer.id for customer in customers]
        purchases_by_customer: Dict[Any, List[Any]] = defaultdict(list)
        if customer_ids:
            purchases_result = await self.db.execute(
                select(PurchaseHistory)
                .options(selectinload(PurchaseHistory.product))
                .where(PurchaseHistory.user_id.in_(customer_ids))
                .order_by(PurchaseHistory.user_id, PurchaseHistory.purchase_date)
            )
            for purchase in purchases_result.scalars().all():
                purchases_by_customer[getattr(purchase, "user_id", None)].append(purchase)

        summary: Dict[str, Any] = {
            "work_date": today.isoformat(),
            "days_ahead": days_ahead,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "certificates_created": 0,
            "certificate_messages_created": 0,
            "certificate_sms_sent": 0,
            "certificate_sms_skipped": 0,
            "errors": [],
            "by_tier": {},
        }

        for customer in customers:
            try:
                birth_date = getattr(customer, "birth_date", None)
                if not birth_date:
                    summary["skipped"] += 1
                    continue
                next_birthday = next_birthday_date(birth_date, today)
                idempotency_key = f"{CRM_BIRTHDAY_SOURCE}:{next_birthday.year}:{customer.id}:{next_birthday.isoformat()}"
                existing = await self.db.scalar(select(CrmTask).where(CrmTask.source_idempotency_key == idempotency_key))
                if existing:
                    summary["skipped"] += 1
                    continue

                profile = calculate_real_purchase_profile(purchases_by_customer.get(customer.id, []))
                tier = birthday_tier(profile)
                assignee = self._manager_for_customer(customer, staff)
                store_name = self._store_name_for_customer(customer)
                days_until = (next_birthday - today).days
                script_text = _birthday_script(customer, tier, next_birthday, today)
                message_text = _birthday_message(customer, tier, next_birthday, today)
                sms_window = _birthday_certificate_sms_window()
                certificate = None
                certificate_pin = ""
                certificate_payload = None
                certificate_message_text = None
                certificate_sms_status = None
                if tier.get("certificate_kopecks"):
                    certificate, certificate_pin, certificate_created = await gift_service.create_program_certificate(
                        recipient_user_id=customer.id,
                        buyer_user_id=getattr(actor, "id", None),
                        nominal_amount=int(tier["certificate_kopecks"]),
                        source=CRM_BIRTHDAY_SOURCE,
                        source_idempotency_key=f"{idempotency_key}:certificate",
                        recipient_name=_customer_display_name(customer),
                        recipient_phone=getattr(customer, "phone", None),
                        recipient_email=getattr(customer, "email", None),
                        message="Сертификат по программе поздравления с днем рождения GLAME.",
                        expires_in_days=_certificate_expires_in_days(today, next_birthday),
                        meta={
                            "crm_campaign_id": CRM_BIRTHDAY_CAMPAIGN_ID,
                            "crm_campaign_name": CRM_BIRTHDAY_CAMPAIGN_NAME,
                            "birthday_date": birth_date.isoformat(),
                            "next_birthday": next_birthday.isoformat(),
                            "birthday_tier": tier.get("code"),
                            "customer_total_spent_kopecks": profile.get("real_total_spent"),
                            "requires_flowers": bool(tier.get("flowers")),
                            "notification_channel": "sms",
                        },
                    )
                    target_expires_at = _certificate_expires_at_for_birthday(next_birthday)
                    if not certificate.expires_at or certificate.expires_at.date() != target_expires_at.date():
                        certificate.expires_at = target_expires_at
                        certificate_meta = certificate.meta if isinstance(certificate.meta, dict) else {}
                        certificate.meta = {
                            **certificate_meta,
                            "valid_until_rule": "birthday_plus_30_days",
                            "valid_until": target_expires_at.date().isoformat(),
                        }
                    certificate_valid_until = _format_certificate_expires_at(certificate, next_birthday)
                    certificate_message_text = _birthday_certificate_sms_text(
                        customer, certificate, certificate_pin, certificate_valid_until
                    )
                    certificate_meta = certificate.meta if isinstance(certificate.meta, dict) else {}
                    certificate.meta = {**certificate_meta, "sms_text": certificate_message_text}
                    certificate_payload = {
                        "id": str(certificate.id),
                        "number": certificate.number,
                        "nominal_amount": int(certificate.nominal_amount or 0),
                        "balance_amount": int(certificate.balance_amount or 0),
                        "status": certificate.status,
                        "expires_at": certificate.expires_at.isoformat() if certificate.expires_at else None,
                        "valid_until": certificate_valid_until,
                        "created": bool(certificate_created),
                    }
                    if certificate_created:
                        summary["certificates_created"] += 1
                    certificate_sms_status = "prepared"
                    script_text = _append_certificate_notification_to_script(script_text, certificate_message_text)
                source_payload = {
                    "birthday_date": birth_date.isoformat(),
                    "next_birthday": next_birthday.isoformat(),
                    "days_until_birthday": days_until,
                    "communication_start_date": (next_birthday - timedelta(days=DEFAULT_BIRTHDAY_DAYS_AHEAD)).isoformat(),
                    "validity_rule": "D−3 is communication/accrual start; bonus gifts are valid for 30 days from birthday; VIP certificates are issued by the platform and are valid for 30 days.",
                    "tier": tier,
                    "profile": profile,
                    "message_text": message_text,
                    "bonus_valid_until": _format_bonus_valid_until(next_birthday) if tier.get("bonus_points") else None,
                    "certificate_valid_until": (
                        certificate_payload.get("valid_until")
                        if certificate_payload
                        else _format_certificate_valid_until(next_birthday) if tier.get("certificate_kopecks") else None
                    ),
                    "certificate_validity_days": tier.get("certificate_validity_days"),
                    "certificate": certificate_payload,
                    "certificate_notification_text": certificate_message_text,
                    "certificate_sms_autosend": False,
                    "certificate_sms_send_window": sms_window,
                    "certificate_sms_status": certificate_sms_status,
                    "assignment_rule": "preferred_store_or_city_manager",
                    "auto_send": False,
                }
                task = CrmTask(
                    customer_id=customer.id,
                    assigned_seller_user_id=getattr(assignee, "id", None),
                    assigned_seller_external_id=self._seller_external_id(assignee),
                    assigned_seller_name=getattr(assignee, "full_name", None),
                    store_id=getattr(customer, "preferred_store_external_id", None),
                    store_name=store_name,
                    work_date=today,
                    due_date=datetime.combine(today, time(hour=20), tzinfo=timezone.utc),
                    priority=1 if tier["code"].startswith("vip") else 2,
                    crm_group="birthday_greeting",
                    reason=(
                        f"День рождения клиента {next_birthday.isoformat()} "
                        f"({'сегодня' if days_until == 0 else f'через {days_until} дн.'}). "
                        f"Уровень: {tier['title']}."
                    ),
                    seller_action=_birthday_seller_action(tier),
                    script_key=f"birthday_{tier['code']}",
                    script_text=script_text,
                    status="new",
                    campaign_id=CRM_BIRTHDAY_CAMPAIGN_ID,
                    campaign_name=CRM_BIRTHDAY_CAMPAIGN_NAME,
                    source=CRM_BIRTHDAY_SOURCE,
                    source_row_id=str(customer.id),
                    source_idempotency_key=idempotency_key,
                    source_payload=source_payload,
                    created_by_user_id=getattr(actor, "id", None),
                    updated_at=datetime.now(timezone.utc),
                )
                self.db.add(task)
                await self.db.flush()
                if certificate and certificate_payload:
                    sms_sent = False
                    certificate_sms_status = "prepared"

                    source_payload["certificate_sms_status"] = certificate_sms_status
                    task.source_payload = source_payload
                    if sms_sent:
                        summary["certificate_sms_sent"] += 1
                    else:
                        summary["certificate_sms_skipped"] += 1

                    self.db.add(CustomerMessage(
                        user_id=customer.id,
                        message=certificate_message_text or message_text,
                        cta="Электронный сертификат GLAME: данные для активации",
                        segment="birthday_greeting",
                        event_type="birthday_certificate",
                        event_brand=f"birthday_{tier['code']}",
                        event_store=store_name,
                        payload={
                            "kind": "birthday_certificate",
                            "crm_task_id": str(task.id),
                            "campaign_id": CRM_BIRTHDAY_CAMPAIGN_ID,
                            "campaign_name": CRM_BIRTHDAY_CAMPAIGN_NAME,
                            "source": CRM_BIRTHDAY_SOURCE,
                            "source_idempotency_key": f"{idempotency_key}:certificate_message",
                            "certificate": certificate_payload,
                            "certificate_pin": certificate_pin,
                            "sms_status": certificate_sms_status,
                            "auto_send": False,
                        },
                        status="sent" if sms_sent else "new",
                        sent_at=datetime.now(timezone.utc) if sms_sent else None,
                    ))
                    self.db.add(CrmTaskEvent(
                        task_id=task.id,
                        event_type="birthday_certificate_issued",
                        actor_user_id=getattr(actor, "id", None),
                        actor_name=crm_service._actor_name(actor),
                        previous_status=None,
                        next_status=task.status,
                        payload={
                            "certificate_id": str(certificate.id),
                            "certificate_number": certificate.number,
                            "certificate_valid_until": certificate_payload.get("valid_until"),
                            "sms_status": certificate_sms_status,
                        },
                    ))
                    summary["certificate_messages_created"] += 1
                self.db.add(CrmTaskEvent(
                    task_id=task.id,
                    event_type="created_from_birthday_rule",
                    actor_user_id=getattr(actor, "id", None),
                    actor_name=crm_service._actor_name(actor),
                    previous_status=None,
                    next_status=task.status,
                    payload={"next_birthday": next_birthday.isoformat(), "tier": tier.get("code")},
                ))
                summary["created"] += 1
                summary["by_tier"][tier["code"]] = int(summary["by_tier"].get(tier["code"]) or 0) + 1
            except Exception as exc:
                summary["errors"].append({"customer_id": str(getattr(customer, "id", "")), "error": str(exc)})

        await self.db.commit()
        return summary

    async def create_vip_preview_task(self, today: Optional[date] = None, *, actor: Optional[Any] = None) -> Any:
        """Create/update one explicit demo task for checking seller-side VIP birthday UX."""
        from sqlalchemy import select

        from app.models.crm_task import CrmTask, CrmTaskEvent
        from app.models.customer_message import CustomerMessage
        from app.models.user import User
        from app.services.crm_task_service import CrmTaskService
        from app.services.gift_certificate_service import GiftCertificateService

        today = today or date.today()
        crm_service = CrmTaskService(self.db)
        gift_service = GiftCertificateService(self.db)
        next_birthday = today + timedelta(days=3)
        test_phone = "79990005000"
        customer = await self.db.scalar(select(User).where(User.phone == test_phone))
        if customer is None:
            customer = User(
                phone=test_phone,
                full_name="Тестовая VIP клиентка ДР",
                birth_date=next_birthday,
                city="Симферополь",
                preferred_store_name="ТРК Центрум",
                total_purchases=7,
                total_spent=150_000_00,
                average_check=21_428_00,
                customer_segment="VIP",
                loyalty_points=0,
                is_customer=True,
                role="customer",
                preferences={"is_demo_crm_customer": True},
            )
            self.db.add(customer)
            await self.db.flush()
        else:
            customer.full_name = "Тестовая VIP клиентка ДР"
            customer.birth_date = next_birthday
            customer.city = "Симферополь"
            customer.preferred_store_name = "ТРК Центрум"
            customer.total_purchases = max(int(customer.total_purchases or 0), 7)
            customer.total_spent = max(int(customer.total_spent or 0), 150_000_00)
            customer.average_check = customer.average_check or 21_428_00
            customer.customer_segment = "VIP"
            prefs = customer.preferences if isinstance(customer.preferences, dict) else {}
            customer.preferences = {**prefs, "is_demo_crm_customer": True}

        staff = (
            await self.db.execute(
                select(User).where(
                    User.is_customer.is_(False),
                    User.role.in_(["seller", "manager", "admin"]),
                    User.full_name.isnot(None),
                )
            )
        ).scalars().all()
        assignee = self._manager_for_customer(customer, staff)
        store_name = self._store_name_for_customer(customer) or "ТРК Центрум"
        profile = {
            "real_receipts_count": 7,
            "real_total_spent": 150_000_00,
            "average_receipt": 21_428_00,
            "high_quality_checks": 7,
            "excluded_accessory_amount": 0,
            "receipt_bundles": [
                {
                    "document_ids": ["DEMO-BDAY-VIP-001"],
                    "purchase_date": datetime.combine(today - timedelta(days=45), time(hour=12), tzinfo=timezone.utc).isoformat(),
                    "total_amount": 150_000_00,
                    "items_count": 2,
                    "item_names": ["Демо украшение GLAME"],
                }
            ],
        }
        tier = birthday_tier(profile)
        certificate, certificate_pin, certificate_created = await gift_service.create_program_certificate(
            recipient_user_id=customer.id,
            buyer_user_id=getattr(actor, "id", None),
            nominal_amount=BIRTHDAY_CERTIFICATE_AMOUNT_KOPECKS,
            source="birthday_crm_preview",
            source_idempotency_key="birthday_crm_preview:vip_certificate:gift_certificate",
            recipient_name=_customer_display_name(customer),
            recipient_phone=getattr(customer, "phone", None),
            recipient_email=getattr(customer, "email", None),
            message="Тестовый сертификат для проверки VIP-задачи ДР GLAME.",
            expires_in_days=_certificate_expires_in_days(today, next_birthday),
            meta={
                "is_demo": True,
                "crm_campaign_id": "birthday-greetings-preview",
                "crm_campaign_name": "Тест · Поздравление с ДР VIP",
                "birthday_date": customer.birth_date.isoformat() if customer.birth_date else None,
                "next_birthday": next_birthday.isoformat(),
                "birthday_tier": tier.get("code"),
                "valid_until_rule": "birthday_plus_30_days",
                "notification_channel": "crm_task_only",
                "sms_autosend": False,
            },
        )
        target_expires_at = _certificate_expires_at_for_birthday(next_birthday)
        if not certificate.expires_at or certificate.expires_at.date() != target_expires_at.date():
            certificate.expires_at = target_expires_at
        certificate_meta = certificate.meta if isinstance(certificate.meta, dict) else {}
        certificate.meta = {
            **certificate_meta,
            "is_demo": True,
            "valid_until_rule": "birthday_plus_30_days",
            "valid_until": target_expires_at.date().isoformat(),
            "sms_autosend": False,
        }
        certificate_number = certificate.number
        certificate_valid_until = _format_certificate_expires_at(certificate, next_birthday)
        certificate_message_text = _birthday_certificate_sms_text(customer, certificate, certificate_pin, certificate_valid_until)
        script_text = _append_certificate_notification_to_script(
            _birthday_script(customer, tier, next_birthday, today),
            certificate_message_text,
        )
        days_until = (next_birthday - today).days
        idempotency_key = "birthday_crm_preview:vip_certificate:seller_card"
        source_payload = {
            "task_type": "BIRTHDAY_VIP_PREVIEW",
            "is_demo": True,
            "birthday_date": customer.birth_date.isoformat() if customer.birth_date else None,
            "next_birthday": next_birthday.isoformat(),
            "days_until_birthday": days_until,
            "communication_start_date": today.isoformat(),
            "validity_rule": "Демо: VIP-сертификат действует 30 дней от дня рождения.",
            "tier": tier,
            "profile": profile,
            "message_text": _birthday_message(customer, tier, next_birthday, today),
            "certificate_valid_until": certificate_valid_until,
            "certificate_validity_days": BIRTHDAY_CERTIFICATE_VALIDITY_DAYS,
            "certificate": {
                "id": str(certificate.id),
                "number": certificate_number,
                "nominal_amount": int(certificate.nominal_amount or 0),
                "balance_amount": int(certificate.balance_amount or 0),
                "status": certificate.status,
                "expires_at": certificate.expires_at.isoformat() if certificate.expires_at else None,
                "valid_until": certificate_valid_until,
                "created": bool(certificate_created),
                "is_demo": True,
                "onec_series_ref_key": getattr(certificate, "onec_certificate_id", None),
                "onec_sync_status": (certificate.meta or {}).get("onec_sync_status") if isinstance(certificate.meta, dict) else None,
                "onec_sync_error": (certificate.meta or {}).get("onec_sync_error") if isinstance(certificate.meta, dict) else None,
            },
            "certificate_notification_text": certificate_message_text,
            "certificate_sms_autosend": False,
            "certificate_sms_status": "prepared_demo",
            "assignment_rule": "demo_store_manager",
            "auto_send": False,
        }
        task = await self.db.scalar(select(CrmTask).where(CrmTask.source_idempotency_key == idempotency_key))
        if task is None:
            task = CrmTask(
                customer_id=customer.id,
                source="birthday_crm_preview",
                source_idempotency_key=idempotency_key,
                source_row_id=str(customer.id),
                created_by_user_id=getattr(actor, "id", None),
            )
            self.db.add(task)
            event_type = "created_birthday_vip_preview"
            previous_status = None
        else:
            previous_status = task.status
            event_type = "updated_birthday_vip_preview"

        task.assigned_seller_user_id = getattr(assignee, "id", None)
        task.assigned_seller_external_id = self._seller_external_id(assignee)
        task.assigned_seller_name = getattr(assignee, "full_name", None)
        task.store_id = getattr(customer, "preferred_store_external_id", None)
        task.store_name = store_name
        task.work_date = today
        task.due_date = datetime.combine(today, time(hour=20), tzinfo=timezone.utc)
        task.priority = 1
        task.crm_group = "birthday_greeting"
        task.reason = (
            f"ТЕСТ: День рождения VIP-клиента {next_birthday.isoformat()} "
            f"(через {days_until} дн.). Уровень: {tier['title']}."
        )
        task.seller_action = (
            "ТЕСТОВАЯ ЗАДАЧА: проверить, как продавец видит VIP-поздравление с ДР, "
            "персональный сертификат 5 000 ₽ и готовое сообщение клиенту. Реальному клиенту не отправлять."
        )
        task.script_key = f"birthday_{tier['code']}_preview"
        task.script_text = script_text
        task.status = "new"
        task.seller_outcome = None
        task.seller_comment = None
        task.next_action_date = None
        task.completed_at = None
        task.campaign_id = "birthday-greetings-preview"
        task.campaign_name = "Тест · Поздравление с ДР VIP"
        task.source_payload = source_payload
        task.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        self.db.add(
            CrmTaskEvent(
                task_id=task.id,
                event_type=event_type,
                actor_user_id=getattr(actor, "id", None),
                actor_name=crm_service._actor_name(actor),
                previous_status=previous_status,
                next_status=task.status,
                payload={
                    "is_demo": True,
                    "certificate_number": certificate_number,
                    "certificate_valid_until": certificate_valid_until,
                },
            )
        )

        existing_message = await self.db.scalar(
            select(CustomerMessage).where(
                CustomerMessage.user_id == customer.id,
                CustomerMessage.event_type == "birthday_certificate_preview",
                CustomerMessage.payload["crm_task_id"].astext == str(task.id),
            )
        )
        message_payload = {
            "kind": "birthday_certificate_preview",
            "is_demo": True,
            "crm_task_id": str(task.id),
            "campaign_id": task.campaign_id,
            "campaign_name": task.campaign_name,
            "source": task.source,
            "certificate": source_payload["certificate"],
            "sms_status": "prepared_demo",
            "auto_send": False,
        }
        if existing_message is None:
            self.db.add(
                CustomerMessage(
                    user_id=customer.id,
                    message=certificate_message_text,
                    cta="Демо: электронный сертификат GLAME",
                    segment="birthday_greeting",
                    event_type="birthday_certificate_preview",
                    event_brand=task.script_key,
                    event_store=store_name,
                    payload=message_payload,
                    status="new",
                    sent_at=None,
                )
            )
        else:
            existing_message.message = certificate_message_text
            existing_message.payload = message_payload
            existing_message.status = "new"
            existing_message.sent_at = None

        await self.db.commit()
        detailed_task = await crm_service.get_task(task.id, admin=True)
        return await crm_service.serialize_task(detailed_task)

    def _store_name_for_customer(self, customer: Any) -> Optional[str]:
        return _crm_customer_store_name(customer)

    def _manager_for_customer(self, customer: Any, staff: List[Any]) -> Optional[Any]:
        manager_name = None
        # Приоритет назначения: основной магазин клиента → город → вторичный/исторический магазин.
        # Например, у части ялтинских клиентов secondary_store_name = "Мрия"; это не должно
        # перебивать основной магазин "Ялта, Набережная 18".
        for raw_value in [
            _crm_customer_store_name(customer),
            getattr(customer, "city", None),
            getattr(customer, "secondary_store_name", None),
        ]:
            marker_source = str(_crm_display_store_name(raw_value) or "").lower()
            if not marker_source:
                continue
            for marker, name in BIRTHDAY_STORE_MANAGER_NAMES.items():
                if marker in marker_source:
                    manager_name = name
                    break
            if manager_name:
                break
        if not manager_name:
            return None
        normalized = manager_name.lower().replace("ё", "е")
        for user in staff:
            full_name = str(getattr(user, "full_name", "") or "").lower().replace("ё", "е")
            if full_name == normalized:
                return user
        return None

    def _seller_external_id(self, user: Optional[Any]) -> Optional[str]:
        if not user:
            return None
        prefs = getattr(user, "preferences", None)
        if not isinstance(prefs, dict):
            return None
        return (
            str(prefs.get("seller_external_id") or "").strip()
            or str(prefs.get("onec_seller_id") or "").strip()
            or str(prefs.get("employee_external_id") or "").strip()
            or None
        )
