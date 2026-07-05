import os
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.services.onec_order_xml_service import build_orders_xml_from_db, write_orders_xml_snapshot


router = APIRouter()


def _check_export_token(token: Optional[str], header_token: Optional[str]) -> None:
    expected = os.getenv("ONEC_ORDER_EXPORT_TOKEN", "").strip()
    if not expected:
        return
    actual = (token or header_token or "").strip()
    if actual != expected:
        raise HTTPException(status_code=401, detail="Invalid 1C export token")


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid updated_since")


@router.get("/1c/orders/export.xml")
async def export_orders_xml(
    order_id: Optional[str] = Query(None, description="UUID конкретного заказа"),
    updated_since: Optional[str] = Query(None, description="ISO datetime, например 2026-05-01T00:00:00Z"),
    include_canceled: bool = Query(False),
    token: Optional[str] = Query(None),
    x_1c_export_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Выгрузка заказов для 1С:УНФ в XML CommerceML 2.05.

    1С:УНФ обычно забирает заказы через стандартный "Обмен с сайтом"; этот
    endpoint можно указать как источник orders.xml или использовать как основу
    для полного протокола обмена.
    """
    _check_export_token(token, x_1c_export_token)

    oid = None
    if order_id:
        try:
            oid = UUID(order_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid order_id")
    since = _parse_dt(updated_since)

    xml = await build_orders_xml_from_db(
        db,
        order_id=oid,
        updated_since=since,
        include_canceled=include_canceled,
    )
    return Response(content=xml, media_type="application/xml; charset=utf-8")


@router.get("/1c/orders/snapshot")
async def refresh_orders_snapshot(
    token: Optional[str] = Query(None),
    x_1c_export_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    _check_export_token(token, x_1c_export_token)
    path = await write_orders_xml_snapshot(db)
    return {"ok": True, "path": path, "public_url": "/static/1c_exchange/orders.xml"}


@router.api_route("/1c/exchange", methods=["GET", "POST"])
async def onec_exchange_protocol(
    type: Optional[str] = Query(None),
    mode: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    x_1c_export_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Минимальный сценарий обмена с сайтом для 1С:УНФ.
    УНФ вызывает этот URL с query-параметрами type=sale&mode=...
    """
    _check_export_token(token, x_1c_export_token)

    exchange_type = (type or "").lower()
    exchange_mode = (mode or "").lower()
    if exchange_type not in {"sale", ""}:
        return PlainTextResponse("failure\nunsupported type", status_code=400)

    if exchange_mode == "checkauth":
        return PlainTextResponse("success\n1c_exchange\n1c_exchange\n")
    if exchange_mode == "init":
        return PlainTextResponse("zip=no\nfile_limit=10485760\n")
    if exchange_mode == "query":
        xml = await build_orders_xml_from_db(db)
        await write_orders_xml_snapshot(db)
        return Response(content=xml, media_type="application/xml; charset=utf-8")
    if exchange_mode == "success":
        return PlainTextResponse("success\n")
    if exchange_mode in {"file", "import"}:
        return PlainTextResponse("success\n")

    return PlainTextResponse("failure\nunsupported mode", status_code=400)
