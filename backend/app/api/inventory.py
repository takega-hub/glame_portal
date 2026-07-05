from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List, Optional

from datetime import date, datetime, timedelta, timezone
from app.database.connection import get_db
from app.models.inventory_target_category import InventoryTargetCategory
from app.models.product import Product
from app.models.sales_record import SalesRecord
from app.services.inventory_snapshot_service import InventorySnapshotService
from app.services.inventory_control_service import InventoryControlService
from app.services.sales_record_filters import product_eligible_filter, sales_record_eligible_product_filter
from app.agents.inventory_assortment_matrix_agent import AssortmentMatrixAgent

from uuid import UUID


router = APIRouter()
ASSORTMENT_SNAPSHOT_TYPE = "assortment_jewelry_only"
MARKETING_LINK_SNAPSHOT_TYPE = "marketing_link_jewelry_only"

def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    return date.fromisoformat(v)


def _resolve_period(
    analysis_period_days: int,
    period: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> tuple[datetime, datetime, int]:
    p = (period or "").strip().lower() or None
    today = datetime.now(timezone.utc).date()

    if p in {"week", "month", "quarter", "year"}:
        days = {"week": 7, "month": 30, "quarter": 90, "year": 365}[p]
        end_d = today
        start_d = end_d - timedelta(days=days - 1)
    elif p == "custom":
        sd = _parse_date(start_date)
        ed = _parse_date(end_date)
        if not sd or not ed:
            raise ValueError("start_date and end_date are required for custom period")
        if ed < sd:
            sd, ed = ed, sd
        start_d, end_d = sd, ed
        days = (end_d - start_d).days + 1
    else:
        days = max(1, int(analysis_period_days or 1))
        end_d = today
        start_d = end_d - timedelta(days=days - 1)

    start_dt = datetime.combine(start_d, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_d + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return start_dt, end_dt, days


class TargetCategoryPayload(BaseModel):
    category: str
    target_share: float
    is_active: bool = True


@router.get("/target-matrix/categories")
async def list_target_categories(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(InventoryTargetCategory).order_by(InventoryTargetCategory.category.asc()))
    rows = result.scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "category": r.category,
                "target_share": r.target_share,
                "is_active": r.is_active,
            }
            for r in rows
        ]
    }


@router.put("/target-matrix/categories")
async def upsert_target_categories(
    items: List[TargetCategoryPayload],
    db: AsyncSession = Depends(get_db),
):
    normalized = []
    for it in items:
        cat = (it.category or "").strip()
        if not cat:
            continue
        normalized.append((cat, float(it.target_share), bool(it.is_active)))

    if not normalized:
        return {"updated": 0, "created": 0}

    created = 0
    updated = 0
    for cat, share, active in normalized:
        existing_result = await db.execute(select(InventoryTargetCategory).where(InventoryTargetCategory.category == cat))
        existing = existing_result.scalar_one_or_none()
        if existing:
            existing.target_share = share
            existing.is_active = active
            db.add(existing)
            updated += 1
        else:
            db.add(InventoryTargetCategory(category=cat, target_share=share, is_active=active))
            created += 1

    await db.commit()
    return {"updated": updated, "created": created}


@router.delete("/target-matrix/categories/{category_id}")
async def delete_target_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(InventoryTargetCategory).where(InventoryTargetCategory.id == category_id))
    await db.commit()
    return {"deleted": True, "id": str(category_id)}


