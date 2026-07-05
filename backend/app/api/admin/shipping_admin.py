from typing import Any, Dict, Optional
import json

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_any_role
from app.database.connection import get_db
from app.models.app_setting import AppSetting
from app.models.store import Store
from app.models.user import User
from app.services.cdek_service import get_cdek_service


router = APIRouter()


CDEK_TARIFF_CATALOG = [
    {"code": 136, "name": "Посылка склад-склад"},
    {"code": 137, "name": "Посылка склад-дверь"},
    {"code": 138, "name": "Посылка дверь-склад"},
    {"code": 139, "name": "Посылка дверь-дверь"},
    {"code": 231, "name": "Экономичная посылка дверь-дверь"},
    {"code": 232, "name": "Экономичная посылка дверь-склад"},
    {"code": 233, "name": "Экономичная посылка склад-дверь"},
    {"code": 234, "name": "Экономичная посылка склад-склад"},
    {"code": 366, "name": "Посылка дверь-постамат"},
    {"code": 368, "name": "Посылка склад-постамат"},
    {"code": 378, "name": "Экономичная посылка склад-постамат"},
    {"code": 2261, "name": "Documents Express дверь-дверь"},
    {"code": 2262, "name": "Documents Express дверь-склад"},
    {"code": 2263, "name": "Documents Express склад-дверь"},
    {"code": 2264, "name": "Documents Express склад-склад"},
    {"code": 2266, "name": "Documents Express дверь-постамат"},
    {"code": 2267, "name": "Documents Express склад-постамат"},
    {"code": 480, "name": "Экспресс дверь-дверь"},
    {"code": 481, "name": "Экспресс дверь-склад"},
    {"code": 482, "name": "Экспресс склад-дверь"},
    {"code": 483, "name": "Экспресс склад-склад"},
]


def _mask_secret(value: Optional[str]) -> str | None:
    if not value:
        return None
    if len(value) <= 6:
        return "***"
    return value[:3] + "***" + value[-2:]


