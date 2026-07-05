from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database.connection import get_db
from app.models.app_setting import AppSetting
from app.models.order import Order
from app.models.user import User
from app.services.cdek_service import get_cdek_service


router = APIRouter()


class CdekPackage(BaseModel):
    weight: int = Field(ge=1)
    length: int = Field(ge=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class CdekCalculateRequest(BaseModel):
    from_city_code: int
    to_city_code: int
    packages: List[CdekPackage]
    tariff_codes: Optional[List[int]] = None


class CdekCreateShipmentRequest(BaseModel):
    order_id: str
    delivery_type: str = Field(pattern="^(pvz|courier)$")
    to_city_code: int
    pvz_code: Optional[str] = None
    address: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_phone: Optional[str] = None
    recipient_email: Optional[str] = None
    tariff_code: Optional[int] = None


def _extract_cdek_order_uuid(resp: Dict[str, Any]) -> Optional[str]:
    if not isinstance(resp, dict):
        return None
    entity = resp.get("entity")
    if isinstance(entity, dict) and entity.get("uuid"):
        return str(entity.get("uuid"))
    if resp.get("uuid"):
        return str(resp.get("uuid"))
    return None


def _extract_cdek_number(resp: Dict[str, Any]) -> Optional[str]:
    if not isinstance(resp, dict):
        return None
    entity = resp.get("entity")
    if isinstance(entity, dict) and entity.get("cdek_number") is not None:
        return str(entity.get("cdek_number"))
    if resp.get("cdek_number") is not None:
        return str(resp.get("cdek_number"))
    return None


@router.get("/shipping/cdek/cities")
async def cdek_search_cities(
    q: str = Query(..., min_length=2),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    svc = get_cdek_service()
    if not svc:
        raise HTTPException(status_code=500, detail="CDEK is not configured")
    return await svc.search_cities(query=q, country_codes=["RU"], size=size)


@router.get("/shipping/cdek/pvz")
async def cdek_list_pvz(
    city_code: int = Query(..., ge=1),
    size: int = Query(200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    svc = get_cdek_service()
    if not svc:
        raise HTTPException(status_code=500, detail="CDEK is not configured")
    return await svc.list_pickup_points(city_code=city_code, size=size)


@router.get("/shipping/cdek/options")
async def cdek_checkout_options(
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Возвращает безопасные для клиента настройки CDEK из админки,
    чтобы checkout мог корректно считать доставку и показывать доступность.
    """
    disabled = _bool(await _get_setting(db, "cdek_disabled"))
    disable_submit = _bool(await _get_setting(db, "cdek_disable_submit"))

    sender_city_code = _int(await _get_setting(db, "cdek_sender_city_code"), 0)
    sender_city_name = (await _get_setting(db, "cdek_sender_city_name")) or None
    sender_office_code = (await _get_setting(db, "cdek_sender_office_code")) or None
    sender_office_address = (await _get_setting(db, "cdek_sender_office_address")) or None

    tariff_pvz = _int(await _get_setting(db, "cdek_tariff_pvz"), 136)
    tariff_courier = _int(await _get_setting(db, "cdek_tariff_courier"), 0)

    weight_g = _int(await _get_setting(db, "cdek_dim_weight_g"), 1000)
    length_mm = _int(await _get_setting(db, "cdek_dim_length_mm"), 350)
    width_mm = _int(await _get_setting(db, "cdek_dim_width_mm"), 250)
    height_mm = _int(await _get_setting(db, "cdek_dim_height_mm"), 50)
    measurement = (await _get_setting(db, "cdek_measurement_type")) or "g_mm"

    pricing_mode = (await _get_setting(db, "cdek_pricing_mode")) or "calculator"
    # Canonical keys are aligned with admin shipping settings.
    free_shipping_threshold_rub = _int(
        await _get_setting(db, "cdek_free_shipping_threshold_rub"), 0
    )
    markup_rub = _int(await _get_setting(db, "cdek_markup_rub"), 0)

    return {
        "enabled": not disabled,
        "disable_submit": disable_submit,
        "sender": {
            "city_code": sender_city_code,
            "city_name": sender_city_name,
            "office_code": sender_office_code,
            "office_address": sender_office_address,
        },
        "tariffs": {
            "pvz": tariff_pvz,
            "courier": tariff_courier,
        },
        "package": {
            "weight_g": weight_g,
            "length_mm": length_mm,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "measurement_type": measurement,
        },
        "pricing": {
            # New canonical keys
            "mode": pricing_mode,
            "free_shipping_threshold_rub": free_shipping_threshold_rub,
            "markup_rub": markup_rub,
            # Backward-compatible aliases used by existing clients
            "free_shipping_from": free_shipping_threshold_rub,
            "surcharge": markup_rub,
        },
    }


@router.post("/shipping/cdek/calculate")
async def cdek_calculate(
    body: CdekCalculateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = get_cdek_service()
    if not svc:
        raise HTTPException(status_code=500, detail="CDEK is not configured")
    measurement = (await _get_setting(db, "cdek_measurement_type")) or "g_mm"
    raw_packages = [p.model_dump() for p in body.packages]
    packages: List[Dict[str, Any]] = []
    for p in raw_packages:
        weight = max(1, _int(str(p.get("weight")), 1))
        length = max(1, _int(str(p.get("length")), 1))
        width = max(1, _int(str(p.get("width")), 1))
        height = max(1, _int(str(p.get("height")), 1))
        # CDEK calculator expects dimensions in centimeters.
        if measurement == "g_mm":
            length = _mm_to_cm(length)
            width = _mm_to_cm(width)
            height = _mm_to_cm(height)
        packages.append(
            {
                "weight": int(weight),
                "length": int(length),
                "width": int(width),
                "height": int(height),
            }
        )
    return await svc.calculate_by_available_tariffs(
        from_city_code=body.from_city_code,
        to_city_code=body.to_city_code,
        packages=packages,
        tariff_codes=body.tariff_codes,
    )


async def _get_setting(db: AsyncSession, key: str) -> Optional[str]:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    return row.value if row else None


def _bool(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes"}


def _int(v: Optional[str], default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _mm_to_cm(value_mm: int) -> int:
    return max(1, int((int(value_mm) + 9) // 10))


@router.post("/shipping/cdek/shipments")
async def cdek_create_shipment_after_payment(
    body: CdekCreateShipmentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = get_cdek_service()
    if not svc:
        raise HTTPException(status_code=500, detail="CDEK is not configured")

    disabled = _bool(await _get_setting(db, "cdek_disabled"))
    if disabled:
        raise HTTPException(status_code=400, detail="CDEK delivery is disabled")

    try:
        oid = UUID(body.order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id")

    order = (
        await db.execute(select(Order).where(Order.id == oid, Order.user_id == current_user.id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "paid":
        raise HTTPException(status_code=400, detail="Order is not paid")

    meta = getattr(order, "meta", None) or {}
    if isinstance(meta, dict) and meta.get("cdek") and isinstance(meta.get("cdek"), dict):
        return {"order_id": str(order.id), "shipment": meta.get("cdek")}

    disable_submit = _bool(await _get_setting(db, "cdek_disable_submit"))

    tariff_pvz = _int(await _get_setting(db, "cdek_tariff_pvz"), 136)
    tariff_courier = _int(await _get_setting(db, "cdek_tariff_courier"), 0)

    sender_city_code = _int(await _get_setting(db, "cdek_sender_city_code"), 0)
    sender_office_code = (await _get_setting(db, "cdek_sender_office_code")) or None
    sender_office_address = (await _get_setting(db, "cdek_sender_office_address")) or None

    if not sender_city_code:
        raise HTTPException(status_code=400, detail="Sender city is not configured")

    dim_weight_g = _int(await _get_setting(db, "cdek_dim_weight_g"), 1000)
    dim_length = _int(await _get_setting(db, "cdek_dim_length_mm"), 350)
    dim_width = _int(await _get_setting(db, "cdek_dim_width_mm"), 250)
    dim_height = _int(await _get_setting(db, "cdek_dim_height_mm"), 50)
    measurement = (await _get_setting(db, "cdek_measurement_type")) or "g_mm"

    if measurement == "g_mm":
        dim_length_cm = _mm_to_cm(dim_length)
        dim_width_cm = _mm_to_cm(dim_width)
        dim_height_cm = _mm_to_cm(dim_height)
    else:
        dim_length_cm = max(1, dim_length)
        dim_width_cm = max(1, dim_width)
        dim_height_cm = max(1, dim_height)

    contact = getattr(order, "contact", None) or {}
    delivery = getattr(order, "delivery", None) or {}

    recipient_name = (body.recipient_name or contact.get("name") or contact.get("full_name") or "")
    recipient_phone = (body.recipient_phone or contact.get("phone") or "")
    recipient_email = (body.recipient_email or contact.get("email") or contact.get("mail") or None)
    recipient_name = str(recipient_name).strip()
    recipient_phone = str(recipient_phone).strip()

    if not recipient_name:
        raise HTTPException(status_code=400, detail="recipient_name is required")
    if not recipient_phone:
        raise HTTPException(status_code=400, detail="recipient_phone is required")

    delivery_type = body.delivery_type
    pvz_code = (body.pvz_code or delivery.get("pvz_code") or delivery.get("delivery_point"))
    address = (body.address or delivery.get("address"))

    if delivery_type == "pvz" and not pvz_code:
        raise HTTPException(status_code=400, detail="pvz_code is required for pvz delivery")
    if delivery_type == "courier" and not address:
        raise HTTPException(status_code=400, detail="address is required for courier delivery")

    tariff_code = body.tariff_code
    if tariff_code is None:
        tariff_code = tariff_pvz if delivery_type == "pvz" else tariff_courier
    if not tariff_code:
        raise HTTPException(status_code=400, detail="Tariff is not configured")

    total_qty = 1
    try:
        total_qty = int(delivery.get("items_count") or 1)
    except Exception:
        total_qty = 1
    package_weight = max(1, dim_weight_g * max(1, total_qty))

    payload: Dict[str, Any] = {
        "type": 1,
        "number": str(order.id),
        "tariff_code": int(tariff_code),
        "recipient": {
            "name": recipient_name,
            "phones": [{"number": recipient_phone}],
            **({"email": recipient_email} if recipient_email else {}),
        },
        "from_location": {"code": int(sender_city_code), **({"address": sender_office_address} if sender_office_address else {})},
        "packages": [
            {
                "number": "1",
                "weight": int(package_weight),
                "length": int(dim_length_cm),
                "width": int(dim_width_cm),
                "height": int(dim_height_cm),
            }
        ],
    }

    if sender_office_code:
        payload["shipment_point"] = sender_office_code

    if delivery_type == "pvz":
        payload["delivery_point"] = str(pvz_code)
    else:
        payload["to_location"] = {"code": int(body.to_city_code), "address": str(address)}

    shipment: Dict[str, Any]
    if disable_submit:
        shipment = {
            "mode": "disabled",
            "created_at": None,
            "tariff_code": int(tariff_code),
            "delivery_type": delivery_type,
            "to_city_code": int(body.to_city_code),
            "pvz_code": str(pvz_code) if pvz_code else None,
            "address": str(address) if address else None,
        }
    else:
        resp = await svc.create_order(payload)
        shipment = {
            "mode": "cdek",
            "request": payload,
            "response": resp,
            "order_uuid": _extract_cdek_order_uuid(resp),
            "cdek_number": _extract_cdek_number(resp),
        }

    new_meta = dict(meta) if isinstance(meta, dict) else {}
    new_meta["cdek"] = shipment
    order.meta = new_meta
    await db.commit()

    return {"order_id": str(order.id), "shipment": shipment}


@router.get("/shipping/cdek/track/{order_id}")
async def cdek_track_order(
    order_id: str,
    refresh: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = get_cdek_service()
    if not svc:
        raise HTTPException(status_code=500, detail="CDEK is not configured")

    try:
        oid = UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id")

    order = (
        await db.execute(select(Order).where(Order.id == oid, Order.user_id == current_user.id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    meta = getattr(order, "meta", None) or {}
    if not isinstance(meta, dict):
        meta = {}
    cdek_meta = meta.get("cdek") if isinstance(meta.get("cdek"), dict) else None
    if not cdek_meta:
        return {"order_id": str(order.id), "provider": "cdek", "tracking": None}

    if cdek_meta.get("mode") != "cdek":
        return {"order_id": str(order.id), "provider": "cdek", "tracking": cdek_meta}

    order_uuid = cdek_meta.get("order_uuid")
    if not order_uuid:
        resp = cdek_meta.get("response")
        if isinstance(resp, dict):
            order_uuid = _extract_cdek_order_uuid(resp)

    if not order_uuid:
        return {"order_id": str(order.id), "provider": "cdek", "tracking": cdek_meta}

    tracking_cached = cdek_meta.get("tracking") if isinstance(cdek_meta.get("tracking"), dict) else None
    if tracking_cached and not refresh:
        return {"order_id": str(order.id), "provider": "cdek", "tracking": tracking_cached}

    remote = await svc.get_order(str(order_uuid))

    tracking = {
        "order_uuid": str(order_uuid),
        "cdek_number": cdek_meta.get("cdek_number"),
        "remote": remote,
        "updated_at": None,
    }

    cdek_meta = dict(cdek_meta)
    cdek_meta["tracking"] = tracking
    meta["cdek"] = cdek_meta
    order.meta = meta
    await db.commit()

    return {"order_id": str(order.id), "provider": "cdek", "tracking": tracking}