@router.get("/dashboard")
async def get_inventory_dashboard(
    analysis_period_days: int = Query(90, ge=1, le=365, description="Период анализа продаж в днях"),
    period: Optional[str] = Query(None, description="week|month|quarter|year|custom"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    seller_id: Optional[str] = Query(None, description="Фильтр по продавцу / 1C seller key"),
    brand: Optional[str] = Query(None, description="Фильтр по бренду"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    use_cache: bool = Query(True),
    force_refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    try:
        start_dt, end_dt, resolved_days = _resolve_period(
            analysis_period_days=analysis_period_days, period=period, start_date=start_date, end_date=end_date
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    service = InventoryControlService(db)
    resolved_store_id = await service._resolve_store_id(store_id)

    if use_cache and not force_refresh:
        snap = InventorySnapshotService(db)
        cached = await snap.get_fresh_snapshot(
            snapshot_type="dashboard",
            analysis_period_days=resolved_days,
            store_id=resolved_store_id,
            period_start=start_dt,
            period_end=end_dt,
            max_age_seconds=86400,
        )
        if cached:
            return cached

    rows = await service.build_inventory_rows(
        analysis_period_days=resolved_days,
        store_id=resolved_store_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    sales_conditions = [SalesRecord.sale_date >= start_dt, SalesRecord.sale_date < end_dt]
    if resolved_store_id:
        sales_conditions.append(SalesRecord.store_id == resolved_store_id)

    sales_stmt = select(
        func.coalesce(func.sum(SalesRecord.revenue), 0.0).label("revenue"),
        func.count(func.distinct(func.coalesce(SalesRecord.document_id, SalesRecord.external_id))).label("checks_count"),
    ).where(and_(*sales_conditions))
    sales_result = await db.execute(sales_stmt)
    revenue, checks_count = sales_result.one()

    items_stmt = select(func.coalesce(func.sum(SalesRecord.quantity), 0.0).label("items_count")).where(
        and_(
            *sales_conditions,
            SalesRecord.quantity > 0,
            (SalesRecord.revenue / SalesRecord.quantity) >= 3.0,
        )
    )
    items_result = await db.execute(items_stmt)
    (items_count,) = items_result.one()

    revenue = float(revenue or 0.0)
    checks_count = int(checks_count or 0)
    items_count = float(items_count or 0.0)
    avg_check = (revenue / checks_count) if checks_count > 0 else None

    sku_count = sum(1 for r in rows if r.stock_qty > 0)
    total_stock = sum(r.stock_qty for r in rows)
    stock_cover_values = [r.stock_cover for r in rows if r.stock_cover is not None]
    avg_stock_cover = (sum(stock_cover_values) / len(stock_cover_values)) if stock_cover_values else None
    critical_count = sum(1 for r in rows if r.status == "critical_stock")
    slow_moving_count = sum(1 for r in rows if r.status == "slow_moving")
    dead_stock_count = sum(1 for r in rows if r.status == "no_sales" and r.stock_qty > 0)

    order_rows = _build_reorder_rows(rows)
    items_to_order = len(order_rows)
    total_order_qty = sum(float(rr.get("order_qty") or 0.0) for rr in order_rows)
    total_order_amount = sum(float(rr.get("order_amount") or 0.0) for rr in order_rows)
    critical_items = sum(1 for r in rows if r.status == "critical_stock" and _calc_order_qty(r.sales_month, r.stock_qty) > 0)

    clearance_rows = _build_clearance_rows(rows)
    promo_count = sum(1 for r in clearance_rows if r.get("recommendation") == "PROMO")
    write_off_count = sum(1 for r in clearance_rows if r.get("recommendation") == "WRITE_OFF")

    payload = {
        "sales": {
            "revenue": revenue,
            "items_count": items_count,
            "avg_check": avg_check,
            "check_length": None,
            "checks_count": checks_count,
            "shifts_count": None,
            "avg_sales_per_shift": None,
            "plan_fact_deviation": None,
            "traffic": None,
            "revenue_per_visitor": None,
            "plan_fact_conversion": None,
        },
        "stock": {
            "sku_count": sku_count,
            "total_stock": total_stock,
            "avg_stock_cover": avg_stock_cover,
            "critical_count": critical_count,
            "slow_moving_count": slow_moving_count,
        },
        "purchases": {
            "total_order_qty": total_order_qty,
            "items_to_order": items_to_order,
            "total_order_amount": total_order_amount,
            "critical_items": critical_items,
        },
        "clearance": {
            "slow_moving_count": slow_moving_count,
            "dead_stock_count": dead_stock_count,
            "promo_count": promo_count,
            "bundle_count": sum(1 for r in clearance_rows if r.get("recommendation") == "BUNDLE"),
            "relocation_count": sum(1 for r in clearance_rows if r.get("recommendation") == "RELOCATION"),
            "write_off_count": write_off_count,
        },
        "updated_at": None,
    }

    snap = InventorySnapshotService(db)
    await snap.upsert_snapshot(
        snapshot_type="dashboard",
        analysis_period_days=resolved_days,
        store_id=resolved_store_id,
        period_start=start_dt,
        period_end=end_dt,
        payload=payload,
    )
    return payload


@router.get("/report")
async def get_inventory_report(
    analysis_period_days: int = Query(90, ge=1, le=365, description="Период анализа продаж в днях"),
    period: Optional[str] = Query(None, description="week|month|quarter|year|custom"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    color: Optional[str] = Query(None, description="Фильтр по цвету"),
    brand: Optional[str] = Query(None, description="Фильтр по бренду"),
    collection: Optional[str] = Query(None, description="Фильтр по коллекции"),
    limit: int = Query(2000, ge=1, le=20000),
    use_cache: bool = Query(True),
    force_refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    start_dt, end_dt, resolved_days = _resolve_period(
        analysis_period_days=analysis_period_days, period=period, start_date=start_date, end_date=end_date
    )
    can_cache = use_cache and not force_refresh and not any([category, color, brand, collection])
    if can_cache:
        snap = InventorySnapshotService(db)
        cached = await snap.get_fresh_snapshot(
            snapshot_type="report",
            analysis_period_days=resolved_days,
            store_id=store_id,
            period_start=start_dt,
            period_end=end_dt,
            max_age_seconds=86400,
        )
        if cached:
            if isinstance(cached.get("rows"), list):
                cached["rows"] = cached["rows"][:limit]
            return cached

    service = InventoryControlService(db)
    rows = await service.build_inventory_rows(
        analysis_period_days=resolved_days,
        store_id=store_id,
        start_dt=start_dt,
        end_dt=end_dt,
        category=category,
        color=color,
        brand=brand,
        collection=collection,
    )

    payload = [
        {
            "nomenclature": r.nomenclature,
            "color": r.color,
            "category": r.category,
            "sold_qty": r.sold_qty,
            "stock_qty": r.stock_qty,
            "sales_month": r.sales_month,
            "stock_cover": r.stock_cover,
            "status": r.status,
        }
        for r in rows[:limit]
    ]
    out = {"rows": payload, "total": len(rows)}
    if can_cache:
        snap = InventorySnapshotService(db)
        await snap.upsert_snapshot(
            snapshot_type="report",
            analysis_period_days=resolved_days,
            store_id=store_id,
            period_start=start_dt,
            period_end=end_dt,
            payload={"rows": payload[:5000], "total": len(rows)},
        )
    return out


@router.get("/order")
async def get_inventory_order(
    analysis_period_days: int = Query(90, ge=1, le=365, description="Период анализа продаж в днях"),
    period: Optional[str] = Query(None, description="week|month|quarter|year|custom"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    color: Optional[str] = Query(None, description="Фильтр по цвету"),
    brand: Optional[str] = Query(None, description="Фильтр по бренду"),
    collection: Optional[str] = Query(None, description="Фильтр по коллекции"),
    limit: int = Query(2000, ge=1, le=20000),
    use_cache: bool = Query(True),
    force_refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    start_dt, end_dt, resolved_days = _resolve_period(
        analysis_period_days=analysis_period_days, period=period, start_date=start_date, end_date=end_date
    )
    can_cache = use_cache and not force_refresh and not any([category, color, brand, collection])
    if can_cache:
        snap = InventorySnapshotService(db)
        cached = await snap.get_fresh_snapshot(
            snapshot_type="order",
            analysis_period_days=resolved_days,
            store_id=store_id,
            period_start=start_dt,
            period_end=end_dt,
            max_age_seconds=86400,
        )
        if cached:
            if isinstance(cached.get("rows"), list):
                cached["rows"] = cached["rows"][:limit]
            return cached

    service = InventoryControlService(db)
    rows = await service.build_inventory_rows(
        analysis_period_days=resolved_days,
        store_id=store_id,
        start_dt=start_dt,
        end_dt=end_dt,
        category=category,
        color=color,
        brand=brand,
        collection=collection,
    )
    order_rows = _build_reorder_rows(rows)
    order_rows.sort(key=lambda r: float(r.get("order_qty") or 0.0), reverse=True)
    out = {"rows": order_rows[:limit], "total": len(order_rows)}
    if can_cache:
        snap = InventorySnapshotService(db)
        await snap.upsert_snapshot(
            snapshot_type="order",
            analysis_period_days=resolved_days,
            store_id=store_id,
            period_start=start_dt,
            period_end=end_dt,
            payload={"rows": order_rows[:5000], "total": len(order_rows)},
        )
    return out


@router.get("/clearance")
async def get_inventory_clearance(
    analysis_period_days: int = Query(90, ge=1, le=365, description="Период анализа продаж в днях"),
    period: Optional[str] = Query(None, description="week|month|quarter|year|custom"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    limit: int = Query(2000, ge=1, le=20000),
    use_cache: bool = Query(True),
    force_refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    start_dt, end_dt, resolved_days = _resolve_period(
        analysis_period_days=analysis_period_days, period=period, start_date=start_date, end_date=end_date
    )
    if use_cache and not force_refresh:
        snap = InventorySnapshotService(db)
        cached = await snap.get_fresh_snapshot(
            snapshot_type="clearance",
            analysis_period_days=resolved_days,
            store_id=store_id,
            period_start=start_dt,
            period_end=end_dt,
            max_age_seconds=86400,
        )
        if cached:
            if isinstance(cached.get("rows"), list):
                cached["rows"] = cached["rows"][:limit]
            return cached

    service = InventoryControlService(db)
    rows = await service.build_inventory_rows(
        analysis_period_days=resolved_days, store_id=store_id, start_dt=start_dt, end_dt=end_dt
    )
    clearance_rows = _build_clearance_rows(rows)
    out = {"rows": clearance_rows[:limit], "total": len(clearance_rows)}
    snap = InventorySnapshotService(db)
    await snap.upsert_snapshot(
        snapshot_type="clearance",
        analysis_period_days=resolved_days,
        store_id=store_id,
        period_start=start_dt,
        period_end=end_dt,
        payload={"rows": clearance_rows[:5000], "total": len(clearance_rows)},
    )
    return out


@router.get("/assortment/filters")
async def get_inventory_assortment_filters(
    analysis_period_days: int = Query(90, ge=1, le=365, description="Период анализа продаж в днях"),
    period: Optional[str] = Query(None, description="week|month|quarter|year|custom"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    limit: int = Query(5000, ge=100, le=20000, description="Лимит строк продаж для извлечения продавцов"),
    db: AsyncSession = Depends(get_db),
):
    start_dt, end_dt, resolved_days = _resolve_period(
        analysis_period_days=analysis_period_days, period=period, start_date=start_date, end_date=end_date
    )
    service = InventoryControlService(db)
    resolved_store_id = await service._resolve_store_id(store_id)
    agent = AssortmentMatrixAgent(db)

    sales_rows = await agent._load_sales_detail_rows(
        start_dt=start_dt,
        end_dt=end_dt,
        store_id=resolved_store_id,
        seller_id=None,
        seller_name=None,
        brand=None,
        category=None,
    )
    seller_map: Dict[str, Dict[str, Any]] = {}
    for row in sales_rows[:limit]:
        seller_key = str(row.get("seller_external_id") or row.get("seller_id") or "").strip()
        seller_label = str(row.get("seller_name") or "").strip()
        if not seller_key or seller_key == "unmatched" or seller_label == "Не сопоставлено с продавцом":
            continue
        seller_map[seller_key] = {
            "value": seller_key,
            "label": seller_label or seller_key,
            "seller_id": seller_key,
            "seller_name": seller_label,
        }

    try:
        plan_rows = await agent._load_plan_sources(start_dt=start_dt, end_dt=end_dt, store_id=resolved_store_id)
        for row in plan_rows:
            if row.get("warning"):
                continue
            seller_key = str(row.get("seller_external_id") or "").strip()
            seller_label = str(row.get("seller_name") or "").strip()
            if seller_key and seller_key not in seller_map:
                seller_map[seller_key] = {
                    "value": seller_key,
                    "label": seller_label or seller_key,
                    "seller_id": seller_key,
                    "seller_name": seller_label,
                }
    except Exception:
        pass

    sales_filters = [
        SalesRecord.sale_date >= start_dt,
        SalesRecord.sale_date < end_dt,
        sales_record_eligible_product_filter(SalesRecord, func, and_),
    ]
    if resolved_store_id:
        sales_filters.append(SalesRecord.store_id == resolved_store_id)

    product_brands_result = await db.execute(
        select(Product.brand).where(
            Product.is_active == True,
            Product.brand.isnot(None),
            Product.brand != "",
            product_eligible_filter(Product, func, and_),
        ).distinct()
    )
    sales_brands_result = await db.execute(
        select(SalesRecord.product_brand).where(and_(*sales_filters), SalesRecord.product_brand.isnot(None), SalesRecord.product_brand != "").distinct()
    )
    product_categories_result = await db.execute(
        select(Product.category).where(
            Product.is_active == True,
            Product.category.isnot(None),
            Product.category != "",
            product_eligible_filter(Product, func, and_),
        ).distinct()
    )
    sales_categories_result = await db.execute(
        select(SalesRecord.product_category).where(and_(*sales_filters), SalesRecord.product_category.isnot(None), SalesRecord.product_category != "").distinct()
    )

    def clean_values(values: List[Any]) -> List[str]:
        out = sorted({str(value).strip() for value in values if str(value or "").strip()}, key=lambda item: item.lower())
        return out

    brands = clean_values([row[0] for row in product_brands_result.all()] + [row[0] for row in sales_brands_result.all()])
    categories = clean_values(
        [row[0] for row in product_categories_result.all()] + [row[0] for row in sales_categories_result.all()]
    )
    sellers = sorted(seller_map.values(), key=lambda item: str(item.get("label") or "").lower())

    return {
        "period": {"start_date": start_dt.date().isoformat(), "end_date": (end_dt - timedelta(days=1)).date().isoformat(), "days": resolved_days},
        "store_id": resolved_store_id,
        "sellers": sellers,
        "brands": brands,
        "categories": categories,
    }


@router.get("/assortment")
async def get_inventory_assortment(
    analysis_period_days: int = Query(90, ge=1, le=365, description="Период анализа продаж в днях"),
    period: Optional[str] = Query(None, description="week|month|quarter|year|custom"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    seller_id: Optional[str] = Query(None, description="Фильтр по продавцу / seller_id из 1C"),
    seller_name: Optional[str] = Query(None, description="Фильтр по имени продавца, если seller_id еще не сопоставлен"),
    brand: Optional[str] = Query(None, description="Фильтр по бренду"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    limit: int = Query(200, ge=1, le=500, description="Лимит товарных позиций в диагностике"),
    use_cache: bool = Query(True),
    force_refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    start_dt, end_dt, resolved_days = _resolve_period(
        analysis_period_days=analysis_period_days, period=period, start_date=start_date, end_date=end_date
    )
    service = InventoryControlService(db)
    resolved_store_id = await service._resolve_store_id(store_id)
    can_cache = use_cache and not force_refresh and not any([seller_id, seller_name, brand, category]) and limit == 200
    if can_cache:
        snap = InventorySnapshotService(db)
        cached = await snap.get_fresh_snapshot(
            snapshot_type=ASSORTMENT_SNAPSHOT_TYPE,
            analysis_period_days=resolved_days,
            store_id=resolved_store_id,
            period_start=start_dt,
            period_end=end_dt,
            max_age_seconds=86400,
        )
        if cached:
            return cached

    agent = AssortmentMatrixAgent(db)
    out = await agent.build_assortment(
        analysis_period_days=resolved_days,
        store_id=resolved_store_id,
        start_dt=start_dt,
        end_dt=end_dt,
        seller_id=seller_id,
        seller_name=seller_name,
        brand=brand,
        category=category,
        limit=limit,
    )

    if can_cache:
        snap = InventorySnapshotService(db)
        await snap.upsert_snapshot(
            snapshot_type=ASSORTMENT_SNAPSHOT_TYPE,
            analysis_period_days=resolved_days,
            store_id=resolved_store_id,
            period_start=start_dt,
            period_end=end_dt,
            payload=out,
        )
    return out


@router.get("/marketing-link")
async def get_inventory_marketing_link(
    analysis_period_days: int = Query(90, ge=1, le=365, description="Период анализа продаж в днях"),
    period: Optional[str] = Query(None, description="week|month|quarter|year|custom"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    limit: int = Query(2000, ge=1, le=20000),
    use_cache: bool = Query(True),
    force_refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    start_dt, end_dt, resolved_days = _resolve_period(
        analysis_period_days=analysis_period_days, period=period, start_date=start_date, end_date=end_date
    )
    if use_cache and not force_refresh:
        snap = InventorySnapshotService(db)
        cached = await snap.get_fresh_snapshot(
            snapshot_type=MARKETING_LINK_SNAPSHOT_TYPE,
            analysis_period_days=resolved_days,
            store_id=store_id,
            period_start=start_dt,
            period_end=end_dt,
            max_age_seconds=86400,
        )
        if cached:
            if isinstance(cached.get("rows"), list):
                cached["rows"] = cached["rows"][:limit]
            return cached

    service = InventoryControlService(db)
    rows = await service.build_inventory_rows(
        analysis_period_days=resolved_days, store_id=store_id, start_dt=start_dt, end_dt=end_dt
    )
    payload: List[Dict[str, Any]] = []
    for r in rows:
        group = _marketing_group(r.sales_month, r.stock_cover)
        if not group:
            continue
        recommended_channel = _marketing_channel(group)
        basis = _marketing_basis(group, r.sales_month, r.stock_cover)
        payload.append(
            {
                "nomenclature": r.nomenclature,
                "color": r.color,
                "sales_month": r.sales_month,
                "stock_qty": r.stock_qty,
                "stock_cover": r.stock_cover,
                "group": group,
                "recommended_channel": recommended_channel,
                "basis": basis,
            }
        )

    payload.sort(key=lambda x: (x.get("group") or "", -(float(x.get("sales_month") or 0.0)), float(x.get("stock_cover") or 0.0)))
    out = {"rows": payload[:limit], "total": len(payload)}
    snap = InventorySnapshotService(db)
    await snap.upsert_snapshot(
        snapshot_type=MARKETING_LINK_SNAPSHOT_TYPE,
        analysis_period_days=resolved_days,
        store_id=store_id,
        period_start=start_dt,
        period_end=end_dt,
        payload={"rows": payload[:5000], "total": len(payload)},
    )
    return out


@router.get("/pricing/report")
async def get_pricing_report(
    analysis_period_days: int = Query(90, ge=1, le=365, description="Период анализа продаж в днях"),
    period: Optional[str] = Query(None, description="week|month|quarter|year|custom"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    limit: int = Query(2000, ge=1, le=20000),
    use_cache: bool = Query(True),
    force_refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    start_dt, end_dt, resolved_days = _resolve_period(
        analysis_period_days=analysis_period_days, period=period, start_date=start_date, end_date=end_date
    )
    if use_cache and not force_refresh:
        snap = InventorySnapshotService(db)
        cached = await snap.get_fresh_snapshot(
            snapshot_type="pricing_report",
            analysis_period_days=resolved_days,
            store_id=store_id,
            period_start=start_dt,
            period_end=end_dt,
            max_age_seconds=604800,
        )
        if cached:
            if isinstance(cached.get("rows"), list):
                cached["rows"] = cached["rows"][:limit]
            return cached

    service = InventoryControlService(db)
    rows = await service.build_inventory_rows(
        analysis_period_days=resolved_days, store_id=store_id, start_dt=start_dt, end_dt=end_dt
    )
    payload: List[Dict[str, Any]] = []
    for r in rows:
        protected = bool(r.is_core_assortment or r.supports_brand_concept)
        status = _pricing_status(r.sales_month, r.stock_cover, protected=protected)
        payload.append(
            {
                "nomenclature": r.nomenclature,
                "color": r.color,
                "sales_month": r.sales_month,
                "stock_qty": r.stock_qty,
                "stock_cover": r.stock_cover,
                "pricing_status": status,
                "is_core_assortment": r.is_core_assortment,
                "supports_brand_concept": r.supports_brand_concept,
            }
        )
    out = {"rows": payload[:limit], "total": len(payload)}
    snap = InventorySnapshotService(db)
    await snap.upsert_snapshot(
        snapshot_type="pricing_report",
        analysis_period_days=resolved_days,
        store_id=store_id,
        period_start=start_dt,
        period_end=end_dt,
        payload={"rows": payload[:5000], "total": len(payload)},
    )
    return out


def _calc_optimal_stock(sales_month: float) -> float:
    return float(sales_month) * 3.0


def _calc_order_qty(sales_month: float, stock_qty: float) -> float:
    order_qty = _calc_optimal_stock(sales_month) - float(stock_qty or 0.0)
    return float(order_qty) if order_qty > 0 else 0.0


def _build_reorder_rows(rows: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        order_qty = _calc_order_qty(r.sales_month, r.stock_qty)
        if order_qty <= 0:
            continue
        optimal_stock = _calc_optimal_stock(r.sales_month)
        order_amount = None
        if r.price_cents is not None:
            order_amount = (order_qty * (float(r.price_cents) / 100.0))
        out.append(
            {
                "nomenclature": r.nomenclature,
                "color": r.color,
                "stock_qty": r.stock_qty,
                "sales_month": r.sales_month,
                "optimal_stock": optimal_stock,
                "order_qty": order_qty,
                "order_amount": order_amount,
                "status": r.status,
            }
        )
    return out


def _build_clearance_rows(rows: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        if r.stock_qty <= 0:
            continue
        stock_cover = r.stock_cover
        protected = bool(r.is_core_assortment or r.supports_brand_concept)
        recommendation = None
        reason = None
        if r.sales_month <= 0:
            if stock_cover is not None and stock_cover > 12:
                recommendation = "WRITE_OFF"
                reason = "sales_month = 0 AND stock_cover > 12"
            else:
                recommendation = "RELOCATION"
                reason = "sales_month = 0"
        else:
            if stock_cover is not None and stock_cover > 6:
                recommendation = "PROMO"
                reason = "sales_month > 0 AND stock_cover > 6"
            elif stock_cover is not None and stock_cover > 5:
                recommendation = "BUNDLE"
                reason = "sales_month > 0 AND stock_cover > 5"

        if protected and recommendation in ("WRITE_OFF", "PROMO"):
            if recommendation == "WRITE_OFF":
                recommendation = "RELOCATION"
                reason = "protected_product: prefer relocation before write_off"
            else:
                recommendation = "BUNDLE"
                reason = "protected_product: prefer bundle before promo"

        if recommendation:
            out.append(
                {
                    "nomenclature": r.nomenclature,
                    "color": r.color,
                    "stock_qty": r.stock_qty,
                    "sales_month": r.sales_month,
                    "stock_cover": stock_cover,
                    "recommendation": recommendation,
                    "reason": reason,
                    "is_protected": protected,
                }
            )

    out.sort(key=lambda x: (x.get("recommendation") or "", -(float(x.get("stock_cover") or 0.0))))
    return out


def _marketing_group(sales_month: float, stock_cover: Optional[float]) -> Optional[str]:
    if sales_month > 0.7 and stock_cover is not None and stock_cover <= 2:
        return "PROTECT_PRODUCTS"
    if sales_month > 0.5 and stock_cover is not None and stock_cover <= 3:
        return "GROWTH_PRODUCTS"
    if stock_cover is not None and stock_cover > 6:
        return "PROMO_PRODUCTS"
    if stock_cover is not None and stock_cover > 4 and sales_month > 0.2:
        return "INVENTORY_RELIEF"
    return None


def _marketing_channel(group: str) -> Optional[str]:
    if group == "GROWTH_PRODUCTS":
        return "Instagram"
    if group == "INVENTORY_RELIEF":
        return "Email / SMS"
    if group == "PROMO_PRODUCTS":
        return "Promotions"
    return None


def _marketing_basis(group: str, sales_month: float, stock_cover: Optional[float]) -> str:
    sc = "—" if stock_cover is None else f"{stock_cover:.2f}"
    return f"{group}: sales_month={sales_month:.2f}, stock_cover={sc}"


def _pricing_status(sales_month: float, stock_cover: Optional[float], protected: bool) -> str:
    if sales_month <= 0:
        return "HOLD PRICE"
    if stock_cover is None:
        return "HOLD PRICE"
    if sales_month > 0.7 and stock_cover <= 3:
        return "NO DISCOUNT"
    if sales_month > 0.2 and 3 < stock_cover <= 6:
        return "BUNDLE INSTEAD OF DISCOUNT" if protected else "LIGHT DISCOUNT"
    if sales_month <= 0.2 and stock_cover > 6:
        return "BUNDLE INSTEAD OF DISCOUNT" if protected else "HEAVY DISCOUNT"
    return "HOLD PRICE"
