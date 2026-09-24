"""Date-aware store aliases for 1C cash-register / structural-unit history."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional


CENTRUM_STORE_ID_1C = "6c3a8322-a2ab-11f0-96fc-fa163e4cc04e"
YALTA_STORE_ID_1C = "3daee4e4-a2ab-11f0-96fc-fa163e4cc04e"
LEGACY_MEGANOM_STORE_ID_1C = "8cebda58-a2ab-11f0-96fc-fa163e4cc04e"
MRIYA_STORE_ID_1C = "e1a2ea42-fdc8-11ef-8c0c-fa163e4cc04e"
MEGANOM_TO_MRIYA_START_DATE = date(2026, 6, 1)


def coerce_date(value: Any) -> Optional[date]:
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


def effective_store_id(store_id: Optional[str], event_date: Any = None) -> Optional[str]:
    cleaned = str(store_id or "").strip()
    if not cleaned:
        return None
    day = coerce_date(event_date)
    if cleaned == LEGACY_MEGANOM_STORE_ID_1C and day and day >= MEGANOM_TO_MRIYA_START_DATE:
        return MRIYA_STORE_ID_1C
    return cleaned


def effective_store_name(store_name: Optional[str], event_date: Any = None, store_id: Optional[str] = None) -> Optional[str]:
    text = " ".join(str(store_name or "").replace("\u00a0", " ").strip().split())
    day = coerce_date(event_date)
    effective_id = effective_store_id(store_id, day)
    if effective_id == MRIYA_STORE_ID_1C:
        return "Мрия"
    if not text:
        return None
    normalized = text.lower().replace("ё", "е")
    if ("меганом" in normalized or "meganom" in normalized) and day and day >= MEGANOM_TO_MRIYA_START_DATE:
        return "Мрия"
    return text


def crm_store_key(store_name: Optional[str] = None, city: Optional[str] = None, event_date: Any = None, store_id: Optional[str] = None) -> Optional[str]:
    name = effective_store_name(store_name, event_date, store_id=store_id)
    source = " ".join([str(name or ""), str(city or "")]).lower().replace("ё", "е")
    if not source:
        return None
    if "мрия" in source or "mriya" in source:
        return "MRIYA"
    if "ялта" in source:
        return "YALTA"
    if "центрум" in source or "centrum" in source or "симфер" in source:
        return "CENTRUM"
    if "меганом" in source or "meganom" in source:
        return "MEGANOM"
    return None


def effective_store_id_sql(store_id_expr: str, date_expr: str) -> str:
    return f"""
CASE
    WHEN {store_id_expr} = '{LEGACY_MEGANOM_STORE_ID_1C}' AND {date_expr} >= TIMESTAMPTZ '2026-06-01 00:00:00+00'
    THEN '{MRIYA_STORE_ID_1C}'
    ELSE {store_id_expr}
END
"""


def effective_store_name_sql(store_name_expr: str, store_id_expr: str, date_expr: str) -> str:
    return f"""
CASE
    WHEN {store_id_expr} = '{LEGACY_MEGANOM_STORE_ID_1C}' AND {date_expr} >= TIMESTAMPTZ '2026-06-01 00:00:00+00'
    THEN 'Мрия'
    WHEN LOWER(COALESCE({store_name_expr}, '')) LIKE '%меганом%' AND {date_expr} >= TIMESTAMPTZ '2026-06-01 00:00:00+00'
    THEN 'Мрия'
    ELSE COALESCE({store_name_expr}, {store_id_expr})
END
"""