def _bool(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes"}


def _int(v: Optional[str], default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


async def _get_setting(db: AsyncSession, key: str) -> Optional[str]:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    return row.value if row else None


async def _set_setting(db: AsyncSession, key: str, value: Optional[str]) -> None:
    existing = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    if value is None:
        if existing:
            await db.delete(existing)
            await db.commit()
        return
    val = str(value)
    if existing:
        existing.value = val
    else:
        db.add(AppSetting(key=key, value=val))
    await db.commit()


@router.get("/cdek/settings")
async def get_cdek_settings(
    current_user: User = Depends(require_any_role(["admin", "content_manager"])),
    db: AsyncSession = Depends(get_db),
):
    client_id = os.getenv("CDEK_CLIENT_ID")
    client_secret = os.getenv("CDEK_CLIENT_SECRET")
    base_url = os.getenv("CDEK_BASE_URL") or "https://api.cdek.ru/v2"

    keys = {
        "display_name": "cdek_display_name",
        "company_name": "cdek_company_name",
        "company_email": "cdek_company_email",
        "company_phone": "cdek_company_phone",
        "package_comment": "cdek_package_comment",
        "contract_type": "cdek_contract_type",
        "tariff_pvz": "cdek_tariff_pvz",
        "tariff_courier": "cdek_tariff_courier",
        "sender_city_code": "cdek_sender_city_code",
        "sender_city_name": "cdek_sender_city_name",
        "sender_office_code": "cdek_sender_office_code",
        "sender_office_address": "cdek_sender_office_address",
        "dim_weight_g": "cdek_dim_weight_g",
        "dim_length_mm": "cdek_dim_length_mm",
        "dim_width_mm": "cdek_dim_width_mm",
        "dim_height_mm": "cdek_dim_height_mm",
        "pricing_mode": "cdek_pricing_mode",
        "measurement_type": "cdek_measurement_type",
        "markup_rub": "cdek_markup_rub",
        "insurance_enabled": "cdek_insurance_enabled",
        "ship_days": "cdek_ship_days",
        "free_shipping_threshold_rub": "cdek_free_shipping_threshold_rub",
        "disable_submit": "cdek_disable_submit",
        "disabled": "cdek_disabled",
    }

    values: Dict[str, Any] = {}
    for out_key, setting_key in keys.items():
        values[out_key] = await _get_setting(db, setting_key)

    pickup_store_ids_raw = await _get_setting(db, "pickup_store_ids")
    pickup_store_ids: list[str] = []
    if pickup_store_ids_raw:
        try:
            parsed = json.loads(pickup_store_ids_raw)
            if isinstance(parsed, list):
                pickup_store_ids = [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pickup_store_ids = []

    stores_res = await db.execute(select(Store).where(Store.is_active == True).order_by(Store.name.asc()))  # noqa: E712
    active_stores = stores_res.scalars().all()
    pickup_store_options = [
        {
            "id": str(s.id),
            "name": s.name,
            "city": s.city,
            "address": s.address,
            "is_active": bool(s.is_active),
        }
        for s in active_stores
    ]

    # Backward-compatible default: if no explicit selection is saved yet,
    # consider all active stores allowed for pickup.
    if not pickup_store_ids:
        pickup_store_ids = [x["id"] for x in pickup_store_options]

    return {
        "credentials": {
            "base_url": base_url,
            "client_id": client_id,
            "client_secret_masked": _mask_secret(client_secret),
            "client_secret_set": bool(client_secret),
        },
        "settings": {
            **values,
            "insurance_enabled": _bool(values.get("insurance_enabled")),
            "disable_submit": _bool(values.get("disable_submit")),
            "disabled": _bool(values.get("disabled")),
            "pickup_store_ids": pickup_store_ids,
        },
        "pickup_store_options": pickup_store_options,
    }


@router.get("/cdek/options")
async def get_cdek_options(
    current_user: User = Depends(require_any_role(["admin", "content_manager"])),
    db: AsyncSession = Depends(get_db),
):
    contract_types = [
        {"value": "internet_shop", "label": "Интернет-магазин"},
    ]
    measurement_types = [
        {"value": "g_mm", "label": "г / мм"},
        {"value": "g_cm", "label": "г / см"},
    ]
    pricing_modes = [
        {
            "value": "calculator",
            "label": "Калькулятор",
            "hint": "Цена доставки считается по тарифу СДЭК и правилам корзины",
        },
        {"value": "free", "label": "Бесплатно", "hint": "Доставка всегда 0"},
        {
            "value": "fixed",
            "label": "Фиксированная сумма",
            "hint": "Фиксированная стоимость доставки (в рублях)",
        },
    ]

    sender_city_code = _int(await _get_setting(db, "cdek_sender_city_code"), 0)
    dim_weight_g = _int(await _get_setting(db, "cdek_dim_weight_g"), 1000)
    dim_length = _int(await _get_setting(db, "cdek_dim_length_mm"), 350)
    dim_width = _int(await _get_setting(db, "cdek_dim_width_mm"), 250)
    dim_height = _int(await _get_setting(db, "cdek_dim_height_mm"), 50)
    measurement = (await _get_setting(db, "cdek_measurement_type")) or "g_mm"

    if measurement == "g_mm":
        length = max(1, int((dim_length + 9) // 10))
        width = max(1, int((dim_width + 9) // 10))
        height = max(1, int((dim_height + 9) // 10))
    else:
        length = max(1, dim_length)
        width = max(1, dim_width)
        height = max(1, dim_height)

    tariffs = [{"code": int(t["code"]), "name": t.get("name"), "description": t.get("description")} for t in CDEK_TARIFF_CATALOG]
    svc = get_cdek_service()
    if svc and sender_city_code:
        try:
            calc = await svc.calculate_by_available_tariffs(
                from_city_code=sender_city_code,
                to_city_code=sender_city_code,
                packages=[
                    {
                        "weight": max(1, dim_weight_g),
                        "length": length,
                        "width": width,
                        "height": height,
                    }
                ],
            )
            candidates = []
            if isinstance(calc, dict):
                candidates = (
                    calc.get("tariff_codes")
                    or calc.get("tariffs")
                    or calc.get("result")
                    or []
                )
            if isinstance(candidates, list):
                for t in candidates:
                    if not isinstance(t, dict):
                        continue
                    code = t.get("tariff_code") or t.get("code")
                    name = t.get("tariff_name") or t.get("name")
                    desc = t.get("tariff_description") or t.get("description")
                    if code is None:
                        continue
                    tariffs.append(
                        {
                            "code": int(code),
                            "name": str(name) if name is not None else None,
                            "description": str(desc) if desc is not None else None,
                        }
                    )
        except Exception:
            pass

    tariffs = sorted({t["code"]: t for t in tariffs}.values(), key=lambda x: x["code"])

    return {
        "contract_types": contract_types,
        "measurement_types": measurement_types,
        "pricing_modes": pricing_modes,
        "tariffs": tariffs,
    }


@router.get("/cdek/search/cities")
async def cdek_search_cities_admin(
    q: str,
    size: int = 20,
    current_user: User = Depends(require_any_role(["admin", "content_manager"])),
    db: AsyncSession = Depends(get_db),
):
    svc = get_cdek_service()
    if not svc:
        raise HTTPException(status_code=500, detail="CDEK is not configured")
    qv = (q or "").strip()
    if len(qv) < 2:
        return []
    return await svc.search_cities(query=qv, country_codes=["RU"], size=size)


@router.get("/cdek/search/offices")
async def cdek_search_offices_admin(
    city_code: int,
    q: str = "",
    size: int = 200,
    current_user: User = Depends(require_any_role(["admin", "content_manager"])),
    db: AsyncSession = Depends(get_db),
):
    svc = get_cdek_service()
    if not svc:
        raise HTTPException(status_code=500, detail="CDEK is not configured")
    points = await svc.list_pickup_points(city_code=int(city_code), size=size)
    qv = (q or "").strip().lower()
    if not qv:
        return points
    filtered = []
    for p in points:
        if not isinstance(p, dict):
            continue
        hay = " ".join(
            [
                str(p.get("code") or ""),
                str(p.get("name") or ""),
                str(p.get("address") or ""),
                str((p.get("location") or {}).get("address") if isinstance(p.get("location"), dict) else ""),
            ]
        ).lower()
        if qv in hay:
            filtered.append(p)
    return filtered


@router.put("/cdek/settings")
async def update_cdek_settings(
    payload: Dict[str, Any],
    current_user: User = Depends(require_any_role(["admin", "content_manager"])),
    db: AsyncSession = Depends(get_db),
):
    allowed = {
        "display_name": "cdek_display_name",
        "company_name": "cdek_company_name",
        "company_email": "cdek_company_email",
        "company_phone": "cdek_company_phone",
        "package_comment": "cdek_package_comment",
        "contract_type": "cdek_contract_type",
        "tariff_pvz": "cdek_tariff_pvz",
        "tariff_courier": "cdek_tariff_courier",
        "sender_city_code": "cdek_sender_city_code",
        "sender_city_name": "cdek_sender_city_name",
        "sender_office_code": "cdek_sender_office_code",
        "sender_office_address": "cdek_sender_office_address",
        "dim_weight_g": "cdek_dim_weight_g",
        "dim_length_mm": "cdek_dim_length_mm",
        "dim_width_mm": "cdek_dim_width_mm",
        "dim_height_mm": "cdek_dim_height_mm",
        "pricing_mode": "cdek_pricing_mode",
        "measurement_type": "cdek_measurement_type",
        "markup_rub": "cdek_markup_rub",
        "insurance_enabled": "cdek_insurance_enabled",
        "ship_days": "cdek_ship_days",
        "free_shipping_threshold_rub": "cdek_free_shipping_threshold_rub",
        "disable_submit": "cdek_disable_submit",
        "disabled": "cdek_disabled",
        "pickup_store_ids": "pickup_store_ids",
    }

    for k, setting_key in allowed.items():
        if k not in payload:
            continue
        v = payload.get(k)
        if k == "pickup_store_ids":
            if v is None:
                await _set_setting(db, setting_key, None)
            elif isinstance(v, list):
                cleaned = [str(x).strip() for x in v if str(x).strip()]
                await _set_setting(db, setting_key, json.dumps(cleaned, ensure_ascii=True))
            else:
                raise HTTPException(status_code=400, detail="pickup_store_ids must be an array")
            continue
        if isinstance(v, bool):
            await _set_setting(db, setting_key, "true" if v else "false")
        elif v is None:
            await _set_setting(db, setting_key, None)
        else:
            await _set_setting(db, setting_key, str(v).strip())

    return {"success": True}
